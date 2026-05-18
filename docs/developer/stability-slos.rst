Stability SLOs and Critical Journeys
=====================================

This page defines measurable stability targets for the metadata refactor
and the user journeys that must remain healthy across every phase.

Critical user journeys
----------------------

1. **Library browse** -- paginated anime list loads from the local DB
   without calling external providers.
2. **Metadata search** -- query with 3+ characters fans out to providers,
   deduplicates, persists through ``DatabaseManager``, and returns results.
3. **Streaming search** -- progressive UI updates per provider batch without
   blocking on the slowest provider.
4. **Startup warm** -- ``fetch_latest`` schedule ingestion completes with
   partial success when individual providers fail.
5. **Anime detail refresh** -- single-anime metadata can be enriched from
   providers without corrupting canonical IDs.

Service level objectives (SLOs)
-------------------------------

.. table:: Refactor stability targets

   ==============================  =========  ======================================
   Metric                          Target     Measurement
   ==============================  =========  ======================================
   Metadata search success rate    >= 95%     ``coordinator.search_errors`` vs searches
   Search p95 latency              <= 25s     ``ingestion.total_ms`` p95 timer
   Startup schedule success        >= 80%     ``startup.job.fetch_latest_anime`` ok rate
   Provider failure isolation      100%       One provider timeout must not abort others
   Architecture boundary violations 0        ``pytest -m architecture``
   Stability gate pass rate        100%       ``python scripts/stability_gate.py``
   ==============================  =========  ======================================

Stability gate
--------------

Every refactor PR must pass::

   python scripts/stability_gate.py

The gate runs:

* Architecture / layer-boundary tests (``pytest -m architecture``)
* Core metadata pipeline unit tests
* API coordinator and ingestion pipeline tests
* Provider contract parity tests

Optional live-provider checks (``RUN_LIVE_ANIMEAPI=1``) are **not** part of
the default gate.

Rollback policy
---------------

* ``new_ingestion_pipeline=false`` is an emergency-only rollback flag.
  It must not be the default in production settings.
* ``db_gateway_writes_only=false`` is for tests and dry-runs only.

See :doc:`operations` for flag wiring and :doc:`api_db_pipeline` for the
canonical ingestion flow.
