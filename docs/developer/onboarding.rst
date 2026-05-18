Developer Onboarding
====================

Welcome! This guide is the fastest way to get productive with the
AnimeManager codebase after the client/server refactor.

Project overview
----------------

AnimeManager is a Python application for managing an anime
collection. It exposes the same business logic to multiple
front-ends through a ports-and-adapters layout (see
``docs/developer/architecture.rst`` and the ADRs under
``docs/adr/``).

Repository tour
---------------

::

    AnimeManager/
    ├── run.py                  # single root startup script (ADR 0006)
    ├── bootstrap.py            # canonical mode dispatcher
    ├── composition/            # dependency wiring (root.py)
    ├── domain/                 # pure entities/policies/errors (re-exports backend.domain)
    ├── application/            # use-cases, DTOs, services
    ├── ports/                  # Protocol interfaces
    ├── adapters/               # IO/framework integrations
    │   ├── api/                # → animeAPI (re-export)
    │   ├── persistence/        # → db_managers (re-export)
    │   ├── torrent/            # → torrent_managers (re-export)
    │   ├── file/               # → file_managers (re-export)
    │   ├── search/             # → search_engines orchestration
    │   ├── media/              # → media_players (or stubs)
    │   └── legacy/             # ↔ backend.adapters.legacy_runtime
    ├── shared/                 # cross-cutting helpers
    │   ├── config/             # ConfigProvider
    │   ├── telemetry/          # LoggerService
    │   ├── security/           # → core.security
    │   └── utils/              # → general_utils
    ├── backend/                # canonical impl (domain/application/ports/adapters live here too)
    ├── clients/                # peer client adapters
    │   ├── sdk.py              # ClientSDK
    │   ├── tk/                 # desktop Tk client
    │   ├── tk_legacy/          # transitional home for old windows/ views
    │   └── http/               # FastAPI HTTP client
    ├── components/             # legacy services consumed by adapters
    ├── core/                   # low-level helpers (event bus, etc.)
    ├── animeAPI/               # provider wrappers (allowlisted hotspot)
    ├── db_managers/            # SQLite / MySQL / embedded MariaDB
    ├── file_managers/          # local / FTP file system
    ├── torrent_managers/       # qbittorrent / transmission / deluge / libtorrent
    ├── search_engines/         # torrent search framework + vendored nova3
    ├── docs/                   # Sphinx docs + ADRs
    ├── tests/                  # pytest suite (unit, architecture, perf, security)
    ├── __main__.py             # DEPRECATED shim → run.py
    ├── API_server.py           # DEPRECATED shim → clients.http.app
    └── launch/__main__.py      # DEPRECATED shim → run.py

Environment setup
-----------------

1. **Prerequisites**

   * Python 3.10+
   * Git
   * (Recommended) a virtual environment

2. **Clone and install**

   .. code-block:: bash

      git clone https://github.com/WiredMind2/AnimeManager.git
      cd AnimeManager
      python -m venv venv
      # Windows
      .\venv\Scripts\activate
      # Unix
      source venv/bin/activate
      pip install -r requirements.txt

3. **Verify the package imports**

   .. code-block:: bash

      python -c "from bootstrap import main, list_modes; print(sorted(list_modes()))"

4. **Run the test suite**

   .. code-block:: bash

      pytest -m "not slow"
      pytest -m architecture

5. **Run the desktop client**

   .. code-block:: bash

      python run.py
      # equivalent to:
      python run.py gui

6. **Run the HTTP client**

   .. code-block:: bash

      python run.py api --host 0.0.0.0 --port 8081

7. **Run the Next.js web client (new UI)**

   .. code-block:: bash

      cd next-web
      cp .env.example .env.local
      npm install
      npm run dev

   To make Python redirect legacy ``/ui/*`` HTML routes to Next during
   cutover, set ``ANIMEMANAGER_NEXT_UI_URL=http://127.0.0.1:3000`` in
   the API process environment.

Code style
----------

* PEP 8 with a 100-character line length.
* Type-hint every public API.
* Domain code (everything under ``backend/domain``) must remain
  pure: no I/O, no imports from infrastructure plug-ins.
* New cross-layer behavior should be added at the
  :class:`backend.application.service.AnimeApplicationService`
  level, *not* inside client adapters.

Development workflow
--------------------

1. Create a feature branch:

   .. code-block:: bash

      git checkout -b feature/your-feature-name

2. Write tests first whenever possible. The fast unit slice lives
   under ``tests/unit/`` and avoids real I/O.

3. Iterate. Whenever you change a public contract, add or update an
   ADR if the change reflects a deliberate architectural decision.

4. Lint and type-check:

   .. code-block:: bash

      flake8 .
      mypy .

5. Open a pull request describing the user-visible behavior change
   and any ADRs touched.

Common tasks
------------

**Add a new use-case (visible to clients)**

1. Declare DTOs in ``backend/domain/dto.py``.
2. Add a method on
   :class:`backend.application.service.AnimeApplicationService`.
3. Extend the appropriate port in ``backend/ports/interfaces.py``
   when a new infrastructure capability is required.
4. Update the legacy adapter or write a new one under
   ``backend/adapters/``.
5. Bind the new port implementation in
   ``backend/composition.py``.
6. Re-export the method through
   :class:`backend.interfaces.embedded.facade.EmbeddedClientFacade`.
7. Surface it on :class:`clients.sdk.ClientSDK` and add a route /
   widget in the relevant client adapter(s).
8. Unit-test the service with fakes; integration-test the client
   adapter with the SDK monkey-patched.

**Add a new client adapter (e.g. Qt, CLI)**

1. Create ``clients/<name>/`` with an ``__init__.py``.
2. Build a transport layer that only talks to
   :class:`clients.sdk.ClientSDK`.
3. Map domain errors to transport-appropriate notifications.
4. Mirror the test layout used by ``clients/http``.

**Add a new metadata provider, torrent client, or DB backend**

These all live in the plug-in collections under ``animeAPI/``,
``torrent_managers/`` and ``db_managers/`` respectively. Implement
the corresponding base class, register the new entry, and the
existing legacy components will pick it up. No backend changes
required.

**Modify configuration**

Settings live in ``settings.json`` and are loaded by
``constants.Constants`` / ``getters.Getters``. The
``LegacyRuntime`` adapter is the only consumer of those modules; if
you add a new setting, document it in the README and reference the
JSON path from the runtime.

Where to dig next
-----------------

* Read the four ADRs in order (``docs/adr/``).
* Skim the architecture overview
  (``docs/developer/architecture.rst``).
* Browse ``backend/README.md`` and ``clients/README.md`` for
  layer-specific guides.
* Look at the existing tests under ``tests/unit/backend/`` and
  ``tests/unit/clients/`` for patterns to copy.

Welcome aboard.
