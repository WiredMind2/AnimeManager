Testing Strategy
================

The AnimeManager test suite is split into several slices. Each slice
trades off speed for breadth: the *unit* slice runs in seconds and
covers the bulk of the business logic; the *architecture* slice
guards the layering contract; *performance* and *security* slices
exercise non-functional properties; and integration tests are kept
out of the default invocation so the developer feedback loop stays
fast.

This page is the canonical answer to *"which tests do I run when?"*

Test layout
-----------

::

   tests/
   ├── architecture/                # ADR 0003 / 0005 / 0006 guards
   │   ├── test_layer_boundaries.py
   │   └── test_no_new_multi_inheritance.py
   ├── unit/
   │   ├── backend/                 # AnimeApplicationService + ports
   │   ├── clients/                 # ClientSDK / FastAPI adapter
   │   ├── core/                    # event bus, telemetry, queues, ...
   │   ├── components/              # database / api / download managers
   │   ├── animeAPI/                # provider wrappers
   │   ├── db_managers/             # SQLite / MariaDB / MySQL backends
   │   ├── torrent_managers/        # qBittorrent / Transmission / ...
   │   ├── file_managers/           # local-disk / FTP filesystem
   │   ├── search_engines/          # planner / parser / ranking / ...
   │   └── monolith_decomp/         # characterization tests (ADR 0005)
   ├── performance/                 # benchmark + load suites
   ├── security/                    # input sanitization, query safety
   ├── integration/                 # cross-module flows (slow marker)
   ├── e2e/                         # end-to-end scenarios (slow marker)
   ├── gui/                         # Tk smoke tests (gui marker)
   └── conftest.py                  # shared fixtures and helpers

Default invocation (fast unit slice)
------------------------------------

``pytest.ini`` configures the default invocation. It excludes
``slow`` and runs every other slice. The most common day-to-day
command is:

.. code-block:: bash

   pytest -m "not slow"

This is equivalent to the default ``pytest`` because ``pytest.ini``
already pins ``-m "not slow"`` in ``addopts``. It runs unit,
architecture, performance, security, gui (where available) and any
non-slow integration cases. Use it before every commit.

Architecture tests
------------------

Architecture tests enforce the layer contracts described in
``docs/developer/layer-contracts.rst`` and the inheritance contract
described in ``docs/developer/decomposition-guide.rst``. They are
tagged with the ``architecture`` marker.

* ``tests/architecture/test_layer_boundaries.py`` parses every
  Python file under ``domain``, ``application``, ``ports`` and
  ``clients`` and fails when a forbidden import appears. The
  forbidden sets in that file are the ground truth for which
  modules each layer is allowed to touch.
* ``tests/architecture/test_no_new_multi_inheritance.py`` scans
  every runtime layer and rejects any class that declares more than
  one non-allowlisted base. The legacy allowlist
  (``LEGACY_CLASS_ALLOWLIST``) is intentionally short and frozen.

Run the architecture slice in isolation when you change imports or
class hierarchies:

.. code-block:: bash

   pytest -m architecture

Performance tests
-----------------

Performance benchmarks live under ``tests/performance/``. They are
tagged with the ``performance`` marker and rely on
``pytest-benchmark`` (see the ``[tool:pytest-benchmark]`` block in
``pytest.ini``).

.. code-block:: bash

   pytest -m performance

Two suites are shipped:

* ``tests/performance/test_search_performance.py`` measures the
  search engine throughput end-to-end.
* ``tests/performance/test_performance_benchmarks.py`` collects
  per-component micro-benchmarks (database access patterns, query
  building, telemetry overhead).

The performance slice runs by default because it is fast enough,
but it is the first slice you should isolate when investigating a
regression.

Security tests
--------------

Security tests live under ``tests/security/`` and are tagged with
the ``security`` marker.

.. code-block:: bash

   pytest tests/security
   # or
   pytest -m security

They cover input sanitisation, query construction safety, and the
hardened-MariaDB checks under
``tests/unit/db_managers/test_embedded_mariadb_security.py`` (kept
under ``unit/`` because the checks are static rather than
runtime-driven).

Slow and integration tests
--------------------------

The ``slow`` marker is excluded from ``addopts``. Integration and
end-to-end suites carry that marker (in addition to ``integration``
or ``e2e``) because they spin up real I/O. They are explicitly
opted in:

.. code-block:: bash

   pytest -m slow
   pytest -m "integration and slow"
   pytest -m "e2e and slow"

Do not enable the ``slow`` slice in tight inner-loop runs; reserve
it for CI and pre-release validation.

Coverage gate
-------------

Coverage is wired through ``pytest-cov`` in ``addopts``:

.. code-block:: text

   --cov=. --cov-report=html:htmlcov --cov-report=xml
   --cov-report=term-missing --cov-fail-under=85

The gate is currently **85 %**. During the ports-and-adapters
migration the gate is *waived* in CI: large legacy modules are still
being decomposed and characterized, so coverage numbers fluctuate as
shims are removed. The waiver is intentional, not permanent.

Operational rules while the waiver is in effect:

* New code must ship with tests; the migration is not an excuse for
  untested adapters.
* A pull request must **not** regress coverage. The HTML report
  under ``htmlcov/`` and the ``coverage.xml`` artifact make it easy
  to compare against ``main`` before opening a PR.
* When the migration completes and the legacy hotspots leave the
  allowlist, the waiver will be lifted and the 85 % gate will
  become hard again.

Characterization tests for legacy decomposition
-----------------------------------------------

The directory ``tests/unit/monolith_decomp/`` contains
*characterization tests* — black-box tests that pin the externally
visible behaviour of a legacy class so it can be safely decomposed
into composed services. They are the safety net referenced by ADR
0005 and the decomposition playbook.

Two suites are in place today:

* ``test_legacy_runtime_composition.py`` pins the public attribute
  surface of :class:`backend.adapters.legacy_runtime.LegacyRuntime`
  (``database``, ``api``, ``fm``, ``tm``, ``settings``,
  ``settingsPath``, ``log``, ``setSettings``) and asserts that the
  class no longer inherits from ``Constants`` or ``Getters``.
* ``test_anime_api_inheritance_surface.py`` records the current
  surface of :class:`animeAPI.AnimeAPI` and
  :class:`animeAPI.APIUtils.APIUtils` so a future decomposition can
  prove behaviour parity.

When you start decomposing a new hotspot, the first commit should
add a characterization test for the class as it exists today.
Subsequent commits move behaviour into composed services while
keeping that test green. The architecture test ensures the legacy
inheritance form stays on the allowlist until the characterization
test confirms it is safe to remove.

Quick reference
---------------

.. code-block:: bash

   # Default fast loop (unit + architecture + performance + security)
   pytest

   # Architecture only (after import / class hierarchy changes)
   pytest -m architecture

   # Performance only
   pytest -m performance

   # Security only
   pytest tests/security

   # Slow / integration / e2e (CI, pre-release)
   pytest -m slow
   pytest -m "integration and slow"

   # Coverage HTML report
   pytest --cov=. --cov-report=html:htmlcov
