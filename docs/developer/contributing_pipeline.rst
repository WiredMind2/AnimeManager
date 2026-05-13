Contributing to the API → DB Pipeline
=====================================

This guide tells you how to extend, debug, and test the API->DB
pipeline. For the high-level architecture see :doc:`api_db_pipeline`;
for runtime knobs see :doc:`operations`.

Layout
------

::

    core/                       # dependency-light infrastructure
      contracts.py              # AnimeRecord / IngestionResult / enums
      ingestion_pipeline.py     # IngestionPipeline + ProviderSpec
      query_builder.py          # build_anime_list_query + ALLOWED_CRITERIA
      persistence_queue.py      # PersistenceQueue
      security.py               # validate_url, load_secret, redact
      telemetry.py              # TelemetryCollector + get_telemetry
      base_component.py         # minimal base class for components

    components/                 # long-lived services
      api_coordinator.py        # search fan-out + persistence sink
      database_manager.py       # gateway for all API-originated writes
      download_manager.py       # URL-validated torrent / HTTP fetcher

    backend/adapters/legacy_runtime.py
                                # the hexagonal seam between ports and
                                # the components above

    tests/unit/core/            # one file per core module
    tests/unit/components/      # integration-style component tests
    tests/unit/db_managers/     # embedded MariaDB security regressions
    tests/unit/test_pipeline_refactor.py
                                # legacy smoke checks still kept around

Adding a new metadata provider
------------------------------

1. Write the wrapper under ``animeAPI/<Name>.py``. It must subclass
   :class:`animeAPI.APIUtils.APIUtils` (or expose ``searchAnime`` with
   the same signature).
2. Expose ``self.__name__`` (or rely on the class name) so the
   telemetry counter ``ingestion.provider.<Name>_ms`` is readable.
3. Add the wrapper to ``animeAPI/__init__.py``'s auto-loader by
   placing it in the package directory; ``AnimeAPI.load_apis`` picks
   it up automatically.
4. **Do not** call ``self.database.save(...)`` directly from the
   wrapper; that path is dead. Provider responses must reach the DB
   through :class:`components.api_coordinator.APICoordinator` -- the
   coordinator already wires every provider's ``searchAnime`` into
   :class:`core.ingestion_pipeline.IngestionPipeline`.
5. If your wrapper needs to surface fields that the default
   ``_legacy_adapter`` does not project, either extend
   :class:`core.contracts.AnimeRecord` (preferred) or supply a custom
   ``adapter=`` to :class:`core.ingestion_pipeline.ProviderSpec`.
6. Add a unit test under ``tests/unit/animeAPI/``.

Adding a new normalized field
-----------------------------

1. Add the field to :class:`core.contracts.AnimeRecord` (frozen
   dataclass; keep defaults so old adapters keep working).
2. Update :meth:`APICoordinator._legacy_adapter` to project the field.
3. Update :meth:`APICoordinator._record_to_anime` so the legacy
   :class:`classes.Anime` ends up with the new attribute.
4. Add an assertion in
   ``tests/unit/components/test_api_coordinator_pipeline.py`` to lock
   the projection.

Adding a new criteria value to the anime list
---------------------------------------------

1. Extend :data:`core.query_builder.ALLOWED_CRITERIA`.
2. Add the branch to
   :func:`core.query_builder.build_anime_list_query`. Never build SQL
   from raw caller input; reuse the existing pattern that hard-codes
   the SQL fragments.
3. Add an assertion in
   ``tests/unit/core/test_query_builder.py`` for both shape (correct
   ``table`` / ``filter`` / ``sort``) and safety (no caller-controlled
   text in the clause).

Adding a new telemetry series
-----------------------------

1. Decide on a name. Use the existing prefixes (``ingestion.``,
   ``coordinator.``, ``db.``) -- the operations runbook depends on
   them.
2. Increment / record from the component that produces the signal::

      from shared.telemetry import get_telemetry
      get_telemetry().increment("db.queued_write_errors")
      with get_telemetry().time("db.upsert_anime_batch_ms"):
          ...

3. Update :doc:`operations` so operators know what the metric means.
4. Verify with a test that grabs ``get_telemetry().snapshot()`` after
   the operation.

Working with the persistence queue
----------------------------------

The queue is **opt-in**. Default semantics are synchronous so simple
callers do not need to manage a worker thread.

* Synchronous (preferred): call
  :meth:`DatabaseManager.upsert_anime_batch` with a list.
* Async (high-volume): call
  :meth:`DatabaseManager.enable_batched_writes` once, then
  :meth:`DatabaseManager.enqueue_anime` for each record. Call
  :meth:`DatabaseManager.close` (or rely on it being called by the
  composition root) to drain the queue at shutdown.

Common pitfalls
---------------

* **Do not depend on ``initialize()``/``start()``/``stop()``.** All
  three components self-initialize in their ``__init__`` and expose
  ``close()``. The legacy hooks remain only for backward compatibility
  with code that already drives them.
* **Do not interpolate caller input into SQL.** All list SQL goes
  through :func:`core.query_builder.build_anime_list_query`. Use
  parameterized values via ``BaseDB.sql(query, params, save=...)``.
* **Do not hand-roll URL allow-lists.** Use
  :func:`core.security.validate_url`. The download manager already
  does so; future components must too.
* **Do not log raw OAuth payloads.** Pass them through
  :func:`core.security.redact` first.
* **Never persist by calling ``getDatabase().save(...)`` from a
  provider wrapper.** The single allowed path is
  :meth:`DatabaseManager.upsert_anime_batch` (or its queued sibling).

Running the relevant tests
--------------------------

Fast slice covering this pipeline::

   pytest tests/unit/core/ tests/unit/components/ \
          tests/unit/backend/ tests/unit/db_managers/ \
          tests/unit/test_pipeline_refactor.py -q --no-cov

Coverage configuration is in ``pytest.ini``; the default invocation
enforces a global threshold. Use ``--no-cov`` while iterating to keep
runs fast.

Pull-request checklist
----------------------

Before opening a PR that touches this pipeline:

* [ ] Tests under ``tests/unit/core/`` and ``tests/unit/components/``
      cover every new code path.
* [ ] No new ``f"...{user_input}..."`` SQL strings.
* [ ] No new direct calls to ``getDatabase().save(...)`` from
      provider wrappers or download paths.
* [ ] Any new external request is validated by
      :func:`core.security.validate_url`.
* [ ] Any new secret is loaded through
      :func:`core.security.load_secret`.
* [ ] New telemetry series are documented in :doc:`operations`.
* [ ] If you changed a feature flag default, mention it explicitly in
      the PR description -- it is the rollback contract.
