Refactor Phases Status Board
============================

The architecture migration is complete. This document is now a final
closure record for ADR 0005 (composition over inheritance) and ADR 0006
(package layout and entrypoint policy).

Final state
-----------

* Canonical runtime layers are `domain`, `application`, `ports`,
  `composition`, `adapters`, `shared`, and `clients`.
* Deprecated namespace packages were physically removed from the
  repository tree: `backend`, `animeAPI`, `db_managers`,
  `torrent_managers`, `file_managers`, `media_players`, `windows`,
  `launch`, and the transitional `components` and `core` packages.
* The legacy `components/*` orchestrators migrated into
  `application/services/` (`api_coordinator`, `database_manager`,
  `download_manager`).
* The legacy `core/*` package was distributed across the canonical
  layers: `BaseComponent` and `contracts` moved to `shared/`,
  `security` and the in-process telemetry collector were merged into
  `shared/security/` and `shared/telemetry/` respectively, the
  ingestion pipeline moved to `application/services/`, and the
  persistence queue and query builder moved to `adapters/persistence/`.
* Root compatibility shims were removed. Root Python policy is now
  strict: only startup/packaging modules remain (`run.py`,
  `bootstrap.py`, `__init__.py`, `setup.py`, `sitecustomize.py`).
* Legacy runtime multi-inheritance bridges were retired from the
  canonical runtime path. Runtime wiring is composition-only.
* Architecture checks enforce zero tolerance for deprecated namespace
  imports in canonical layers.
* Baseline conversion-test failures were fixed and folded into the
  normal verification gates.

Completed phases
----------------

Phase 0 — Baseline and Guardrails
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Completed. ADRs and architecture test suite are in place and enforced.

Phase 1 — Package Skeleton
~~~~~~~~~~~~~~~~~~~~~~~~~~

Completed. Canonical package layout and `run.py` single-entrypoint model
are in production.

Phase 2 — Monolith Decomposition
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Completed. Runtime hotspots were decomposed to explicit collaborators;
new multi-inheritance is blocked by architecture tests.

Phase 3 — Domain / Application / Ports Lift
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Completed. Canonical implementations live in top-level layered
packages; deprecated compatibility namespaces are removed.

Phase 4 — Adapter Migration
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Completed. Adapter implementations live under `adapters.*`. The
vendored `search_engines/nova3` subtree remains preserved.

Phase 5 — Client and Legacy UI Migration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Completed. Client adapters are under `clients.*`. Deprecated `windows`
compatibility namespace was retired.

Phase 6 — Root Cleanup
~~~~~~~~~~~~~~~~~~~~~~

Completed. Root-level compatibility shims and deprecated wrappers were
removed; strict root allowlist is enforced by tests.

Phase 7 — Documentation
~~~~~~~~~~~~~~~~~~~~~~~

Completed. Documentation now reflects final architecture only.
Refactor Phases Status Board
============================

This document is the long-form status board for the AnimeManager
architecture refactor that started with ADR 0001 and is locked in by
ADRs 0005 (Composition Over Inheritance) and 0006 (Package Layout and
Single Entrypoint). It enumerates every phase, summarises the scope
and deliverables, and records the current status with explicit notes
on what has been deferred and why.

The companion document :doc:`monolith_decomposition_status` tracks the
remaining inheritance hotspots and the decomposition work in progress.

.. contents::
   :local:
   :depth: 1

Phase 0 — Baseline and Guardrails
---------------------------------

Scope
~~~~~

Establish the architectural rules and a measurable baseline before any
code is moved. Without a baseline, later phases cannot detect
regressions; without explicit rules, the refactor drifts.

Deliverables
~~~~~~~~~~~~

* ADR 0005 (`docs/adr/0005-composition-over-inheritance.md`) — bans
  new multi-inheritance in runtime modules and defines the allowlist
  for existing hotspots.
* ADR 0006 (`docs/adr/0006-package-layout-and-single-entrypoint.md`) —
  fixes the target package layout and mandates a single root-level
  startup script.
* Architecture-test marker (``architecture``) wired into
  :file:`pytest.ini` and the corresponding suite under
  ``tests/architecture/``.
