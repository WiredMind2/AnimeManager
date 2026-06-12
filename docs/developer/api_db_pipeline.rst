API → DB Pipeline
=================

This document is the deep dive on the pipeline that converts metadata
provider responses into rows in the local database. It is the
counterpart to :doc:`architecture`; everything described here lives
under the ``core/`` and ``components/`` packages and is consumed by the
hexagonal layer through :class:`backend.adapters.legacy_runtime.LegacyMetadataProviderAdapter`.

Why a dedicated pipeline?
-------------------------

The legacy code performed three independent layers of concurrency
(``Manager`` threads + ``APICoordinator`` executor + ``AnimeAPI``
per-provider threads + ``ItemList`` streaming threads), persisted
records through implicit callbacks, and built SQL fragments via
f-strings. The new pipeline replaces all of that with:

* one bounded worker pool inside
  :class:`core.ingestion_pipeline.IngestionPipeline`,
* one typed contract (:class:`core.contracts.AnimeRecord`) flowing
  between adapters and the persistence sink,
* one explicit persistence boundary
  (:meth:`components.database_manager.DatabaseManager.upsert_anime_batch`),
* one whitelist-only query builder
  (:func:`core.query_builder.build_anime_list_query`),
* one telemetry collector for SLO-ready metrics
  (:func:`core.telemetry.get_telemetry`),
* one centralized URL validator and secret loader
  (:mod:`core.security`).

End-to-end flow
---------------

::

    ┌──────────────────────────────────┐
    │ AnimeApplicationService.search() │
    └─────────────────┬────────────────┘
                      │
                      ▼
    ┌──────────────────────────────────┐
    │ LegacyMetadataProviderAdapter    │
    │     .search()                    │
    └─────────────────┬────────────────┘
                      │ APICoordinator.search_anime(...)
                      ▼
    ┌──────────────────────────────────┐
    │ APICoordinator                   │   (components/)
    │   • rate limiter                 │
    │   • _spec_for(provider) for each │
    │     loaded AnimeAPI wrapper      │
    │   • CatalogIdentityService       │
    │     (canonical id + external_ids)│
    └─────────────────┬────────────────┘
                      │ IngestionPipeline.run(specs, terms, ...)
                      ▼
    ┌──────────────────────────────────┐
    │ IngestionPipeline                │   (core/)
    │   • ThreadPoolExecutor (bounded) │
    │   • per-provider timeout         │
    │   • partial/failed accounting    │
    │   • dedupe by canonical id       │
    └─────────────────┬────────────────┘
                      │ list[AnimeRecord] + optional sink
                      ▼
    ┌──────────────────────────────────┐
    │ persistence sink                 │
    │   = DatabaseManager.upsert_anime │
    │     _batch(animes)               │
    └─────────────────┬────────────────┘
                      │ db.save(...) one record at a time
                      │ inside a single get_connection() ctx
                      ▼
    ┌──────────────────────────────────┐
    │ db_managers.BaseDB               │
    │   • MariaDB / SQLite / MySQL     │
    └──────────────────────────────────┘

Module responsibilities
-----------------------

``application/services/catalog_identity.py`` / ``catalog_merge.py``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* :class:`~application.services.catalog_identity.CatalogIdentityService`
  resolves a single internal catalogue id from provider ``external_ids``
  (``mal_id``, ``anilist_id``, ``kitsu_id``, …). Provider wrappers call
  ``resolve_catalog_id`` during conversion instead of ad-hoc ``save_mapped``
  SQL.
* :class:`~application.services.catalog_merge.CatalogMergeService` folds
  duplicate ``indexList`` / ``anime`` rows through
  :mod:`adapters.persistence.catalog_repository` (transactional
  ``save=True`` writes). Startup repair uses provider-id grouping by
  default; title-based repair is opt-in.

``core/contracts.py``
~~~~~~~~~~~~~~~~~~~~~

Defines the typed DTOs that every adapter must produce and that every
persistence sink must accept. ``AnimeRecord`` is a frozen dataclass so
adapters cannot mutate it after creation; ``external_ids`` carries
cross-provider keys; ``IngestionResult`` reports
the run-level status (``COMPLETE`` / ``PARTIAL`` / ``FAILED``) plus
collected records, failed-provider count, total provider count,
elapsed milliseconds, and per-provider error tags.

``core/ingestion_pipeline.py``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* :class:`~core.ingestion_pipeline.ProviderSpec` -- ``(name, search,
  adapter)`` triple: the search callable is whatever the provider
  exposes (default: ``provider.searchAnime``) and the adapter is the
  callable that turns one raw response into an ``AnimeRecord`` (or
  ``None`` to drop it).
* :class:`~core.ingestion_pipeline.IngestionPipeline.run` -- submits
  one job per spec to the executor, honors a per-provider timeout,
  cancels stragglers when the wall-clock budget is exhausted, and
  returns an :class:`~core.contracts.IngestionResult`.
* Always called via :meth:`APICoordinator._search_via_pipeline`; nothing
  else should ever spawn provider threads.

``core/security.py``
~~~~~~~~~~~~~~~~~~~~

* ``validate_url(url, *, allowed_schemes, allowed_hosts, blocked_attrs,
  resolver)`` -- returns ``(safe: bool, reason: str)``. Rejects empty /
  unparseable URLs, schemes outside the allow-list (default
  ``("https",)``), hosts not in ``allowed_hosts`` (when given), and
  hostnames that resolve to private, loopback, link-local, multicast,
  reserved, or unspecified IPs. The resolver defaults to
  ``socket.gethostbyname`` but is parameterizable so tests can monkey
  patch DNS.
