# `clients/` — client adapters

Each subpackage of `clients/` is a *peer* user-interface for the same
embedded backend. They all consume the same in-process SDK and share
the same domain/application contracts; only the transport (Tk events,
HTTP requests, …) differs.

> See ADRs [0001](../docs/adr/0001-embedded-runtime-model.md) and
> [0003](../docs/adr/0003-dependency-rules.md) for the rationale.

## Layout

```
clients/
├── sdk.py        # ClientSDK: shared command/query API over the embedded facade
├── tk/           # desktop Tkinter client
└── http/         # FastAPI client (used by web/mobile, served by uvicorn)
```

## The shared SDK (`clients/sdk.py`)

`ClientSDK` is a thin Python class with one method per backend
use-case. It owns the lifetime of the embedded facade via
`functools.lru_cache`, so adapters only pay the construction cost the
first time the SDK is touched (and unit tests can swap the cached
instance to inject fakes).

```python
from AnimeManager.clients.sdk import ClientSDK

sdk = ClientSDK()
response = sdk.search_anime(query="bleach", limit=20)
```

Every client adapter **must** depend on `ClientSDK` (or on the
`EmbeddedClientFacade` it wraps) — never on backend internals like
`AnimeApplicationService` or on infrastructure modules such as
`db_managers`.

## Desktop client (`clients/tk/`)

* `app.py` defines `run()` which builds a minimal Tk window and drives
  the SDK in response to user actions.
* `AnimeManager/__main__.py` and `AnimeManager/launch/__main__.py`
  both call this `run()` to launch the desktop UI.
* The Tk client is intentionally small; rich legacy widgets (modal
  windows, tables, scrollbars) lived under the deleted `windows/`,
  `anime_list_frame.py`, etc. and have been removed. New desktop UI
  should be built on top of the SDK only.

## HTTP client (`clients/http/`)

* `app.py` exposes a FastAPI app named `app` and serves **two peer
  surfaces**:
  * a JSON API (`/anime/*`, `/animelist`, `/search`, `/download/*`,
    `/torrents/*`, `/settings`, ...) for tooling, mobile, and the
    test suite, and
  * a full server-rendered **web UI** mounted under `/ui/*` (Jinja2 +
    HTMX, no Node build chain). Static assets live at
    `/ui/static`. See [`docs/features/web_ui.rst`](../docs/features/web_ui.rst).
* The app uses `get_sdk()` (lazy, `lru_cache`d) so tests can override
  the SDK with `monkeypatch.setattr(http_app, "get_sdk", fake)` and
  cover **both** surfaces in one patch.
* Maps domain errors to HTTP status codes (`NotFoundError → 404`,
  `ValidationError → 422`, `UnauthorizedError → 401`,
  `InfrastructureError → 502`); web routes render a friendly error
  page for 404s and surface validation failures as inline flashes.
* `GET /` returns the JSON service probe for API clients but redirects
  browsers (`Accept: text/html`) to `/ui/library` so the project
  starts with a real UI when you open it in a browser.
* `API_server.py` at the repository root is a backwards-compatible
  shim that re-exports `app`, so existing `uvicorn API_server:app`
  invocations keep working.

## Adding a new client adapter

1. Create `clients/<name>/` with an `__init__.py` that re-exports the
   adapter entry point.
2. Build a transport layer (CLI, Qt, websocket, …) that translates
   transport-specific inputs into `ClientSDK` method calls.
3. Translate domain errors into transport-appropriate signals
   (HTTP statuses, dialog windows, exit codes, …).
4. Write integration tests under `tests/unit/clients/<name>/` that
   exercise the adapter against a fake SDK.

## What clients are not allowed to do

* Import `db_managers`, `animeAPI`, `torrent_managers`,
  `file_managers`, `search_engines` or the legacy `components/`
  package.
* Reach into `backend/adapters` or `backend/composition`.
* Mutate global state in `constants`, `getters` or settings files.

If you find yourself wanting to do any of those, the right fix is to
add a new use-case in `backend/application/service.py` and surface it
through the SDK.