* Baseline test counts captured for later comparison:

  * 223 pre-existing tests passing.
  * 4 pre-existing failures in
    ``tests/unit/animeAPI/test_conversion_methods.py``. These failures
    pre-date the refactor and are tracked separately; they are not
    treated as regressions.

Status
~~~~~~

**Done.** Both ADRs are accepted and merged. The architecture suite is
green. The pre-existing test failures are unchanged and remain in
their original module.

Phase 1 — Package Skeleton
--------------------------

Scope
~~~~~

Materialise the ADR 0006 package layout at the repository root so new
code can already be written against the target import paths without
waiting for the (much larger) file relocation.

Deliverables
~~~~~~~~~~~~

* Top-level package skeletons created at the repository root:
  :mod:`composition`, :mod:`domain` (with ``entities``, ``policies``,
  ``errors``, ``services``, ``value_objects`` subpackages),
  :mod:`application` (with ``services``, ``dto``, ``commands``,
  ``queries``, ``use_cases``), :mod:`ports` (with ``inbound`` and
  ``outbound``), :mod:`adapters` (with ``api``, ``persistence``,
  ``search``, ``media``, ``torrent``, ``file``, ``legacy``), and
  :mod:`shared` (with ``config``, ``telemetry``, ``security``,
  ``utils``).
* Single root-level startup script :file:`run.py` and the in-package
  dispatcher :mod:`bootstrap`. ``run.py`` performs argument parsing
  only and delegates to :func:`bootstrap.main`, which dispatches to
  the registered mode handlers (``gui``, ``api``).
* Legacy entrypoints (:file:`__main__.py`, :file:`launch/__main__.py`,
  :file:`API_server.py`) reduced to thin shims that emit
  ``DeprecationWarning`` and forward to :func:`bootstrap.main`.

Status
~~~~~~

**Done.** The skeletons exist, ``run.py`` is the documented entrypoint
in the README and in :doc:`/runbooks/local_dev`, and every legacy
startup path warns on import.

Phase 2 — Monolith Decomposition
--------------------------------

Scope
~~~~~

Break the most damaging multi-inheritance hotspots into composed
collaborators while preserving observable behavior via
characterization tests.

Deliverables
~~~~~~~~~~~~

* :class:`backend.adapters.legacy_runtime.LegacyRuntime` rewritten
  around composition. The Phase 0 class signature was
  ``LegacyRuntime(Constants, Getters)``; the new shape is an outer
  :class:`LegacyRuntime` that holds a private ``_LegacyBackbone``
  (the only place ``Constants``/``Getters`` still meet), a
  :class:`shared.config.ConfigProvider`, and a
  :class:`shared.telemetry.LoggerService`. The deprecated
  multi-inheritance form survives as
  :class:`backend.adapters.legacy_runtime.InheritingLegacyRuntime`,
  which emits a ``DeprecationWarning`` on construction.
* :class:`animeAPI.AnimeAPI` and :class:`animeAPI.APIUtils` placed on
  the explicit allowlist in
  ``tests/architecture/test_no_new_multi_inheritance.py``.
  Characterization tests for both hotspots live in
  ``tests/unit/monolith_decomp/test_anime_api_inheritance_surface.py``
  and pin the public method surface so future decomposition work can
  proceed without breaking callers.
* Characterization tests for the composed :class:`LegacyRuntime` in
  ``tests/unit/monolith_decomp/test_legacy_runtime_composition.py``
  cover delegation, settings persistence, and the deprecation warning
  emitted by :class:`InheritingLegacyRuntime`.

Status
~~~~~~

**Done.** :class:`LegacyRuntime` no longer inherits from
:class:`constants.Constants` or :class:`getters.Getters`. The remaining
allowlisted hotspots (:class:`AnimeAPI`, :class:`APIUtils`) are
covered by characterization tests; their decomposition is tracked in
:doc:`monolith_decomposition_status`.

Phase 3 — Domain / Application / Ports Lift
-------------------------------------------

Scope
~~~~~

Move the canonical implementations of the domain, application and
ports layers from :mod:`backend.domain`, :mod:`backend.application`
and :mod:`backend.ports` to the new top-level :mod:`domain`,
:mod:`application` and :mod:`ports` packages introduced in Phase 1.

Deliverables (originally planned)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Physical relocation of the modules into the new packages.
* Removal of the corresponding ``backend.*`` modules once no caller
  references them.

