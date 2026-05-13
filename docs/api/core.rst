Core Module (moved)
===================

.. deprecated:: 2026
   The historical ``core`` package was distributed across the canonical
   layers by the Root Hygiene cleanup. This page is retained as a
   redirector so deep-links and downstream documentation keep working.

The infrastructure that previously lived under ``core`` is now hosted
by the canonical layers:

* :mod:`shared.base_component` — ``BaseComponent``
* :mod:`shared.contracts` — typed DTOs (``AnimeRecord``,
  ``IngestionResult``, ``ProviderName``, ``RelationRecord``).
* :mod:`shared.security` — URL validation, secret loading, log
  redaction.
* :mod:`shared.telemetry` — :class:`Logger` plus the in-process
  :class:`TelemetryCollector` (formerly ``core.telemetry``).
* :mod:`adapters.persistence.query_builder` — whitelisted anime-list
  query construction.
* :mod:`adapters.persistence.queue` — bounded batched
  :class:`PersistenceQueue`.
* :mod:`application.services.ingestion_pipeline` — bounded
  fan-out :class:`IngestionPipeline` and :class:`ProviderSpec`.

Base Component
--------------

.. automodule:: shared.base_component
   :members:
   :undoc-members:
   :show-inheritance:

Typed Contracts
---------------

.. automodule:: shared.contracts
   :members:
   :undoc-members:
   :show-inheritance:

Security
--------

.. automodule:: shared.security.utils
   :members:
   :undoc-members:
   :show-inheritance:

Telemetry Collector
-------------------

.. automodule:: shared.telemetry.collector
   :members:
   :undoc-members:
   :show-inheritance:

Query Builder
-------------

.. automodule:: adapters.persistence.query_builder
   :members:
   :undoc-members:
   :show-inheritance:

Persistence Queue
-----------------

.. automodule:: adapters.persistence.queue
   :members:
   :undoc-members:
   :show-inheritance:

Ingestion Pipeline
------------------

.. automodule:: application.services.ingestion_pipeline
   :members:
   :undoc-members:
   :show-inheritance:
