Operations Runbook
==================

This page covers the operational knobs that influence the API->DB
pipeline at runtime: feature flags, secret provisioning, database
bootstrap, and rollback procedures.

Stability gate
--------------

Before merging refactor work, run the mandatory stability gate::

   python scripts/stability_gate.py

See :doc:`stability-slos` for SLO targets and critical user journeys.

Feature flags
-------------

Feature flags live under ``feature_flags`` in ``settings.json`` and are
read by :func:`backend.composition.build_embedded_facade` -- well, by
the adapters built from it. The flags currently honored are:

============================  ===========  =========================================================
Flag                          Default      Effect
============================  ===========  =========================================================
``new_ingestion_pipeline``    ``true``     When ``false``, ``APICoordinator`` skips the bounded
                                           pipeline and returns whatever the legacy
                                           ``AnimeAPI.searchAnime`` thread-fan-out produces. Use this
                                           only as an emergency rollback.
``db_gateway_writes_only``    ``true``     When ``false``, the pipeline returns records without
                                           persisting them. Useful for dry-run searches and tests.
``strict_download_url_``      ``true``     Reserved name. The current implementation always uses the
``validation``                             strict validator; the flag is wired into the settings file
                                           for future relaxation.
``secure_db_bootstrap``       ``true``     Reserved name. The embedded MariaDB always starts without
                                           ``--skip-grant-tables``; the flag exists so future code
                                           can short-circuit setup steps after the first run.
============================  ===========  =========================================================

To flip a flag at runtime call::

   coordinator.configure({"new_ingestion_pipeline": False})

Unknown keys are accepted (and ignored) so downstream features can
introduce new flags without breaking existing deployments.

Secret provisioning
-------------------

Secrets are loaded via :func:`core.security.load_secret`. The lookup
order is:

1. ``os.environ[key]`` (or the explicit ``env`` mapping).
2. ``settings[key]`` (supports dotted paths such as
   ``"api_credentials.myanimelist.client_id"``).
3. The ``default`` argument.

Empty strings count as missing.

MyAnimeList OAuth
~~~~~~~~~~~~~~~~~

* ``ANIMEMANAGER_MAL_CLIENT_ID``
* ``ANIMEMANAGER_MAL_CLIENT_SECRET``

When the environment variables are unset, ``MyAnimeListNetWrapper``
falls back to ``settings.json``::

   {
     "api_credentials": {
       "myanimelist": {
         "client_id": "...",
         "client_secret": "..."
       }
     }
   }

If both sources are empty the wrapper logs a single ``"MAL OAuth
credentials are not configured"`` message and quietly disables the
interactive auth flow; the rest of the application continues to work.

OAuth tokens are persisted to ``animeAPI/token.json`` (configurable
via ``MyAnimeListNetWrapper(tokenPath=...)``). After every refresh the
file is ``chmod 600`` on POSIX filesystems that support it; this is
best-effort on FAT / Windows.

Database bootstrap (embedded MariaDB)
-------------------------------------

The embedded MariaDB launcher (``db_managers/embeddedMariaDB.py``)
follows three rules in steady state:

1. The server is started **without** ``--skip-grant-tables``.
2. Root fallback authentication is **disabled** unless
   ``allow_root_fallback`` is set explicitly in ``settings.json``::

      {
        "database": {
          "allow_root_fallback": true
        }
      }

   This flag exists for legacy environments where the bootstrap user
   has not yet been migrated; new deployments should never enable it.
3. The fallback ``getId`` path validates the API column name against
   an allow-list (``mal_id``, ``kitsu_id``, ``anilist_id``,
   ``anidb_id``, ``id``) and uses parameterized queries.

URL validation
--------------

:func:`core.security.validate_url` is invoked by the download manager
before every outbound HTTP request. The default policy:

* Scheme must be ``https``.
* Hostname must resolve to a public IP. Private, loopback, link-local,
  multicast, reserved, and unspecified addresses are rejected.
* ``allowed_hosts`` (when configured) is matched against the hostname
  plus its dotted suffixes, so ``example.com`` in the list permits
  ``api.example.com`` but not ``evilexample.com``.

To tighten the policy further -- for example, restrict downloads to a
fixed set of mirrors -- pass ``allowed_hosts={"a.example.com",
"b.example.com"}`` to ``validate_url``. The download manager currently
delegates without an allow-list; future work can pull the list from
settings.

Rollback procedures
-------------------

**Symptom: search latency regresses sharply after the new pipeline
goes live.**

1. Snapshot telemetry::

      from shared.telemetry import get_telemetry
      print(get_telemetry().snapshot())

   Check ``ingestion.total_ms``, per-provider timers, and
   ``ingestion.failed_providers``.
2. If a single provider is consistently the bottleneck, drop it from
   the loaded list in ``settings.json`` or lower its limit.
3. As an emergency stop, flip ``new_ingestion_pipeline`` to ``false``
   so the coordinator hands control back to ``AnimeAPI.searchAnime``.
   This is reversible at any time.

**Symptom: persistence backs up under high load.**

1. Enable the queued path::

      db_manager.enable_batched_writes(batch_size=50, max_latency_ms=200)

2. Watch ``db.queued_writes_flushed`` and
   ``db_manager.write_queue_stats()`` for backpressure (``dropped``
   should stay at 0).
3. If the queue is dropping records, raise ``queue_maxsize`` in
   ``PersistenceQueue`` -- or scale the underlying DB.

**Symptom: download links to private hosts are being followed.**

1. This must not happen; if it does, file a security ticket.
2. Confirm ``validate_url`` returns ``(False, "...")`` for the URL.
3. Verify no caller is bypassing ``DownloadManager._is_url_allowed``.

Health checks
-------------

The pipeline currently exposes its health through telemetry counters
rather than a dedicated probe. A minimal health probe can be assembled
in any client::

   from shared.telemetry import get_telemetry

   def health_snapshot() -> dict:
       snap = get_telemetry().snapshot()
       counters = snap["counters"]
       gauges = snap["gauges"]
       return {
           "last_search_records": gauges.get(
               "coordinator.last_search_records", 0.0
           ),
           "last_search_failed_providers": gauges.get(
               "coordinator.last_search_failed", 0.0
           ),
           "persistence_errors": counters.get(
               "coordinator.persist_errors", 0
           ),
       }

A future enhancement can promote this to an HTTP endpoint on the
``clients/http`` app.

Logging
-------

Every component routes through the central ``Logger`` mixin. The
ingestion pipeline emits a single line per search summarising
``status``, ``records``, ``failed``, and ``elapsed_ms``. Per-provider
errors are logged with their exception class name; the full traceback
is only emitted by the wrappers themselves to keep production logs
compact.

Use :func:`core.security.redact` before including request bodies or
response payloads in log messages -- it masks bearer tokens and keys
matching ``password``, ``token``, ``api_key``, ``client_secret``, ...

Glossary
--------

* **Provider** -- a metadata source under ``animeAPI/`` (Jikan,
  AniList, Kitsu, MAL, ...).
* **Ingestion** -- the cycle that turns provider responses into rows.
* **Sink** -- the callable invoked by :class:`IngestionPipeline` to
  persist a deduplicated batch. The coordinator wires it to
  :meth:`DatabaseManager.upsert_anime_batch`.
* **Gateway path** -- the single allowed route for API-originated
  writes. Lives entirely inside :class:`DatabaseManager`.