Status
~~~~~~

**Done.** The Phase 3 physical relocation landed during the
Technical Debt Burn-Down. The canonical implementations now live at:

* :mod:`domain` (with :mod:`domain.dto`, :mod:`domain.entities`,
  :mod:`domain.errors`, :mod:`domain.policies`).
* :mod:`application.services.anime_service` (legacy
  ``backend.application.service`` is a shim).
* :mod:`ports.interfaces` (legacy ``backend.ports.interfaces`` is a
  shim).
* :mod:`composition.facade` and :mod:`composition.root`
  (``build_embedded_facade`` is now sourced from
  :mod:`composition.root`).
* :mod:`adapters.legacy.runtime` (was
  ``backend.adapters.legacy_runtime``).

``backend.*`` survives only as a thin compatibility shim that emits a
``DeprecationWarning`` and re-exports from the new canonical
locations. Architecture tests now forbid new imports from
``backend.*`` outside the shim itself (see
``tests/architecture/test_layer_boundaries.py::test_canonical_layers_do_not_import_deprecated_namespaces``).

Phase 4 — Adapter Migration
---------------------------

Scope
~~~~~

Move the concrete adapter implementations under :mod:`adapters` so
the composition root can wire them without crossing into legacy
top-level packages.

Deliverables (originally planned)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Move :mod:`animeAPI` under :mod:`adapters.api`.
* Move :mod:`db_managers` under :mod:`adapters.persistence`.
* Move :mod:`torrent_managers` under :mod:`adapters.torrent`.
* Move :mod:`file_managers` under :mod:`adapters.file`.
* Move :mod:`media_players` under :mod:`adapters.media`.
* Move :mod:`search_engines` orchestration entrypoints under
  :mod:`adapters.search` (the vendored ``nova3`` plug-ins remain
  untouched).

Status
~~~~~~

**Done.** The Phase 4 physical relocation landed during the
Technical Debt Burn-Down. Concrete adapter implementations now live
under :mod:`adapters`:

* :mod:`adapters.api` (was :mod:`animeAPI`) — providers
  ``AnilistCo``, ``JikanMoe``, ``KitsuIo``, ``MyAnimeListNet``,
  plus ``AnimeAPI`` and ``APIUtils``.
* :mod:`adapters.persistence` (was :mod:`db_managers`) — including
  ``base``, ``dbManager``, ``embeddedMariaDB``, ``mySql``.
* :mod:`adapters.torrent` (was :mod:`torrent_managers`) — including
  ``deluge``, ``libtorrent``, ``qbittorrent``, ``transmission``.
* :mod:`adapters.file` (was :mod:`file_managers`) — including
  ``local_disk`` and ``FTP``.
* :mod:`adapters.search` (was :mod:`search_engines` orchestration
  layer). The vendored ``search_engines/nova3`` plug-ins remain at
  their original path because they are a black-box dependency.
* :mod:`adapters.media` retains the legacy re-export surface;
  ``media_players/`` was empty so nothing physically moved.

Each legacy top-level package (``animeAPI``, ``db_managers``,
``torrent_managers``, ``file_managers``, ``search_engines``) now
contains thin compatibility shims that emit a ``DeprecationWarning``
and re-export the symbols from the new canonical location. New code
MUST import from ``adapters.*``; the architecture suite enforces this
via :func:`test_canonical_layers_do_not_import_deprecated_namespaces`.

Phase 5 — Client and Legacy UI Migration
----------------------------------------

Scope
~~~~~

Make the client adapters self-contained under :mod:`clients` and
retire the historical :mod:`windows` package that held the desktop
Tk views.

Deliverables
~~~~~~~~~~~~

* Modern client adapters consolidated under :mod:`clients`: the SDK
  surface in :mod:`clients.sdk`, the Tk client in :mod:`clients.tk`
  (with its own ``app``), and the FastAPI client in
  :mod:`clients.http` (with ``app``). Each is a peer client per ADR
  0001; none of them know about the others.
* The legacy Tk view package collected at :mod:`clients.tk_legacy`.
  The original :mod:`windows` tree was empty in the current codebase,
  so the new :mod:`clients.tk_legacy` is intentionally empty as well —
  it exists to hold the legacy views once they are extracted from
  other call sites, but there is nothing to relocate right now.
