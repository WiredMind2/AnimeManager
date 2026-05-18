# Next.js Migration UI Inventory

This document catalogs the current `/ui/*` surface so the Next.js
App Router frontend can replace it with parity.

## Current UI Pages

| Route | Current template | Notes |
| --- | --- | --- |
| `/ui/library` | `clients/http/templates/library.html` | List/search page; websocket streaming for `q` queries |
| `/ui/anime/{anime_id}` | `clients/http/templates/anime_detail.html` | Main detail page; HTMX partial swaps and torrent SSE panel |
| `/ui/anime/{anime_id}/characters` | `clients/http/templates/anime_characters.html` | Character tab content |
| `/ui/anime/{anime_id}/watch` | `clients/http/templates/watch_episode.html` | Episode player page; playback session APIs |
| `/ui/downloads` | `clients/http/templates/downloads.html` | Downloads dashboard, websocket updates |
| `/ui/torrents` | `clients/http/templates/torrents.html` | Manual torrent search table |
| `/ui/settings` | `clients/http/templates/settings.html` | Settings editor and file browser dialog |
| `/ui/logs` | `clients/http/templates/logs.html` | Live logs page; SSE stream |
| `/ui/offline` | `clients/http/templates/offline.html` | PWA offline page |

## Core Partials

- `clients/http/templates/partials/anime_actions.html`
- `clients/http/templates/partials/anime_card.html`
- `clients/http/templates/partials/anime_episode_player.html`
- `clients/http/templates/partials/anime_torrent_results.html`
- `clients/http/templates/partials/anime_torrent_row.html`
- `clients/http/templates/partials/download_card.html`
- `clients/http/templates/partials/downloads_panel.html`
- `clients/http/templates/partials/file_browser.html`
- `clients/http/templates/partials/filter_chips.html`
- `clients/http/templates/partials/log_row.html`
- `clients/http/templates/partials/rail.html`
- `clients/http/templates/partials/search_terms.html`
- `clients/http/templates/partials/table_pager.html`
- `clients/http/templates/partials/topbar.html`
- `clients/http/templates/partials/torrent_filters_bar.html`

## Interactive Streams

### Server-Sent Events

- `/ui/anime/{anime_id}/torrents/stream`
- `/ui/logs/stream`

### WebSockets

- `/ui/library/ws`
- `/ui/downloads/ws`

## UI Mutation Endpoints

### Anime actions

- `POST /ui/anime/{anime_id}/like`
- `POST /ui/anime/{anime_id}/tag`
- `POST /ui/anime/{anime_id}/seen`
- `POST /ui/anime/{anime_id}/refresh`
- `POST /ui/anime/{anime_id}/redownload`
- `POST /ui/anime/{anime_id}/delete-seen`
- `POST /ui/anime/{anime_id}/delete-files`
- `POST /ui/anime/{anime_id}/remove`

### Episode actions

- `POST /ui/anime/{anime_id}/episode-progress`
- `POST /ui/anime/{anime_id}/episode-delete`
- `POST /ui/anime/{anime_id}/episode-mark-seen`
- `POST /ui/anime/{anime_id}/episode-mark-unseen`
- `POST /ui/anime/{anime_id}/episode-redownload`
- `POST /ui/anime/{anime_id}/play`

### Terms, downloads, settings, logs

- `POST /ui/anime/{anime_id}/terms`
- `DELETE /ui/anime/{anime_id}/terms`
- `POST /ui/anime/{anime_id}/download`
- `POST /ui/anime/{anime_id}/cancel`
- `POST /ui/settings`
- `POST /ui/logs/clear`

## Existing JSON Endpoints Reusable by Next

- `GET /animelist`
- `GET /anime/{anime_id}`
- `GET /search`
- `GET /state/{anime_id}`
- `GET /search-terms/{anime_id}`
- `POST /search-terms/{anime_id}`
- `DELETE /search-terms/{anime_id}`
- `GET /torrents/search`
- `GET /download/active`
- `GET /download/progress/{anime_id}`
- `GET /settings`
- `PATCH /settings`
- `GET /ui/downloads/overview.json`
- `GET /ui/logs/data`

## Cutover Scope

The Next.js app must replace all page routes listed above while still
consuming Python for:

- anime metadata/state mutations,
- torrent search and download orchestration,
- playback session management and stream segments,
- settings persistence,
- live logs and live download telemetry.
