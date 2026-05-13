# AnimeManager

[![Documentation Status](https://readthedocs.org/projects/animemanager/badge/?version=latest)](https://animemanager.readthedocs.io/en/latest/?badge=latest)

AnimeManager is a Python application for managing an anime collection.
It searches multiple anime metadata providers, drives torrent downloads
across several torrent clients, and exposes the same business logic to
multiple front-ends (a desktop Tk client today, an HTTP/web client, and
any additional client adapter you wire up).

The codebase follows a strictly layered ports-and-adapters architecture
captured in the [ADR series](docs/adr/README.md). The latest decisions
(ADRs **0005 — Composition Over Inheritance** and **0006 — Package
Layout and Single Entrypoint**) lock the runtime around a single root
launcher (`run.py`) and ban new multi-inheritance in runtime modules.
The classic monolithic `Manager` class has been removed; the embedded
backend is now the single source of truth for business logic.

## High-level architecture

```text
run.py  ─►  bootstrap.main(mode)  ─►  composition root  ─►  application  ─►  domain
                                          │                  │
                                          ▼                  ▼
                                     adapters/*           ports/*
                                          │
                                          ▼
                                external systems (API, DB, FS, torrents)
```

Top-level packages (all inside the repo-root package):

* **`domain/`** — pure entities, DTOs, policies and the unified error
  hierarchy. No I/O, no UI imports.
* **`ports/`** — `Protocol` interfaces consumed by the application
  layer (repository, metadata provider, downloader, user actions).
* **`application/`** — `AnimeApplicationService` orchestrates
  use-cases against those ports and emits DTOs.
* **`adapters/`** — concrete IO/framework integrations. The only
  layer allowed to talk to external systems.
* **`composition/`** — `build_embedded_facade()` wires every adapter
  into its port. The only place allowed to import both `application/`
  and `adapters/`.
* **`shared/`** — cross-cutting technical helpers (`ConfigProvider`,
  `LoggerService`, security, generic utilities). No feature logic.
* **`clients/`** — peer client adapters:
  * **`clients/sdk.py`** — thin command/query SDK shared by every
    adapter; lazily instantiates the embedded facade.
* **`clients/tk`** — desktop Tk client (modular views/presenters/widgets).
  * **`clients/http`** — FastAPI client treated as a peer of the
    desktop client, not a privileged backend.
* **`bootstrap.py`** — single in-package entrypoint; dispatches to
  GUI / API / future modes.
* **`run.py`** — the only root-level startup script.

See [`docs/developer/architecture.rst`](docs/developer/architecture.rst)
for the long-form description and [`clients/README.md`](clients/README.md)
for client-adapter guidance.

## Features

* Multi-provider anime metadata (Kitsu, AniList, MyAnimeList, Jikan).
* Torrent search via the bundled
  [`search_engines/`](search_engines/README.md) framework.
* Torrent download across qBittorrent, Transmission, Deluge and
  libtorrent.
* Pluggable database backends (SQLite, MySQL, embedded MariaDB).
* HTTP API exposed via FastAPI (`clients.http.app`) for web/mobile
  clients.

## Installation

### From source

```bash
git clone https://github.com/WiredMind2/AnimeManager.git
cd AnimeManager
python -m venv venv
# Windows
.\venv\Scripts\activate
# Unix
source venv/bin/activate
pip install -r requirements.txt
```

### Running the desktop client

```bash
python run.py
# equivalent to:
python run.py gui
```

`run.py` is the single root-level startup script (ADR 0006). It parses
`mode` plus optional `--host`/`--port` and delegates to
`bootstrap.main`.

### Running the HTTP client (JSON API + web UI)

```bash
python run.py api --host 0.0.0.0 --port 8081
```

This launches uvicorn against the canonical ASGI target
`clients.http.app:app`. The same process serves two peer surfaces:

* the **JSON API** at `/anime/*`, `/animelist`, `/search`,
  `/download/*`, `/torrents/*`, `/settings`, etc.
* the **web UI** at `/ui/*` — a server-rendered (Jinja2 + HTMX) admin
  interface with the same feature surface as the desktop client:
  browser/search/filter, anime detail with like/tag/seen + search-term
  manager, torrent search, live downloads view, and a JSON-backed
  settings editor.

Browsers hitting `/` are redirected to `/ui/library`; API tooling
still receives the JSON status payload at `/`. See
[`docs/features/web_ui.rst`](docs/features/web_ui.rst) for the full
route map and design notes.

### Convenience launcher (Windows)

```bash
scripts\run.bat
```

This is a thin wrapper around `python run.py %*` for contributors who
prefer a one-click launcher.

## Configuration

Settings live in `settings.json` (managed by `shared.config.constants.Constants`
and `shared.config.getters.Getters`). Top-level sections:

* `UI` — colors, file markers, tag styles.
* `anime` — per-provider knobs (API toggles, timeouts, limits).
* `database_managers` — connection settings for SQLite/MySQL/MariaDB.
* `file_managers` — local/FTP roots.
* `torrent_managers` — qBittorrent/Transmission/Deluge/libtorrent
  credentials and download paths.

The legacy `media_players` and `phone_sync` sections are no longer
read by the application — they used to feed the deleted media-playback
and mobile-server features.

## Documentation

The Sphinx documentation under `docs/` is the canonical reference.
Build it locally with:

```bash
python -m sphinx -b html docs docs/_build/html
```

Entry points:

* [Documentation index](docs/index.rst) — top-level table of contents.
* [Architecture overview](docs/developer/architecture.rst) and
  [layer contracts](docs/developer/layer-contracts.rst).
* [Runtime flows](docs/developer/runtime-flows.rst) —
  `run.py` → `bootstrap` → composition → application.
* [Inheritance-to-composition playbook](docs/developer/decomposition-guide.rst).
* [Testing strategy](docs/developer/testing.rst) and
  [extension points](docs/developer/extension-points.rst).
* Feature guides under `docs/features/` (anime metadata, search,
  downloads, persistence, configuration, media playback).
* Runbooks under `docs/runbooks/` (`local_dev`, `release_build`).
* Migration status under `docs/migration/` (`refactor_phases`,
  `monolith_decomposition_status`).
* [Architecture Decision Records](docs/adr/README.md) — read 0001
  through 0006 in order.
* Module-level: [search engines](search_engines/README.md).
* Tk parity map: [Tk UI feature guide](docs/features/tk_ui.rst).

## Development

### Tests

```bash
# Fast unit suite (default)
pytest -m "not slow"

# Architecture / layer-boundary checks
pytest -m architecture

# Full suite including slow / integration tests
pytest
```

The fast unit-test slice covers the backend service, the HTTP client
adapter, and the core ingestion/search pipelines. Architecture tests
under `tests/architecture/` statically verify layer boundaries and the
no-new-multi-inheritance rule (ADRs 0003 / 0005 / 0006).

### Lint / formatting

```bash
flake8 .
mypy .
```

### Contributing a new client adapter

1. Implement the new transport (CLI, Qt, websocket, …) under
   `clients/<name>/`.
2. Have it depend only on `clients.sdk.ClientSDK`.
3. Mirror the patterns used by `clients/tk` and `clients/http`.

### Contributing a new use-case

1. Define DTOs in `domain/dto.py`.
2. Add a method on `AnimeApplicationService` in
   `application/services/anime_service.py`.
3. Extend the matching port in `ports/interfaces.py` if a new
   capability is required.
4. Wire the adapter in `adapters/legacy/runtime.py` and update
   `composition/root.py`.
5. Surface the use-case through `clients/sdk.py` and any client
   adapters that need it.
6. Cover the service with unit tests under
   `tests/unit/application/` and the client adapter (if any) under
   `tests/unit/clients/`.

## License

This project is open source. See `LICENSE` for details.

## Disclaimer

This application is intended for personal use. Respect the terms of
service of every API and tracker that you query.
