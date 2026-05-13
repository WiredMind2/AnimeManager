Architecture Overview
=====================

AnimeManager is organised around a small, pure backend and a fleet of
peer client adapters. The shape and the rules that govern it are
captured in six Architecture Decision Records (ADRs); this document
is the narrative companion to those ADRs.

.. seealso::

   * `ADR 0001 — Embedded Runtime Model <../../docs/adr/0001-embedded-runtime-model.md>`_
   * `ADR 0002 — Application Contracts First <../../docs/adr/0002-application-contracts.md>`_
   * `ADR 0003 — Dependency Direction Rules <../../docs/adr/0003-dependency-rules.md>`_
   * `ADR 0004 — Unified Error Model <../../docs/adr/0004-error-model.md>`_
   * `ADR 0005 — Composition Over Inheritance <../../docs/adr/0005-composition-over-inheritance.md>`_
   * `ADR 0006 — Package Layout and Single Entrypoint <../../docs/adr/0006-package-layout-and-single-entrypoint.md>`_

Runtime entrypoint
------------------

A single root-level script, ``run.py``, parses the requested mode
(``gui`` / ``api``) and delegates to :func:`bootstrap.main`. The
remaining ``.py`` files at the repository root are strictly limited to
the packaging/startup essentials (``__init__.py``, ``bootstrap.py``,
``setup.py``, ``sitecustomize.py``). See ADR 0006 for the rule and
``docs/developer/runtime-flows.rst`` for the full call diagram.

Layered structure
-----------------

::

    ┌────────────────────────── clients/ ──────────────────────────┐
    │  clients.tk        clients.http        (future clients)      │
    │                  ▲                                           │
    │                  │ uses ClientSDK                            │
    └──────────────────┼───────────────────────────────────────────┘
                       │
    ┌──────────────────┼───────────────────────────────────────────┐
    │                  │                                           │
    │      EmbeddedClientFacade   (composition.facade)             │
    │                  ▲                                           │
    │      AnimeApplicationService   (application.services)        │
    │                  ▲                                           │
    │       Ports (Protocols)   (ports.interfaces)                 │
    │                  ▲                                           │
    │       Legacy adapters     (adapters.legacy.runtime)          │
    └──────────────────┼───────────────────────────────────────────┘
                       │
    ┌──────────────────┼───────────────────────────────────────────┐
    │ Infrastructure plug-ins (canonical layers only)              │
    │  adapters/api  adapters/persistence  adapters/torrent        │
    │  adapters/file  adapters/search                              │
    │  application/services  (api_coordinator, database_manager,   │
    │                         download_manager, ingestion_pipeline)│
    │  shared/  (base_component, contracts, security, telemetry)   │
    └──────────────────────────────────────────────────────────────┘

Dependency flow goes downward only. Each arrow represents an import
relation that is allowed; everything else is forbidden by ADR 0003
and enforced by tests.

Domain layer (``domain/``)
--------------------------

Pure code: entities, DTOs, policies and the unified error hierarchy.
The domain has zero infrastructure dependencies; nothing in this
layer can import from ``adapters/``, ``clients/`` or any deprecated
namespace (``components``, ``core``, ``animeAPI``, ``db_managers``,
``torrent_managers``, ``file_managers``, ``media_players``, etc.).

* :mod:`domain.entities` – immutable ``AnimeEntity`` /
  ``TorrentEntity`` dataclasses and the ``from_legacy_anime`` helper
  used by adapters during the migration.
* :mod:`domain.dto` – request/response DTOs exchanged between
  the client adapters and the application service.
* :mod:`domain.policies` – pure business policies
  (``derive_status``, ``normalize_search_query``).
* :mod:`domain.errors` – ``AnimeManagerError`` and its
  subclasses (``NotFoundError``, ``ValidationError``,
  ``UnauthorizedError``, ``InfrastructureError``).

Ports (``ports/``)
------------------

``Protocol`` interfaces describing the capabilities the application
needs from infrastructure:

* ``AnimeRepositoryPort`` – local catalog search and list operations.
* ``MetadataProviderPort`` – remote multi-provider search.
* ``DownloadPort`` – torrent orchestration.
* ``UserActionsPort`` – user tagging / state.

Application layer (``application/``)
------------------------------------

``AnimeApplicationService`` (``application.services.anime_service``)
is the single object that exposes use-cases to clients. It depends on
the ports above and the domain layer. Every method:

* validates input via policies,
* delegates I/O to a port,
* translates port exceptions into typed domain errors,
* returns a DTO.

The same package now hosts the legacy bridge orchestrators that
migrated from ``components/`` (``api_coordinator``,
``database_manager``, ``download_manager``) and the
``ingestion_pipeline`` lifted out of the historical ``core/``
namespace. Those bridges hold direct references to
``adapters.legacy`` and ``adapters.persistence`` collaborators and
are explicitly exempted from the application-layer import rule by an
allowlist documented in
:file:`tests/architecture/test_layer_boundaries.py`.

