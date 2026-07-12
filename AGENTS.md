# AnimeManager — Agent Reference

Comprehensive guide for AI agents and contributors working in this repository.
Read this before making architectural, UI, or runtime changes.

---

## Table of contents

1. [What this project is](#what-this-project-is)
2. [Python environment (required)](#python-environment-required)
3. [Running the application](#running-the-application)
4. [Repository layout](#repository-layout)
5. [Architecture and dependency rules](#architecture-and-dependency-rules)
6. [Composition, SDK, and clients](#composition-sdk-and-clients)
7. [Configuration and settings](#configuration-and-settings)
8. [Database, file, and torrent backends](#database-file-and-torrent-backends)
9. [Downloads and torrent lifecycle](#downloads-and-torrent-lifecycle)
10. [Playback and streaming](#playback-and-streaming)
11. [HTTP API and Next.js proxy](#http-api-and-nextjs-proxy)
12. [UI surfaces](#ui-surfaces)
13. [Testing](#testing)
14. [Adding features (checklist)](#adding-features-checklist)
15. [Gotchas and conventions](#gotchas-and-conventions)
16. [Key file paths](#key-file-paths)

---

## What this project is

AnimeManager is a Python application for managing an anime library:

- Multi-provider metadata (Kitsu, AniList, MyAnimeList, Jikan)
- Torrent search via the bundled `search_engines/` Nova3 framework
- Downloads through qBittorrent, Transmission, or embedded LibTorrent
- Pluggable databases (SQLite, MySQL, embedded MariaDB)
- Multiple front-ends sharing one embedded backend

The codebase follows **ports-and-adapters** architecture. The monolithic `Manager` class is gone; `composition/root.py` wires the graph, and every client talks through `clients/sdk.py`.

**Single entrypoint (ADR 0006):** only [`run.py`](run.py) at the repo root. Mode dispatch lives in [`bootstrap.py`](bootstrap.py).

---

## Python environment (required)

**Always use the project virtualenv.** Do not run the app, tests, or Python scripts with the system interpreter (especially on Windows where system Python may be 3.13 and break optional deps like `qbittorrentapi` / `pkg_resources`).

The repo uses **`.venv`** at the project root.

### Create and install

```powershell
# Windows (PowerShell)
cd c:\Users\willi\Documents\Python\AnimeManager
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

```bash
# Unix
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional editable install: `pip install -e .`

### Invoke Python

| Platform | Activate | Direct (preferred in scripts) |
|----------|----------|------------------------------|
| Windows | `.\.venv\Scripts\activate` | `.\.venv\Scripts\python.exe` |
| Unix | `source .venv/bin/activate` | `.venv/bin/python` |

Use the venv for **all** of: `run.py`, `pytest`, `pip`, one-off scripts, and smoke tests.

### Extra dependencies for HTTP modes

`requirements.txt` does not pin FastAPI/uvicorn. Install when running `web` or `api`:

```powershell
.\.venv\Scripts\pip install uvicorn fastapi
```

`bootstrap.py` checks for these and prints install instructions if missing.

### Optional: LibTorrent backend

Requires a compatible `python-libtorrent` wheel for your Python version and platform. Registered in [`adapters/torrent/__init__.py`](adapters/torrent/__init__.py) only when import succeeds (`LIBTORRENT_AVAILABLE`).

---

## Running the application

### Commands

```powershell
.\.venv\Scripts\python.exe run.py              # default: web mode
.\.venv\Scripts\python.exe run.py web
.\.venv\Scripts\python.exe run.py gui           # Tk desktop
.\.venv\Scripts\python.exe run.py api          # FastAPI only
```

CLI options: `run.py [MODE] [--host HOST] [--port PORT] [--next-port PORT]`

Windows shortcut: [`scripts/run.bat`](scripts/run.bat)

### Modes and ports

| Mode | Command | Processes | Ports |
|------|---------|-----------|-------|
| **web** (default) | `run.py` / `run.py web` | FastAPI (uvicorn) + Next.js dev | Backend **8081**, frontend **3000** |
| **gui** | `run.py gui` | Tk desktop client | No HTTP server by default |
| **api** | `run.py api` | FastAPI only | **8081** (default host `0.0.0.0`) |

### Web mode environment

Set by [`bootstrap.py`](bootstrap.py) when spawning subprocesses:

| Variable | Typical value | Purpose |
|----------|---------------|---------|
| `WEB_FRONTEND_URL` | `http://127.0.0.1:3000` | Backend redirects browsers to Next.js |
| `BACKEND_URL` | `http://127.0.0.1:8081` | Next.js server-side proxy target |
| `NEXT_PUBLIC_APP_URL` | `http://127.0.0.1:3000` | Client-side absolute URLs |
| `PORT` | `3000` | Next.js dev server port |

### First-time Next.js setup

```powershell
cd next-web
npm install
```

Web mode prerequisites (checked by bootstrap):

- `uvicorn` + `fastapi` importable
- `npm` on PATH
- `next-web/node_modules/` exists

### Startup jobs

Every mode (except isolated GUI child processes) kicks off [`StartupJobsService`](application/services/startup_jobs.py) on a background thread via `ClientSDK().kickoff_startup_jobs()`.

Jobs include metadata fetch, status repair, LibTorrent session restore, and torrent reconciliation (see [Downloads](#downloads-and-torrent-lifecycle)).

### Docker (production self-host)

Full-stack Compose (app + Elastic telemetry, 7 services):

```powershell
Copy-Item .env.docker.example .env
docker compose up -d --build
```

See [`docker/README.md`](docker/README.md). LibTorrent runs in a **`torrent`** sidecar; `docker compose restart backend` does not interrupt downloads. UI: http://localhost:3000 — Kibana: http://127.0.0.1:5601.

### URLs (local dev)

| Service | URL |
|---------|-----|
| Next.js (user-facing) | http://127.0.0.1:3000 |
| FastAPI backend | http://127.0.0.1:8081 |
| Next.js → backend proxy | http://127.0.0.1:3000/backend/... |
| Embedded MariaDB (if used) | localhost:**3307** |

---

## Repository layout

The **repo root is the Python package** (ADR 0006). Top-level packages:

| Path | Role |
|------|------|
| [`domain/`](domain/) | Pure entities, DTOs, policies, errors. **No I/O**, no UI imports. |
| [`ports/`](ports/) | `Protocol` interfaces (`ports/interfaces.py`, `inbound/`, `outbound/`). |
| [`application/`](application/) | Use-cases: `AnimeApplicationService`, `DownloadManager`, `DatabaseManager`, `StartupJobsService`, playback (`application/playback/`). |
| [`adapters/`](adapters/) | **Only layer** that talks to external systems: API providers, DB, torrent clients, filesystem, FFmpeg, legacy runtime bridge. |
| [`composition/`](composition/) | Wiring: `build_embedded_facade()` in [`composition/root.py`](composition/root.py). |
| [`shared/`](shared/) | Config (`Constants`, `Getters`, `ConfigProvider`), telemetry, security, utilities. |
| [`clients/`](clients/) | Peer client adapters — all use [`clients/sdk.py`](clients/sdk.py). |
| [`search_engines/`](search_engines/) | Nova3 torrent search framework (used by adapters). |
| [`next-web/`](next-web/) | **Default UI** — Next.js 16 + React 19 (Turbopack default; separate Node project). |
| [`bootstrap.py`](bootstrap.py) | In-package mode dispatcher. |
| [`run.py`](run.py) | Root launcher (args only). |
| [`settings.json`](settings.json) | Default settings template (copied to appdata on first run). |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records 0001–0006. |
| [`tests/`](tests/) | Pytest: unit, integration, architecture, e2e, gui, security. |

**Deleted legacy:** monolithic `Manager`, `windows/`, old `*_managers` packages. Shims in [`shared/config/getters.py`](shared/config/getters.py) redirect old names to `adapters.*`.

---

## Architecture and dependency rules

### Layer flow

```text
run.py → bootstrap.main(mode) → build_embedded_facade()
  → EmbeddedClientFacade → AnimeApplicationService (+ ports)
  → adapters/* → DB, APIs, torrents, filesystem, ffmpeg
```

### Import rules (ADR 0003, enforced by [`tests/architecture/test_layer_boundaries.py`](tests/architecture/test_layer_boundaries.py))

| Layer | May import |
|-------|------------|
| `domain` | stdlib, `domain` only |
| `application` | `domain`, `ports`, `shared` — **not** concrete `adapters` |
| `ports` | `domain`, stdlib |
| `adapters` | ports, external libs |
| `composition` | `adapters`, `application`, `ports`, `shared`, `domain` |
| `clients` | SDK/facade, `application`, `ports`, `shared`, `composition` — **not** `adapters` |

### ADRs (read in order)

| ADR | Title | Essence |
|-----|-------|---------|
| [0001](docs/adr/0001-embedded-runtime-model.md) | Embedded Runtime Model | One in-process backend; HTTP is a **peer client** |
| [0002](docs/adr/0002-application-contracts.md) | Application Contracts First | Use-cases + DTOs; clients use SDK |
| [0003](docs/adr/0003-dependency-rules.md) | Dependency Direction Rules | Strict layer imports |
| [0004](docs/adr/0004-error-model.md) | Unified Error Model | `AnimeManagerError` hierarchy → HTTP status |
| [0005](docs/adr/0005-composition-over-inheritance.md) | Composition Over Inheritance | No new multi-inheritance in runtime modules |
| [0006](docs/adr/0006-package-layout-and-single-entrypoint.md) | Package Layout | Only `run.py` at root; canonical folder layout |

### Error hierarchy ([`domain/errors/`](domain/errors/__init__.py))

`AnimeManagerError` → `NotFoundError`, `ValidationError`, `InfrastructureError`, `UnauthorizedError`.

HTTP mapping in [`clients/http/app.py`](clients/http/app.py): validation→400/422, not-found→404, unauthorized→401, infrastructure→502.

---

## Composition, SDK, and clients

### Wiring ([`composition/root.py`](composition/root.py))

`build_embedded_facade()` constructs:

1. `bootstrap_embedded_deps()` + port adapters (repository, metadata, download, user actions, media library)
2. `FFmpegTranscoderAdapter(max_active_sessions=2, segment_seconds=4)`
3. `PlaybackService` (media library + transcoder)
4. `AnimeApplicationService` (all ports)
5. `StartupJobsService` (API coordinator, DB manager, config, torrent manager, logger, download adapter)
6. Returns `EmbeddedClientFacade`

### Facade ([`composition/facade.py`](composition/facade.py))

Transport-agnostic API: search, list, download, playback sessions, settings, startup jobs.

### SDK ([`clients/sdk.py`](clients/sdk.py))

```python
@lru_cache(maxsize=1)
def _facade():
    return build_embedded_facade()

class ClientSDK:
    # One method per use-case; DTOs serialized via dataclasses.asdict
```

**Rule:** every client (`clients/tk`, `clients/http`, future adapters) uses `ClientSDK` only — never `AnimeApplicationService` or `adapters/*` directly.

### Client packages

| Package | Entry | Notes |
|---------|-------|-------|
| `clients/http/` | `clients.http.app:app` | FastAPI JSON API + legacy `/ui/*` HTMX |
| `clients/tk/` | `clients.tk.run` | Desktop Tk client |
| `clients/sdk.py` | `ClientSDK()` | Shared by all clients |

See [`clients/README.md`](clients/README.md).

---

## Configuration and settings

### File locations

| File | Purpose |
|------|---------|
| Repo template | [`settings.json`](settings.json) |
| Runtime (Windows) | `%APPDATA%\Anime Manager\settings.json` |
| SQLite DB (Windows) | `%APPDATA%\Anime Manager\animeData.db` |

First run copies the repo template via [`shared/config/constants.py`](shared/config/constants.py) (`Constants.checkSettings()`).

### Important settings sections

| Section | Keys | Purpose |
|---------|------|---------|
| `file_managers` | `last_fm_used`, `Local.dataPath` | **Library root** — anime folders live under `<dataPath>/Animes/` |
| `torrent_managers` | `last_tm_used`, credentials, paths | Active torrent client |
| `database_managers` | `last_db_used`, connection params | Active DB backend |
| `UI` | `tagcolors`, `torrentsStateColors`, … | Colors/styling (includes `DELETED`, `COMPLETE`, …) |
| `anime` | API toggles, timeouts | Metadata providers |
| `feature_flags` | e.g. `strict_download_url_validation` | Runtime flags |
| `library_sync` | `promote_watching_on_startup`, `purge_seen_on_startup` | Startup tag promotion and SEEN-library cleanup |
| `playback` | `video_encoder` | HLS transcoding encoder (`auto` picks GPU when available; requires restart) |

**`dataPath` is critical:** empty value blocks file manager init. Torrent managers inherit `dataPath` from the active file manager ([`shared/config/getters.py`](shared/config/getters.py) `getTorrentManager()`).

Settings API: `GET/PATCH /settings` via SDK; Next.js UI at `next-web/app/settings/page.tsx`.

---

## Database, file, and torrent backends

### Database ([`adapters/persistence/`](adapters/persistence/))

Selected by `settings.json` → `database_managers.last_db_used`:

| Key | Implementation |
|-----|----------------|
| `SQLite` | `adapters/persistence/dbManager.py` |
| `MySQL` | `adapters/persistence/mySql.py` |
| `EmbeddedMariaDB` | `adapters/persistence/embeddedMariaDB.py` (bundled server, port **3307**) |

Gateway: [`application/services/database_manager.py`](application/services/database_manager.py).

### Torrent managers ([`adapters/torrent/`](adapters/torrent/))

Selected by `torrent_managers.last_tm_used`:

| Key | Class | Dependency |
|-----|-------|------------|
| `qBittorrent` | `qBittorrent` | `qbittorrent-api` |
| `Transmission` | `Transmission` | `transmission_rpc` |
| `LibTorrent` | `LibTorrent` | `python-libtorrent` (optional) |

**Note:** `adapters/torrent/deluge.py` exists but Deluge is **not registered** in the `managers` dict.

### File managers ([`adapters/file/`](adapters/file/))

`Local` (`LocalFileManager`), `FTP` (`FTPFileManager`). Selected by `file_managers.last_fm_used`.

---

## Downloads and torrent lifecycle

### Orchestrator

[`application/services/download_manager.py`](application/services/download_manager.py) — `DownloadManager`:

- URL validation via [`shared/security`](shared/security/)
- Thread-pool queue (`max_concurrent_downloads=3`)
- Status polling throttled to 0.5s
- Persists torrent metadata via `DatabaseManager`
- Exposed through [`DownloadAdapter`](adapters/torrent/download_adapter.py)

### On-disk layout

Downloads land in:

1. `<dataPath>/Animes/<Sanitized Title> - <anime_id>`
2. Fallback: `<dataPath>/Animes/anime_<anime_id>`

Resolved by `DownloadManager._get_anime_folder()`.

### Database tables

- `torrents`: `hash`, `name`, `trackers`, `save_path`, **`status`**
- `torrentsIndex`: maps `anime_id` → torrent hash

### `torrents.status` values

| Value | Meaning |
|-------|---------|
| *(unset)* | Known torrent, never confirmed complete |
| `complete` | Download reached finished/seeding (progress ≥ 99.9%) |
| `deleted` | Was complete; video files are gone from disk |

### Lifecycle events

| Event | What happens |
|-------|----------------|
| Download finishes | `_maybe_mark_torrent_complete` → `status = complete` |
| Completed torrent, files missing | `reconcile_deleted_torrents` → `status = deleted`, remove from torrent client (**no file delete**) |
| User deletes last episode file | `delete_episode_file` marks completed torrents `deleted` immediately |
| Manual re-download | `_clear_deleted_status_for_redownload` clears `deleted` before queuing |
| LibTorrent restore | Skips `deleted` torrents; deletes stale resume files ([`adapters/torrent/libtorrent.py`](adapters/torrent/libtorrent.py)) |
| Anime detail UI | `status = deleted` → state **DELETED** ([`clients/http/web.py`](clients/http/web.py)) |

### File presence detection

[`application/services/torrent_file_presence.py`](application/services/torrent_file_presence.py) — checks for `.mkv`, `.mp4`, `.avi` under `save_path` or anime folder.

### Startup pipeline ([`application/services/startup_jobs.py`](application/services/startup_jobs.py))

Order:

1. `repair_date_from`
2. `fetch_latest_anime`
3. `update_status`
4. `sync_watching_tags` — optional; promotes `NONE` / `WATCHLIST` to `WATCHING` when local episode files exist ([`library_sync.promote_watching_on_startup`](settings.json))
5. `purge_seen_libraries` — optional; deletes on-disk folders and torrents for `SEEN`-tagged anime ([`library_sync.purge_seen_on_startup`](settings.json)); runs **before** LibTorrent restore
6. `purge_deleted_torrents` — remove resume artifacts for DB-deleted torrents
7. `restore_libtorrent_sessions` — `LibTorrent.ensure_restored()` when active
8. `repair_torrent_index` — backfill missing `torrentsIndex` rows
9. `reconcile_deleted_torrents` — via [`DownloadAdapter.reconcile_deleted_torrents()`](adapters/torrent/download_adapter.py)

Library sync logic lives in [`application/services/library_startup_sync.py`](application/services/library_startup_sync.py).

### Download API

| Method | Path |
|--------|------|
| POST | `/download/{anime_id}` |
| GET | `/download/progress/{anime_id}` |
| POST | `/download/cancel/{anime_id}` |
| GET | `/download/active` |
| GET | `/anime/{anime_id}/library-torrents` |

Legacy UI: `POST /ui/anime/{anime_id}/download`, WebSocket `/ui/downloads/ws`.

---

## Playback and streaming

### Backend ([`application/playback/`](application/playback/))

On-demand **HLS** via FFmpeg:

| Module | Role |
|--------|------|
| `service.py` | Session create/heartbeat/stop, segment resolve, resume |
| `contract.py` | `SEGMENT_SECONDS=4`, TTL 900s |
| `transcode_session.py` | Per-session ffmpeg lifecycle |
| `playlist.py` | Canonical VOD `index.m3u8` |
| `resume.py` | Resume segment anchoring |
| `session_store.py` | Token-based session auth |

Transcoder: [`adapters/media/ffmpeg_transcoder.py`](adapters/media/ffmpeg_transcoder.py) — `max_active_sessions=2`, 4-second segments. Encoder selection lives in [`adapters/media/ffmpeg_encoder.py`](adapters/media/ffmpeg_encoder.py).

**Video encoder** (`settings.json` → `playback.video_encoder`, default `auto`):

| Value | Behavior |
|-------|----------|
| `auto` | Prefer hardware encoders: `h264_nvenc` → `h264_qsv` → `h264_amf` → `h264_mf` → `libx264` |
| `libx264` | Force CPU software encoding |
| `h264_nvenc` / `h264_qsv` / `h264_amf` / `h264_mf` | Force a specific encoder; falls back to `libx264` if unavailable |

Changes take effect after restarting the app (transcoder is wired once in [`composition/root.py`](composition/root.py)). Session `_ffmpeg.log` files record the full ffmpeg command including the resolved encoder.

**Critical:** `SEGMENT_SECONDS=4` must match in [`composition/root.py`](composition/root.py), `PlaybackService`, and `FFmpegTranscoderAdapter`.

### HTTP playback routes ([`clients/http/web.py`](clients/http/web.py))

| Route | Purpose |
|-------|---------|
| `POST /ui/anime/{anime_id}/play` | Create session (JSON for Next.js) |
| `GET /ui/stream/{session_id}/index.m3u8` | HLS manifest |
| `GET /ui/stream/{session_id}/{segment_name}` | TS segment |
| `POST /ui/stream/{session_id}/heartbeat` | Keep-alive |
| `POST /ui/stream/{session_id}/stop` | Teardown |

SDK: `create_playback_session`, `heartbeat_playback_session`, `stop_playback_session`, `resolve_playback_media_path`.

### Frontend ([`next-web/lib/playback/`](next-web/lib/playback/))

| File | Role |
|------|------|
| `use-playback.ts` | React hook: Shaka player, session lifecycle |
| `session-api.ts` | Play/heartbeat/stop API calls |
| `shaka.ts` | Shaka Player configuration |
| `progress.ts` | Watch progress reporting |
| `subtitles.ts` | Subtitle tracks (libass-wasm) |
| `session-guard.ts` | Duplicate teardown prevention |

Watch UI: [`next-web/components/player/WatchView.tsx`](next-web/components/player/WatchView.tsx), [`VideoPlayer.tsx`](next-web/components/player/VideoPlayer.tsx).

Browser calls `/backend/ui/...` → [`next-web/app/backend/[...path]/route.ts`](next-web/app/backend/[...path]/route.ts) → FastAPI. Proxy timeout: **240s** (ffmpeg resume).

---

## HTTP API and Next.js proxy

### FastAPI app

- ASGI target: **`clients.http.app:app`**
- Router: [`clients/http/web.py`](clients/http/web.py) (legacy UI + playback + WebSockets)
- SDK singleton: `get_sdk()` → `ClientSDK()` (patchable in tests)

### JSON API ([`clients/http/app.py`](clients/http/app.py))

| Method | Path |
|--------|------|
| GET | `/` — JSON status or redirect to Next.js |
| GET | `/anime/{anime_id}` |
| GET | `/animelist` |
| GET | `/search` |
| POST | `/download/{anime_id}` |
| GET | `/download/active` |
| GET | `/torrents/search` |
| POST | `/tag/{anime_id}`, `/like/{anime_id}`, `/seen/{anime_id}` |
| GET | `/state/{anime_id}` |
| GET | `/anime/{anime_id}/episode-files` |
| GET | `/anime/{anime_id}/library-torrents` |
| GET/PATCH | `/settings` |
| GET | `/health` — process health from telemetry counters |
| GET | `/metrics` — full telemetry snapshot (LAN-only) |

### Telemetry

Hybrid observability: in-process metrics + log buffer (always on) with optional Sentry/OpenTelemetry export.

| Layer | Path / module |
|-------|----------------|
| Backend metrics | [`shared/telemetry/collector.py`](shared/telemetry/collector.py) — `get_telemetry()` |
| HTTP middleware | [`clients/http/telemetry_middleware.py`](clients/http/telemetry_middleware.py) — `x-request-id`, latency timers |
| Error handlers | [`clients/http/errors.py`](clients/http/errors.py) — unified 400/401/404/502 mapping |
| Client event ingest | `POST /ui/telemetry/events` → `CLIENT` category in [`/logs`](next-web/app/logs/page.tsx) |
| Next.js client | [`next-web/lib/telemetry/`](next-web/lib/telemetry/) — errors, web-vitals, batched POST |
| Optional Sentry | `SENTRY_DSN` / `NEXT_PUBLIC_SENTRY_DSN` → [`adapters/observability/sentry.py`](adapters/observability/sentry.py) |
| Optional OTel | `OTEL_EXPORTER_OTLP_ENDPOINT` → [`adapters/observability/otel.py`](adapters/observability/otel.py) (traces, metrics, logs) |
| Local Kibana stack | [tetrazero-observability](https://github.com/WiredMind2/tetrazero-observability) — shared Elasticsearch + Kibana + EDOT collector |

Environment variables:

| Variable | Purpose |
|----------|---------|
| `TELEMETRY_SLOW_REQUEST_MS` | Backend slow-request log threshold (default 2000) |
| `NEXT_PUBLIC_TELEMETRY_ENABLED` | Browser telemetry on/off (default on) |
| `SENTRY_DSN` | Python Sentry (install `requirements-telemetry.txt`) |
| `SENTRY_TRACES_SAMPLE_RATE` | Transaction sampling (default `0.1`; use `1.0` while verifying) |
| `SENTRY_SEND_DEFAULT_PII` | Include request IP/headers in Sentry events (`true`/`false`) |
| `SENTRY_ENABLE_LOGS` | Forward Python logs to Sentry (default `true` when DSN set) |
| `SENTRY_PROFILE_SESSION_SAMPLE_RATE` | Continuous profiling sample rate (`0` disables) |
| `SENTRY_PROFILE_LIFECYCLE` | Profiling mode when enabled (default `trace`) |
| `NEXT_PUBLIC_SENTRY_DSN` | Next.js Sentry (`@sentry/nextjs`; see `next-web/.env.local.example`) |
| `NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE` | Browser transaction sampling |
| `NEXT_PUBLIC_SENTRY_SEND_DEFAULT_PII` | Browser `sendDefaultPii` |
| `NEXT_PUBLIC_SENTRY_ENABLE_LOGS` | Forward browser logs to Sentry |
| `SENTRY_ORG` / `SENTRY_PROJECT` / `SENTRY_AUTH_TOKEN` | Optional source map upload on `next build` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP HTTP intake (default local: `http://127.0.0.1:4318`) |
| `OTEL_SERVICE_NAME` | Service name in Kibana (`animemanager-http` / `animemanager-next-web`) |
| `OTEL_METRICS_EXPORT_INTERVAL_MS` | Backend collector metrics export interval (default `15000`) |
| `OTEL_LOG_LEVEL` | Minimum log level exported via OTLP (default `INFO`) |

**Local Kibana (dev only):**

```powershell
# Start stack: clone tetrazero-observability and run docker compose up -d
# Kibana: http://127.0.0.1:5601  (elastic / elastic)
```

Install optional deps: `pip install -r requirements-telemetry.txt`. Set `OTEL_EXPORTER_OTLP_ENDPOINT` in `.env` (backend) and `next-web/.env.local` (Next.js server). Sentry remains optional and independent.

Settings template (`telemetry` section in [`settings.json`](settings.json)): `enabled`, `slow_request_ms`, `client_error_reporting`.

### Metric/span emissions

In-process metrics (counters/gauges/timers) flow `TelemetryCollector` → [`telemetry_bridge`](adapters/observability/telemetry_bridge.py) → OTLP metrics → EDOT collector → Elasticsearch `metrics-*.otel-*` (OTel mapping mode: values land in `metrics.<name>` fields; dimensions are baked into the metric name). Manual spans use `shared.telemetry.get_tracer(__name__)` (no-op when opentelemetry is not installed). Key emissions:

- HTTP: `http.requests`, `http.responses.{status}`, `http.errors`, `http.errors.{status}`, `http.errors.{ExceptionClass}`, `http.slow_requests`, `http.request_ms`, `http.route_ms.{method}.{route}`
- DB: `db.commits`, `db.queries`, `db.upserts_committed`, `db.queued_writes_flushed`, `db.queued_write_errors`, `db.upsert_anime_batch_ms`
- Ingestion/coordinator: `ingestion.records_collected`, `ingestion.records_persisted`, `ingestion.failed_providers`, `ingestion.total_ms`, `ingestion.sink_flush_ms`, `coordinator.last_search_records`, `coordinator.last_search_failed`, `coordinator.last_{schedule,season,genre}_records`
- Startup: `startup.total_ms`, `startup.total_jobs`, `startup.failed_jobs`, `startup.job.{name}_{ms,errors,commits,queries}`
- Catalog/writes: `catalog.merge`, `catalog.identity.conflict`, `catalog.enrichment.{merges,lookups}`, `anime_write.source.{source}`, `anime_write.persisted`, `anime_write.errors`, `anime_write.persist_records_ms`
- Downloads: `download.started`, `download.completed`, `download.failed`, `download.active` (gauge), `download.queue_depth` (gauge), `download.enqueue_ms`; span `download.process`
- Torrents: `torrent.active` (gauge), `torrent.restore_count`, `torrent.reconcile_deleted` (emitted from backend via `LibTorrentRemote`/`DownloadManager`; the torrent sidecar has no OTLP)
- Playback: `playback.sessions_created`, `playback.active_sessions` (gauge), `playback.session_create_ms`, `playback.segment_resolve_ms`; spans `playback.create_session`, `playback.resolve_segment`
- FFmpeg: `ffmpeg.transcodes_started`, `ffmpeg.failures`, `ffmpeg.active_sessions` (gauge); span `ffmpeg.transcode`

### Kibana dashboards

Ten dashboards are generated from [`observability/dashboards/build.py`](observability/dashboards/build.py): Overview, HTTP & APM, Client UX, Database, Ingestion, Startup, Playback, Downloads & Torrents, HTTP Errors, Catalog & Writes. Regenerate the bundle with `build.py --offline` (no Kibana needed) and import with `scripts/install-kibana-dashboards.ps1`. See [`observability/README.md`](observability/README.md).

### Legacy web UI

Prefix `/ui/*` — Jinja2 + HTMX in [`clients/http/templates/`](clients/http/templates/). When `WEB_FRONTEND_URL` is set, HTML clients redirect to Next.js.

### Next.js proxy

- Config: [`next-web/lib/config.ts`](next-web/lib/config.ts) — `API_PROXY_PREFIX = "/backend"`, `BACKEND_URL` default `http://127.0.0.1:8081`
- Client helper: [`next-web/lib/api.ts`](next-web/lib/api.ts) — browser uses `/backend/...`; SSR uses direct backend URL

---

## UI surfaces

| Surface | Location | When to use |
|---------|----------|-------------|
| **Next.js (default)** | [`next-web/`](next-web/) | All new UI work unless user says otherwise |
| Legacy HTMX/Jinja | `clients/http/templates/`, `clients/http/static/` | Only when explicitly requested |
| Tk desktop | [`clients/tk/`](clients/tk/) | `run.py gui` or explicit Tk work |

Cursor rule: [`.cursor/rules/default-nextjs-ui.mdc`](.cursor/rules/default-nextjs-ui.mdc)

### Next.js routes ([`next-web/app/`](next-web/app/))

| Route | Page |
|-------|------|
| `/library` | Anime library |
| `/anime/[id]` | Detail (torrents, episodes, player links) |
| `/anime/[id]/watch` | HLS player |
| `/downloads` | Active downloads overview |
| `/torrents` | Global torrent search |
| `/settings` | Settings editor |
| `/offline` | PWA offline fallback |
| `/backend/[...path]` | API proxy (not user-facing) |

---

## Testing

**Always use venv Python:**

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest tests/unit/backend/ -v
.\.venv\Scripts\python.exe -m pytest -m architecture
.\.venv\Scripts\python.exe -m pytest -m ""          # include slow tests
.\.venv\Scripts\python.exe -m pytest tests/unit/clients/   # ignored by default
```

### Config ([`pytest.ini`](pytest.ini))

Default `addopts`:

- `-m "not slow"` — slow tests excluded unless `-m ""`
- `--ignore=tests/unit/clients` — client tests exist but not in default run
- `--cov=.` with **85%** fail-under
- `-n auto` (pytest-xdist parallel)
- Reports: `test-results/report.html`, `htmlcov/`

Coverage **omits** `clients/*` and `search_engines/nova3/*`.

### Test layout

| Directory | Purpose |
|-----------|---------|
| `tests/unit/` | Fast isolated tests (backend, adapters, playback, torrent) |
| `tests/integration/` | Real ffmpeg / libtorrent round-trips |
| `tests/architecture/` | Layer boundaries, root allowlist, no multi-inheritance |
| `tests/e2e/`, `tests/gui/`, `tests/security/` | Specialized suites |

### Patterns

- **Application tests:** inject fakes into `AnimeApplicationService` ports (`tests/unit/backend/`)
- **HTTP tests:** patch `clients.http.app.get_sdk` with `FakeSDK`
- **Integration:** `build_embedded_facade()` or `ClientSDK()` with real ffmpeg

### Next.js tests

```powershell
cd next-web
npm test                              # vitest
npm run test:session-guard
npm run test:playback-smoke           # Playwright smoke script
```

---

## Adding features (checklist)

1. DTO / command in `domain/` or `application/dto/`
2. Method on [`AnimeApplicationService`](application/services/anime_service.py)
3. Port in [`ports/interfaces.py`](ports/interfaces.py) if new boundary
4. Adapter implementation in `adapters/`
5. Wire in [`composition/root.py`](composition/root.py) and [`composition/bootstrap.py`](composition/bootstrap.py)
6. Expose in [`clients/sdk.py`](clients/sdk.py)
7. Client surface: Next.js ([`next-web/lib/api.ts`](next-web/lib/api.ts)) and/or FastAPI route
8. Tests: `tests/unit/application/`, `tests/unit/backend/`

**UI default:** implement in `next-web/`, call backend via `/backend` proxy.

**Do not:** import `adapters` from `clients/`, add new root `__main__.py`, or introduce multi-inheritance in runtime modules (ADR 0005).

---

## Gotchas and conventions

1. **Venv is mandatory** — use `.\.venv\Scripts\python.exe`, not system `python`.
2. **Default mode is `web`** (FastAPI + Next.js), not GUI.
3. **HTTP is a peer client** — not a privileged backend layer (ADR 0001).
4. **FastAPI/uvicorn** are not in `requirements.txt` — install separately for HTTP modes.
5. **Segment cadence lock** — `SEGMENT_SECONDS=4` everywhere in playback stack.
6. **Deluge** — code exists, not wired in torrent `managers` dict.
7. **LibTorrent** — optional; restore/reconcile jobs no-op when manager is not LibTorrent.
8. **pytest ignores `tests/unit/clients`** by default — run explicitly when needed.
9. **README says `venv`** — project actually uses **`.venv`**; prefer `.venv` consistently.
10. **Graceful shutdown** — FastAPI lifespan calls `_shutdown_embedded_background()`; `DownloadManager` uses non-daemon thread pool.
11. **Torrent state colors** — `settings.json` → `UI.torrentsStateColors` includes `DELETED`, `COMPLETE`, `DOWNLOADING`; backend must emit matching state strings.
12. **Watching tag** — `_has_completed_torrent` ignores `DELETED` torrents so library tags stay accurate when files are gone.
13. **Playback API** — still under `/ui/anime/{id}/play`; Next.js proxies via `/backend/ui/...`.
14. **Commits** — only when user explicitly asks; never force-push `main`.
15. **Telemetry** — client errors appear in `/logs` under `CLIENT`; correlate with backend via `x-request-id` response header.

---

## Key file paths

| Purpose | Path |
|---------|------|
| Root launcher | [`run.py`](run.py) |
| Mode dispatcher | [`bootstrap.py`](bootstrap.py) |
| Composition / wiring | [`composition/root.py`](composition/root.py), [`composition/facade.py`](composition/facade.py) |
| Main use-case service | [`application/services/anime_service.py`](application/services/anime_service.py) |
| Download orchestration | [`application/services/download_manager.py`](application/services/download_manager.py) |
| Torrent file presence | [`application/services/torrent_file_presence.py`](application/services/torrent_file_presence.py) |
| DB gateway | [`application/services/database_manager.py`](application/services/database_manager.py) |
| Startup jobs | [`application/services/startup_jobs.py`](application/services/startup_jobs.py) |
| Library startup sync | [`application/services/library_startup_sync.py`](application/services/library_startup_sync.py) |
| Playback service | [`application/playback/service.py`](application/playback/service.py) |
| FFmpeg adapter | [`adapters/media/ffmpeg_transcoder.py`](adapters/media/ffmpeg_transcoder.py) |
| FFmpeg encoder selection | [`adapters/media/ffmpeg_encoder.py`](adapters/media/ffmpeg_encoder.py) |
| Composition bootstrap | [`composition/bootstrap.py`](composition/bootstrap.py) |
| Anime repository adapter | [`adapters/persistence/anime_repository.py`](adapters/persistence/anime_repository.py) |
| User actions adapter | [`adapters/persistence/user_actions_repository.py`](adapters/persistence/user_actions_repository.py) |
| Media library adapter | [`adapters/file/local_media_library.py`](adapters/file/local_media_library.py) |
| Download adapter | [`adapters/torrent/download_adapter.py`](adapters/torrent/download_adapter.py) |
| Metadata adapter | [`adapters/metadata/api_coordinator_adapter.py`](adapters/metadata/api_coordinator_adapter.py) |
| LibTorrent adapter | [`adapters/torrent/libtorrent.py`](adapters/torrent/libtorrent.py) |
| Port interfaces | [`ports/interfaces.py`](ports/interfaces.py) |
| Domain errors | [`domain/errors/__init__.py`](domain/errors/__init__.py) |
| Client SDK | [`clients/sdk.py`](clients/sdk.py) |
| FastAPI app | [`clients/http/app.py`](clients/http/app.py) |
| Legacy HTTP + playback routes | [`clients/http/web.py`](clients/http/web.py) |
| Settings / getters | [`shared/config/constants.py`](shared/config/constants.py), [`shared/config/getters.py`](shared/config/getters.py) |
| Default settings template | [`settings.json`](settings.json) |
| Next.js proxy | [`next-web/app/backend/[...path]/route.ts`](next-web/app/backend/[...path]/route.ts) |
| Next.js API helper | [`next-web/lib/api.ts`](next-web/lib/api.ts) |
| Next.js config | [`next-web/lib/config.ts`](next-web/lib/config.ts) |
| Playback hook | [`next-web/lib/playback/use-playback.ts`](next-web/lib/playback/use-playback.ts) |
| Downloaded torrents table | [`next-web/components/anime/DownloadedEpisodesTable.tsx`](next-web/components/anime/DownloadedEpisodesTable.tsx) |
| Pytest config | [`pytest.ini`](pytest.ini) |
| Dependencies | [`requirements.txt`](requirements.txt) |
| ADR index | [`docs/adr/README.md`](docs/adr/README.md) |
| Architecture tests | [`tests/architecture/test_layer_boundaries.py`](tests/architecture/test_layer_boundaries.py) |
| Cursor UI rule | [`.cursor/rules/default-nextjs-ui.mdc`](.cursor/rules/default-nextjs-ui.mdc) |