* :mod:`windows` reduced to a deprecation shim that warns on import
  and forwards ``*`` re-exports from :mod:`clients.tk_legacy`.

Status
~~~~~~

**Done.** :mod:`clients.tk_legacy` is in place, :mod:`windows` warns
on import, and the new Tk and HTTP client adapters route through the
:mod:`clients.sdk` facade.

Phase 6 — Root Cleanup
----------------------

Scope
~~~~~

Reduce the repository root to a single sanctioned startup script and
the package marker, in line with ADR 0006's "no new ``.py`` files at
the root" rule.

Deliverables (originally planned)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Relocate :file:`classes.py`, :file:`getters.py`, :file:`constants.py`,
  :file:`logger.py`, :file:`general_utils.py`,
  :file:`dialog_components.py`, :file:`import_manager.py`,
  :file:`sitecustomize.py` into appropriate homes under :mod:`shared`,
  :mod:`domain` and :mod:`composition`.
* Keep :file:`run.py`, :file:`__init__.py` and :file:`bootstrap.py` as
  the only root-level Python modules.

Status
~~~~~~

**Done.** The Phase 6 root cleanup landed during the Technical Debt
Burn-Down. Operational modules were physically moved into their
canonical layered homes; each historical root file now contains only
a thin re-export shim that emits a ``DeprecationWarning``:

* :file:`classes.py` → :mod:`adapters.legacy.legacy_classes`
  (placed under ``adapters/`` because it transitively imports
  ``requests``/``bencoding`` which violate the
  ``test_domain_layer_has_no_forbidden_imports`` policy).
* :file:`getters.py` → :mod:`shared.config.getters`.
* :file:`constants.py` → :mod:`shared.config.constants`.
* :file:`logger.py` → :mod:`shared.telemetry.logger`.
* :file:`general_utils.py` → :mod:`shared.utils.general`.
* :file:`dialog_components.py` → :mod:`clients.tk.dialogs`.
* :file:`import_manager.py` → :mod:`shared.utils.import_manager`.
* :file:`sitecustomize.py` — **kept at root**: Python's auto-import
  mechanism requires ``sitecustomize`` to live somewhere on
  ``sys.path``, and the file is just used to prepend the
  repository-local ``lib/`` directory to ``PATH`` for bundled native
  binaries.

A new architecture test,
``tests/architecture/test_root_allowlist.py``, locks the boundary by
asserting that the repository root only contains files in the
``ROOT_REQUIRED`` allowlist. ``ROOT_SHIMS`` is intentionally empty
after the Root Hygiene cleanup: every previous shim was either
deleted outright or migrated to its canonical layered home.

Phase 7 — Docs
--------------

Scope
~~~~~

Produce the long-form documentation suite that accompanies the
refactor: developer guides, runbooks, migration status, ADR series
and API reference pages.

Deliverables
~~~~~~~~~~~~

* :doc:`/developer/architecture` — long-form architecture overview.
* :doc:`/developer/operations` — operational concerns (logging,
  configuration, deployment).
* :doc:`/developer/onboarding` — new-contributor walkthrough.
* :doc:`/developer/contributing_pipeline` — guide for the API/DB
  ingestion pipeline.
* Runbooks under ``docs/runbooks/``: :doc:`/runbooks/local_dev` and
  :doc:`/runbooks/release_build`.
* Migration status under ``docs/migration/``:
  :doc:`refactor_phases` (this document) and
  :doc:`monolith_decomposition_status`.
* API reference under ``docs/api/``: :doc:`/api/domain`,
  :doc:`/api/application`, :doc:`/api/ports`, :doc:`/api/adapters`,
  :doc:`/api/shared`, :doc:`/api/composition`, plus the legacy
  :doc:`/api/backend`, :doc:`/api/clients`, :doc:`/api/core` and
  :doc:`/api/classes` pages.
* ADR series updated through 0006, including the new
  ``docs/adr/README.md`` index.

Status
~~~~~~

**Done.** This documentation suite is the deliverable for Phase 7.
Subsequent phases will only edit existing pages; the structure is
considered stable until the Phase 3, 4 and 6 relocations land, at
which point the API reference will be regenerated against the new
module locations.
