# Next.js API Contracts

This document defines the JSON contract used by the Next.js App Router
frontend during and after `/ui` cutover.

## Contract Principles

- Keep Python as the source of truth for domain logic.
- Use JSON endpoints for page data and mutations.
- Keep SSE/WS transport endpoints unchanged for realtime flows.
- Version the UI API via `/ui/api/meta`.

## New Stable JSON Endpoints

All endpoints are provided by `clients/http/app.py`.

### Metadata and capability discovery

- `GET /ui/api/meta`

Response:

```json
{
  "service": "animemanager-http-client-adapter",
  "ui_api_version": "2026-05-18",
  "streams": {
    "library_ws": "/ui/library/ws",
    "downloads_ws": "/ui/downloads/ws",
    "torrent_sse": "/ui/anime/{anime_id}/torrents/stream",
    "logs_sse": "/ui/logs/stream"
  }
}
```

### Library data

- `GET /ui/api/library?q=&filter=DEFAULT&list_start=0&list_stop=50&hide_rated=`
- Returns `{ mode, query, items, has_next, list_start, list_stop, filter }`.
- `mode = "search"` when `q` is non-empty; otherwise `mode = "list"`.

### Anime detail bundle

- `GET /ui/api/anime/{anime_id}/bundle?user_id=1`
- Returns:
  - `anime`
  - `state`
  - `search_terms`
  - `episodes`
  - `relations`
  - `characters`
  - `last_torrent_query`

### Focused anime resources

- `GET /ui/api/anime/{anime_id}/characters`
- `GET /ui/api/anime/{anime_id}/episodes?user_id=1`

### Torrents and downloads

- `GET /ui/api/torrents/search?anime_id=&term=&profile=interactive&limit=200`
- `GET /ui/api/downloads/overview`

### Logs snapshot

- `GET /ui/api/logs?level=INFO&logger=&q=&limit=200&since=0`
- Returns buffered records compatible with the existing logs UI.

### Mutations

- `POST /ui/api/anime/{anime_id}/like` body: `{ "user_id": 1, "liked": true }`
- `POST /ui/api/anime/{anime_id}/tag` body: `{ "user_id": 1, "tag": "WATCHING" }`
- `POST /ui/api/anime/{anime_id}/download` body: `{ "user_id": 1, "url": "...", "hash": "..." }`
- `POST /ui/api/anime/{anime_id}/cancel`

## Realtime Endpoints (Unchanged)

- Library stream websocket: `/ui/library/ws`
- Downloads stream websocket: `/ui/downloads/ws`
- Torrent results SSE: `/ui/anime/{anime_id}/torrents/stream`
- Logs SSE: `/ui/logs/stream`

## Backward Compatibility

- Existing classic JSON endpoints (`/anime/*`, `/animelist`, `/search`, ...)
  remain available.
- Existing server-rendered `/ui/*` pages remain available until cutover.