Adapters (``adapters/``)
------------------------

The only layer allowed to import legacy plug-ins. ``adapters.legacy.runtime``
hosts:

* ``LegacyRuntime`` – a tiny composition of ``Constants`` and
  ``Getters`` that initialises the legacy file/torrent/database
  managers without needing the deleted ``Manager`` class.
* ``LegacyAnimeRepositoryAdapter`` – wraps
  ``application.services.database_manager.DatabaseManager`` to
  implement ``AnimeRepositoryPort``.
* ``LegacyMetadataProviderAdapter`` – wraps
  ``application.services.api_coordinator.APICoordinator`` to
  implement ``MetadataProviderPort``.
* ``LegacyDownloadAdapter`` – wraps
  ``application.services.download_manager.DownloadManager`` and the
  torrent managers to implement ``DownloadPort``.
* ``LegacyUserActionsAdapter`` – writes user tag/like rows directly
  on the configured database to implement ``UserActionsPort``.

When a port is eventually backed by a clean infrastructure module the
matching legacy adapter can be deleted; the binding in
``composition.root`` is the single point that has to change.

Embedded facade (``composition.facade``)
----------------------------------------

``EmbeddedClientFacade`` mirrors the public application service
methods. It is the only object client adapters are allowed to hold a
reference to; it lets us layer cross-cutting concerns (telemetry,
auth, rate limiting) without touching individual clients.

Composition root (``composition.root``)
---------------------------------------

``build_embedded_facade()`` is the single function that knows how to
wire every layer. Tests can either call it (for an integration-style
build with the legacy infrastructure) or construct each layer by
hand with fakes for the ports (for unit tests of the application
service).

Clients (``clients/``)
----------------------

Each client adapter is a *peer*: the Tk desktop client, the FastAPI
HTTP client, and any future Qt or CLI client all sit at the same
layer. They consume the embedded facade through
:class:`clients.sdk.ClientSDK` and translate domain errors into
transport-appropriate signals (dialogs, HTTP statuses, etc.).

* :mod:`clients.tk` – modular Tk desktop client (views/presenters/widgets)
  that keeps all backend interaction behind :class:`clients.sdk.ClientSDK`.
* :mod:`clients.http` – FastAPI app exposed by ``clients.http.app``.
* :mod:`clients.sdk` – the shared command/query API.

The SDK now exposes expanded desktop workflows in addition to the
baseline list/search/download primitives:

* settings read/write (for the settings window),
* torrent search orchestration and active download management,
* search-term management,
* relation lookups and explicit user-state readback.

Error model
-----------

ADR 0004 mandates a single error hierarchy:

* Domain code raises ``AnimeManagerError`` subclasses.
* Adapters translate infrastructure exceptions into the same
  hierarchy.
* The HTTP client maps each subclass to an HTTP status code.
* The Tk client surfaces them as messageboxes (current minimal
  client simply logs them; richer mapping is the responsibility of
  future Tk widgets).

Plug-in catalogue
-----------------

The infrastructure plug-ins now live inside ``adapters/`` and
``shared/``. They are *implementation details*: the application
service consumes them only through ports, but they remain the place
where new infrastructure features land.

* ``adapters/api/`` – metadata provider wrappers (Kitsu, AniList,
  MAL, Jikan) used by
  ``application.services.api_coordinator.APICoordinator``.
* ``adapters/persistence/`` – ``BaseDB`` implementations (SQLite,
  MySQL, embedded MariaDB) plus the
  ``adapters.persistence.query_builder`` whitelist and
  ``adapters.persistence.queue`` batching primitive used by
  ``application.services.database_manager.DatabaseManager``.
* ``adapters/file/`` – local-disk / FTP filesystem abstractions.
* ``adapters/torrent/`` – qBittorrent / Transmission / Deluge /
  libtorrent clients.
* ``adapters/search/`` – torrent search orchestration layered on top
  of the bundled ``search_engines/nova3`` plug-ins; the nova3 tree
  remains untouched as a vendored black-box dependency.
* ``application/services/`` – the legacy orchestrators retired from
  the old ``components/`` package: ``DatabaseManager``,
  ``APICoordinator``, ``DownloadManager``, plus the new
  ``IngestionPipeline``.
* ``shared/`` – cross-cutting helpers: ``BaseComponent``,
  ``contracts`` (DTOs), the ``security`` URL/secret utilities, and
  the ``telemetry`` logger and in-process ``TelemetryCollector``
  (previously hosted under ``core/``).

Testing strategy
----------------

The fast unit-test slice covers:

* Application service behavior with fake ports
  (``tests/unit/backend/test_application_service.py``).
* HTTP client adapter wiring with ``TestClient`` and a fake SDK
  (``tests/unit/clients/test_http_adapter.py``).
* Core helpers under ``tests/unit/core/``,
  ``tests/unit/components/``, ``tests/unit/search_engines/`` and the
  per-plug-in suites.

Integration and performance tests are tagged ``slow`` and excluded
from the default ``pytest`` invocation.
