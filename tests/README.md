# AnimeManager Test Suite

This directory contains the pytest-based test suite for AnimeManager.
The suite is split into fast unit tests (default), and slower
integration / performance / security suites that are only run on
demand.

## Layout

```
tests/
├── conftest.py                     # shared fixtures (temp dir, mock SQLite DB)
├── base_test_framework.py          # base classes for E2E/GUI/perf tests
├── unit/                           # fast, isolated unit tests
│   ├── backend/                    # AnimeApplicationService + fakes
│   ├── clients/                    # HTTP client adapter (TestClient + fake SDK)
│   ├── components/                 # APICoordinator pipeline
│   ├── core/                       # contracts, query builder, telemetry, …
│   ├── animeAPI/                   # provider wrappers
│   ├── db_managers/                # SQLite end-to-end checks
│   ├── file_managers/              # local-disk adapter
│   ├── search_engines/             # planner, parser, dedupe, worker, …
│   ├── torrent_managers/           # qbittorrent / transmission / deluge / libtorrent
│   ├── test_classes.py             # domain dataclasses
│   ├── test_constants.py           # constants module
│   ├── test_getters.py             # legacy Getters helpers
│   ├── test_pipeline_refactor.py   # cross-cutting wiring assertions
│   └── test_utils.py               # general_utils helpers
├── performance/                    # benchmarks (slow)
├── security/                       # security regression tests
├── fixtures/                       # shared test data
├── test_e2e_workflows.py           # async E2E flows (slow)
├── test_documentation.py           # doctest harness
├── security_test.py                # standalone security checks
└── test_config.py                  # test-only configuration values
```

The legacy `Manager` monolith has been removed; consequently there is
no `tests/unit/test_animeManager.py` anymore and `tests/conftest.py`
no longer ships a `manager` fixture. Tests against business logic
should drive the embedded backend through one of:

* `from AnimeManager.backend import build_embedded_facade` (full
  integration build), or
* hand-rolled fakes for the ports under
  `AnimeManager.backend.ports.interfaces` (preferred for unit tests).

## Running tests

```bash
# Default fast slice (excludes anything tagged `slow`):
pytest

# Full suite including integration / performance:
pytest -m ""

# A single test:
pytest tests/unit/backend/test_application_service.py -v

# With coverage:
pytest --cov=. --cov-report=term-missing
```

Markers are defined in `pytest.ini`; the default `addopts` already
sets `-m "not slow"`.

## Patterns to follow

* **Unit tests for the application service** — instantiate
  `AnimeApplicationService` directly and inject fakes for the four
  ports. See `tests/unit/backend/test_application_service.py` for
  examples.
* **Client adapter tests** — patch
  `clients.http.app.get_sdk` (or the equivalent for the Tk client)
  with a fake `ClientSDK` to keep the adapter exercised end-to-end
  without spinning up the legacy infrastructure.
* **Plug-in tests** — every base class under `animeAPI/`,
  `torrent_managers/`, `file_managers/` and `db_managers/` has a
  matching `tests/unit/<plugin>/base_*_tests.py` that concrete
  implementations should reuse.

## What lives outside of `tests/`

* `pytest.ini` — pytest configuration (markers, default addopts,
  coverage thresholds).
* `pyproject.toml` — additional tool config (mypy, black, etc.).
* `.coveragerc` settings inline in `pytest.ini`.