* ``load_secret(key, *, settings, env, default)`` -- ``env`` first
  (default ``os.environ``), then ``settings`` (supports dotted paths
  like ``"section.subkey"``), then ``default``. Empty / whitespace-only
  strings count as missing.
* ``redact(value)`` -- replaces bearer tokens in strings, masks dict
  keys matching the secret pattern (``password``, ``token``,
  ``api_key``, ``client_secret``, ...). Use it before logging
  request/response bodies.

``core/telemetry.py``
~~~~~~~~~~~~~~~~~~~~~

Counters / gauges / latency histograms with hard caps. Use
``get_telemetry()`` to grab the process-wide collector; tests can
``reset_telemetry()`` between runs. The pipeline and components push
these series:

* ``ingestion.total_ms``, ``ingestion.records_collected``,
  ``ingestion.records_persisted``, ``ingestion.failed_providers``
* ``ingestion.provider.<Name>_ms``, ``ingestion.sink_flush_ms``
* ``coordinator.search_errors``, ``coordinator.persist_errors``,
  ``coordinator.last_search_records``, ``coordinator.last_search_failed``
* ``db.upsert_anime_batch_ms``, ``db.upserts_committed``,
  ``db.queued_writes_flushed``, ``db.queued_write_errors``

``core/query_builder.py``
~~~~~~~~~~~~~~~~~~~~~~~~~

``build_anime_list_query(criteria, listrange, hide_rated, user_id)``
returns an :class:`~core.query_builder.AnimeListQuery`. Only criteria
in :data:`~core.query_builder.ALLOWED_CRITERIA` are accepted; anything
else collapses to ``"DEFAULT"``. The numeric ``user_id`` is coerced
through :func:`int` (raises on non-numeric strings) and the result is
interpolated into ``user_id={uid}`` against a constant join template.
All status / tag values are taken from the allow-list, so the produced
SQL fragments contain no caller-controlled text.

``core/persistence_queue.py``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A producer/consumer queue that flushes records in batches sized by
``batch_size`` or by ``max_latency_ms``. Use
:meth:`components.database_manager.DatabaseManager.enable_batched_writes`
to wire it in when ingesting large streams. ``put(record, block=False)``
returns ``False`` on backpressure; flush callables can raise without
killing the worker.

``components/api_coordinator.py``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:class:`~components.api_coordinator.APICoordinator` self-initializes
the pipeline in ``__init__``; adapters merely call ``set_api`` and
``set_database_manager`` and then ``search_anime``. ``close()`` shuts
down the executor; the coordinator no longer needs an external
lifecycle driver. Feature flags:

* ``new_ingestion_pipeline`` (default ``True``) -- when ``False``,
  bypasses the pipeline and returns ``self._api.searchAnime(...)``.
  Use it for emergency rollback only.
* ``db_gateway_writes_only`` (default ``True``) -- when ``False``, the
  pipeline returns records without persisting them. Useful in tests
  and dry-runs.

``components/database_manager.py``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The only legal write path for API-originated data. Surface:

* ``set_database(db)`` -- attach a :class:`db_managers.BaseDB` instance.
* ``search_anime(terms, limit)`` -- bulk metadata loaded via
  ``BaseDB.get_all_metadata_bulk`` (eliminates N+1).
* ``get_anime_list(criteria, listrange, hide_rated, user_id)`` --
  delegates SQL fragment construction to ``build_anime_list_query``.
* ``upsert_anime_batch(records)`` -- synchronous batched save.
* ``upsert_metadata_batch(records)`` -- same for metadata pairs.
* ``enable_batched_writes(...)`` / ``enqueue_anime(record)`` --
  asynchronous queued path for high-volume ingest.
* ``save_torrent(anime_id, torrent)`` / ``get_torrent_data(hash)`` --
  back-compat helpers used by ``DownloadManager``.
* ``close()`` -- drains the optional write queue and releases the DB
  connection.

``components/download_manager.py``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Self-initializes its executor and queue worker.
* Validates every outbound URL through ``core.security.validate_url``;
  disables redirects; caps response size to 10 MiB.
* Receives the ``DatabaseManager`` through ``set_database_manager``
  (replacing the old global container lookup); persistence of torrent
  metadata is delegated to it.
* ``close()`` cancels in-flight downloads and shuts down the executor.

Concurrency model
-----------------

* The coordinator owns **one** ``ThreadPoolExecutor`` (default 4
  workers). The pipeline uses that executor; nothing in
  ``animeAPI/__init__.py`` spawns search threads anymore.
* The persistence queue (when enabled) owns **one** background worker.
* The download manager owns **one** queue-processor thread plus its
  own bounded executor for the actual fetches.

Telemetry-driven SLOs
---------------------

Snapshot the collector at any time::

   from shared.telemetry import get_telemetry
   snap = get_telemetry().snapshot()

The snapshot has ``counters``, ``gauges``, and ``timers`` dictionaries.
Timer entries expose ``count``, ``min``, ``p50``, ``p95``, ``max``,
``avg`` (milliseconds). Production deployments can forward the snapshot
to any metrics backend at a tick of their choice.

Where to start reading
----------------------

1. ``core/contracts.py`` -- the data model.
2. ``core/ingestion_pipeline.py`` -- the orchestration.
3. ``components/api_coordinator.py`` -- the integration with legacy
   wrappers.
4. ``components/database_manager.py`` -- the persistence boundary.
5. ``backend/adapters/legacy_runtime.py`` -- the hexagonal seam.

Operational behavior is covered in :doc:`operations`.
