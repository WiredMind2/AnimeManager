Local Development Runbook
=========================

This runbook describes how to bring up an AnimeManager development
environment from a fresh clone, how to run the application in each of
its supported modes, how to execute the test suites, and how to build
the Sphinx documentation locally. It is the operational counterpart of
the architecture overview in :doc:`/developer/architecture` and ADR
0006 (Package Layout and Single Entrypoint).

The audience is a contributor working on the codebase on their own
machine; for packaged release builds see :doc:`release_build`.

Prerequisites
-------------

* Python 3.10 or newer. The codebase relies on
  ``from __future__ import annotations`` syntax and on PEP 604 union
  types in a number of modules; older interpreters will fail at import
  time.
* A working C/C++ toolchain only if you intend to install
  ``python-libtorrent`` for the libtorrent torrent backend (see the
  "Common failures" section).
* Git, for cloning the repository and for the architecture tests that
  inspect the working tree.
* A virtual environment manager. The project ships a
  ``.\\venv\\Scripts\\activate`` invocation in :file:`build_pyinstaller.bat`,
  so a ``venv``-based environment is the default. ``virtualenv`` and
  ``conda`` also work as long as the active interpreter is Python 3.10+.

Bootstrap the environment
-------------------------

The repository root is the package; do not move sources into a
``src/`` subdirectory. The recommended sequence is:

.. code-block:: powershell

   git clone https://github.com/WiredMind2/AnimeManager.git
   cd AnimeManager
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt

On POSIX shells the activation command is ``source venv/bin/activate``
instead. The requirements file pins the runtime libraries plus the
development tools (``pytest``, ``pytest-cov``, ``pytest-xdist``,
``pytest-html``, ``sphinx``, ``sphinx-rtd-theme``, ``flake8``,
``mypy``, ``black``, ``isort``); installing it once is sufficient to
run every workflow described below.

Editable install (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For tooling that resolves the package via metadata (some IDEs, some
type checkers) you can additionally run:

.. code-block:: powershell

   pip install -e .

This wires :file:`setup.py` into the active environment so the
top-level ``AnimeManager`` import name resolves regardless of the
current working directory.

Running the application
-----------------------

ADR 0006 mandates a single root-level startup script,
:file:`run.py`. All execution flows through it:

.. code-block:: powershell

   python run.py            # default: gui (Tk client adapter)
   python run.py gui        # explicit form
   python run.py api        # FastAPI / uvicorn HTTP client adapter
   python run.py api --host 0.0.0.0 --port 8081

``run.py`` performs argument parsing only and delegates to
:func:`bootstrap.main`, which dispatches to the requested mode handler
in ``_MODES``. New transports register there; they do not get their
own ``__main__.py``.

The legacy entrypoints (``python -m AnimeManager`` via the root
:file:`__main__.py`, ``python -m launch`` via :file:`launch/__main__.py`,
and ``API_server.py``) still work but emit ``DeprecationWarning``.
Treat any such warning as a TODO to update the caller.

Mode semantics
~~~~~~~~~~~~~~

* ``gui`` builds the embedded backend via
  :func:`composition.root.build_embedded_facade` and launches the Tk
  client adapter from :mod:`clients.tk`. ``multiprocessing.freeze_support()``
  is called for Windows-compatible subprocess spawning; child processes
  short-circuit immediately so only the main process drives the UI.
* ``api`` imports :mod:`clients.http.app` and runs it under uvicorn.
  The HTTP client is a peer of the Tk client per ADR 0001, not a
  privileged backend layer.

Running the tests
-----------------

Tests live under ``tests/`` and are split by purpose:

.. code-block:: powershell

   pytest -m "not slow"                            # fast unit slice (default)
   pytest -m architecture                          # layer-boundary tests
   pytest -m slow                                  # integration / perf
   pytest tests/unit/monolith_decomp               # specific subtree
   pytest tests/unit/backend/test_application_service.py
   pytest -k "test_legacy_runtime_delegates"       # by name

:file:`pytest.ini` configures ``--cov=.``, an HTML coverage report at
``htmlcov/``, a JUnit XML report under ``test-results/``, parallel
execution via ``-n auto`` (``pytest-xdist``), and a coverage failure
floor of 85 percent. The default ``addopts`` also passes
``-m "not slow"`` so plain ``pytest`` already skips integration and
performance tests; use the explicit marker invocations above when you
need the broader suite.

Architecture tests
~~~~~~~~~~~~~~~~~~

The ``architecture`` marker covers the boundary rules established in
ADRs 0003, 0005 and 0006:

* Forbidden import edges across layers.
* The "no new multi-inheritance" rule (allowlist enforced in
  ``tests/architecture/test_no_new_multi_inheritance.py``).
* The "no new root-level ``.py`` files" rule.

Run them as a smoke check before pushing:

.. code-block:: powershell

   pytest -m architecture

Characterization tests for the allowlisted hotspots live under
``tests/unit/monolith_decomp/`` (see
:doc:`/migration/monolith_decomposition_status`).

Building the documentation
--------------------------

The Sphinx source tree lives under ``docs/``. Build it with:

.. code-block:: powershell

   python -m sphinx -b html docs docs/_build/html

The output is rendered into ``docs/_build/html``; open
``index.html`` in a browser to validate the new content. ``conf.py``
enables ``sphinx.ext.autodoc`` plus ``sphinx.ext.napoleon`` so the new
API reference pages under :doc:`/api/domain`, :doc:`/api/application`,
:doc:`/api/ports`, :doc:`/api/adapters`, :doc:`/api/shared` and
:doc:`/api/composition` pull docstrings from the runtime modules.

When writing or editing pages, prefer the long-form prose style used in
:doc:`/developer/architecture`: ``code-block::`` blocks, ``:mod:`` /
``:class:`` cross references, and explicit ADR links.

Common failures
---------------

The development environment can fail in a handful of recognisable
ways. Each entry below names the symptom, the root cause, and the
canonical fix.

Missing FastAPI / uvicorn when running the HTTP mode
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Symptom: ``python run.py api`` exits with
``ERROR: 'api' mode requires uvicorn. Install with: pip install uvicorn
fastapi``, or with an ``ImportError`` on :mod:`clients.http.app`.

Cause: :func:`bootstrap._run_api` imports :mod:`uvicorn` and
:mod:`clients.http.app` lazily. ``fastapi`` and ``uvicorn`` are not
listed in :file:`requirements.txt` because the desktop developer
workflow does not need them.

Fix:

.. code-block:: powershell

   pip install fastapi uvicorn

Missing libtorrent for the libtorrent torrent backend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Symptom: an ``ImportError`` for ``libtorrent`` (or
``python-libtorrent``) when :mod:`torrent_managers` initialises the
libtorrent client. The default torrent backend in :file:`settings.json`
is one of qBittorrent / Transmission / Deluge, but switching to
``libtorrent`` exposes this dependency.

Cause: ``libtorrent`` is a C++ binding that is not installable through
``pip`` on every platform; on Windows it usually requires a prebuilt
wheel or the bundled installer.

Fix: keep the default torrent backend during development, or install a
working ``libtorrent`` Python binding for your platform before
selecting it in :file:`settings.json`.

``settings.json`` path missing or unreadable
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Symptom: :class:`constants.Constants` fails to load configuration,
:class:`shared.config.ConfigProvider` raises ``RuntimeError("settings
path not configured")``, or :meth:`LegacyRuntime.setSettings` cannot
persist updates.

Cause: ``Constants`` builds the settings path from the platform
appdata directory. If that directory is unwritable (sandboxed
environments, CI containers) the runtime sees an empty path string.

Fix: ensure :file:`settings.json` at the repo root is readable, or
override ``ANIMEMANAGER_BOOTSTRAP``-aware environment variables and
re-run the bootstrap. For test runs, write a fixture file and point
:class:`ConfigProvider` at it; the characterization test
``test_legacy_runtime_set_settings_persists_to_disk`` shows the
pattern.

``ModuleNotFoundError`` for the top-level packages
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Symptom: ``ModuleNotFoundError: No module named 'composition'`` (or
``domain`` / ``application`` / ``ports`` / ``adapters`` / ``shared``).

Cause: the repository root is the package, so the *parent* of
:file:`run.py` has to be on :data:`sys.path`. Running
``python run.py`` from the repo root works because
:func:`run._ensure_package_path` inserts the directory automatically;
running it from elsewhere does not.

Fix: invoke ``python run.py`` from the repository root, or add the
repo root to :data:`PYTHONPATH` before running ad-hoc scripts.

DeprecationWarnings during normal use
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Symptom: importing :mod:`API_server`, running ``python -m AnimeManager``
or ``python -m launch``, or constructing
:class:`backend.adapters.legacy_runtime.InheritingLegacyRuntime`
emits a ``DeprecationWarning``.

Cause: these are intentional. Per ADR 0006 every legacy startup path
and per ADR 0005 every multi-inheritance hotspot is wrapped in a shim
that warns on use.

Fix: migrate the caller. ``run.py`` replaces every legacy startup
script; :class:`LegacyRuntime` replaces
:class:`InheritingLegacyRuntime`. The warnings are suppressed during
pytest runs via :file:`pytest.ini` (``filterwarnings``) so the test
suite is not noisy.

Coverage failure floor
~~~~~~~~~~~~~~~~~~~~~~

Symptom: pytest exits non-zero with
``Coverage failure: total of N is less than fail-under=85``.

Cause: :file:`pytest.ini` enforces ``--cov-fail-under=85``. A new
module introduced without tests, or a stale ``.coverage`` file from a
previous run, both trigger this.

Fix: add tests for the new module, or temporarily relax the threshold
locally via ``--cov-fail-under=0`` while iterating (never commit a
relaxed value). Delete :file:`.coverage` and rerun if you suspect a
stale data file.
