# Unit 3 — HTTP / SDK / proxy & access control audit

## Scope and method

**Audited (read-only):**

- `clients/http/web.py` — playback routes, `_is_client_allowed_for_streaming`, `_client_host`
- `clients/http/app.py` — JSON API surfaces adjacent to playback
- `clients/sdk.py` — playback method signatures and defaults
- `composition/facade.py` — playback delegation
- `next-web/app/backend/[...path]/route.ts` — proxy timeout and header forwarding
- `next-web/lib/config.ts`, `next-web/lib/playback/session-api.ts` — client URL resolution
- Cross-ref: `application/playback/contract.py`, `application/playback/service.py` (unit 1)
- Tests: `tests/unit/clients/test_http_web_ui.py`, `tests/integration/test_playback_*.py`

**Out of scope:** FFmpeg adapter (unit 2), Shaka player hook internals (unit 4+).

---

## Playback route table

All streaming session lifecycle routes live under the legacy `/ui/*` prefix (not the JSON `/anime/...` API). Next.js reaches them via `/backend/ui/...`.

| Method | Path | Handler | LAN gate | Backend auth | Response |
|--------|------|---------|----------|--------------|----------|
| POST | `/ui/anime/{anime_id}/play` | `web_action_play` | yes | none (creates session) | JSON session payload |
| GET | `/ui/stream/{session_id}/index.m3u8` | `web_stream_manifest` | yes | HMAC token **required** | HLS manifest file |
| GET | `/ui/stream/{session_id}/{segment_name}` | `web_stream_segment` | yes | token **optional** | segment / subtitle / ASS file |
| GET | `/ui/stream/{session_id}/player.log` | `web_stream_player_log_download` | yes | token via manifest resolve | plain-text debug log |
| POST | `/ui/stream/{session_id}/heartbeat` | `web_stream_heartbeat` | yes | session_id only | JSON `{session_id, token, expires_at}` |
| POST | `/ui/stream/{session_id}/stop` | `web_stream_stop` | yes | session_id only | JSON `{ok: true}` |
| POST | `/ui/stream/{session_id}/log` | `web_stream_player_log` | yes | session_id only (output_dir lookup) | JSON `{ok, accepted}` |

**Adjacent routes (no active stream, but feed the player UI):**

| Method | Path | LAN gate | Notes |
|--------|------|----------|-------|
| GET | `/ui/anime/{anime_id}/watch` | **no** | HTML watch shell |
| GET | `/ui/anime/{anime_id}/watch.json` | **no** | Episode list, tracks, resume map |
| POST | `/ui/anime/{anime_id}/episode-progress` | **no** | Watch progress persistence |
| GET | `/anime/{anime_id}/episode-files` | **no** | JSON API (`app.py`); includes `path` field |

No `POST /play`, `/stream/...`, or heartbeat routes exist on the JSON API router (`clients/http/app.py`).

---

## Auth matrix (manifest vs segment vs heartbeat)

| Operation | HTTP token param | Service-layer check | Effective gate |
|-----------|------------------|---------------------|----------------|
| Create session (`/play`) | N/A | file_id must exist on disk | LAN + valid episode |
| Manifest (`index.m3u8`) | required query param (`token: str`) | `UnauthorizedError` if missing/invalid | LAN + valid token |
| Segment / subtitle / ASS | optional (`token: str = ""`) | token verified **only when non-empty**; empty allowed | LAN + session_id (UUID) |
| Player log download | optional (defaults `""`) | uses manifest resolve path → token required when empty | LAN + token |
| Heartbeat | none | session must exist | LAN + session_id |
| Stop | none | session popped if exists | LAN + session_id |
| Client log ingest | none | output_dir from session store | LAN + session_id |

**Cross-ref unit 1 #2:** `application/playback/service.py:322-325` — segment path skips token when `segment_name` is set and token is empty. HTTP layer mirrors this at `web.py:1848-1861`. Integration and unit tests treat tokenless segments as intentional for HLS relative URLs (`test_stream_segment_allows_tokenless_fetch_for_relative_playlist_urls`, `test_playback_subsplease_ep11`).

**Residual risk:** On any host that passes the LAN gate, knowledge of `session_id` (32-char hex) is sufficient to download all segments without the HMAC token.

---

## LAN allowlist & `player_allow_public`

`_is_client_allowed_for_streaming` (`web.py:591-621`) decision order:

1. Empty host → **deny**
2. Loopback names (`127.0.0.1`, `::1`, `localhost`, `testclient`) → **allow**
3. Settings `web.player_allowlist` (CIDR or exact IP) → **allow** if match
4. Settings `web.player_allow_public` (default **false**) → **allow** if true
5. Non-IP hostname → **allow** if DNS resolves to private/loopback/link-local
6. Literal IP → **allow** if private/loopback/link-local; else **deny**

**Config-dependent note:** `player_allow_public` and `player_allowlist` are read from runtime `settings.json` → `web` section at request time. They are **not** present in the repo `settings.json` template; default behavior is LAN-only (private IPs + loopback). Operators must add a `web` object manually, e.g. `"web": { "player_allow_public": true, "player_allowlist": ["192.168.1.0/24"] }`.

Denied requests log via `_log_stream_access_denied` with a settings snapshot including `player_allow_public` / `player_allowlist`.

---

## SDK / facade playback surface

Thin pass-through chain (no HTTP-specific logic):

```
web.py → ClientSDK → EmbeddedClientFacade → AnimeApplicationService → PlaybackService
```

| Method | SDK default | Facade default | HTTP caller |
|--------|-------------|----------------|-------------|
| `create_playback_session(..., ttl_seconds=900)` | 900 | 900 | `PLAYBACK_SESSION_TTL_SECONDS = 900` |
| `heartbeat_playback_session` | — | — | no TTL param |
| `resolve_playback_media_path(token, segment_name?)` | — | — | token forwarded as-is |
| `stop_playback_session` | — | — | session_id only |

SDK serializes DTOs with `dataclasses.asdict`; no field filtering (session responses include `output_dir`, `manifest_path`, etc. in internal flows; play response omits sensitive paths in JSON by selective keying in `web_action_play`).

---

## Proxy timeout vs `RESUME_SEGMENT_WAIT_SECONDS`

| Constant | Location | Value |
|----------|----------|-------|
| `RESUME_SEGMENT_WAIT_SECONDS` | `application/playback/contract.py:29` | **180.0 s** |
| `SESSION_CREATE_WAIT_SECONDS` | `contract.py:28` | 25.0 s |
| `PROXY_TIMEOUT_MS` | `next-web/app/backend/[...path]/route.ts:6` | **240_000 ms (240 s)** |

**Alignment:** Proxy timeout exceeds the longest single backend wait (`RESUME_SEGMENT_WAIT_SECONDS`) by 60 s. Comment in `route.ts:5` ("~3 minutes") matches the contract constant.

**Blocking paths through proxy:**

- `POST /play` — `create_session` waits up to 180 s for resume anchor segment before returning (`service.py:196-207`).
- `GET /ui/stream/.../segment_*.ts` — `_ensure_segment` waits up to 180 s per request on resume playhead paths (`service.py:409-426, 455-463`).

Each individual proxied request should complete within 240 s. No stacked multi-wait loop exceeds 180 s in one handler invocation.

**Gap:** Only the Next.js proxy enforces the 240 s ceiling. Direct FastAPI access (`run.py api`, port 8081) has no equivalent request timeout; uvicorn will wait indefinitely.

---

## Token / TTL duplication vs contract

| Location | Constant / default | Imports `SESSION_TTL_SECONDS`? |
|----------|-------------------|-------------------------------|
| `application/playback/contract.py:27` | `SESSION_TTL_SECONDS = 900` | source of truth |
| `application/commands/media_streaming.py:13` | `ttl_seconds: int = 900` | no |
| `application/playback/service.py:85,148,304` | `default_ttl_seconds=900`; heartbeat uses `_default_ttl_seconds` | no |
| `application/services/anime_service.py:969` | `ttl_seconds: int = 900` | no |
| `composition/facade.py:361` | `ttl_seconds: int = 900` | no |
| `clients/sdk.py:417` | `ttl_seconds: int = 900` | no |
| `clients/http/web.py:101,1692` | `PLAYBACK_SESSION_TTL_SECONDS = 900` | no |

**Cross-ref unit 1 #3, #4, #6:** Heartbeat always resets `expires_at` to `now + _default_ttl_seconds` (900), ignoring per-create TTL. HMAC token lifetime uses `max(ttl_seconds, 12h)` while session record expires at 900 s.

---

## Findings

### 1. LAN streaming gate neutralized in default web mode (Next.js proxy)

- **Severity:** high
- **Title:** All proxied playback requests appear as loopback to FastAPI
- **Evidence:** `route.ts:17-18` forwards to `127.0.0.1:8081`; `web.py:539-545` `_client_host` uses `request.client.host` when no `X-Forwarded-For`; `web.py:595-596` loopback → allow
- **Repro:** Expose Next.js on `0.0.0.0:3000` to WAN; remote client POSTs `/backend/ui/anime/1/play` → backend sees `127.0.0.1` → streaming allowed regardless of `player_allow_public=false`
- **Expected vs actual:** Expected: LAN gate restricts stream artifacts to trusted clients. Actual: web-mode proxy collapses all clients to localhost; allowlist/public flag never evaluated for real client IP
- **Suggested fix:** Next.js proxy should set `X-Forwarded-For` (or `X-Real-IP`) from the browser connection; FastAPI should only trust forwarded headers from known proxy hops

---

### 2. HLS segments do not require HMAC token

- **Severity:** medium
- **Title:** Token optional on segment route (session_id alone)
- **Evidence:** `web.py:1848,1858-1861`; `service.py:322-325`; tests `test_stream_segment_allows_tokenless_fetch_for_relative_playlist_urls`
- **Repro:** `GET /ui/stream/{session_id}/segment_00001.ts` without `token` → 200 if session exists
- **Expected vs actual:** Documented as HLS-relative-URL workaround; security relies on LAN gate + UUID secrecy
- **Suggested fix:** Require token on all artifacts, or document as explicit LAN-trust model (see finding 1 for web-mode LAN bypass)
- **Cross-ref:** unit 1 finding #2

---

### 3. Heartbeat, stop, and client-log routes lack session token

- **Severity:** medium
- **Title:** Session lifecycle endpoints authenticate by session_id only
- **Evidence:** `web.py:1904-1921` (heartbeat), `1924-1944` (stop), `1947-1969` (log ingest) — no token param
- **Repro:** On a LAN-permitted host, POST `/ui/stream/{session_id}/heartbeat` extends TTL without token; POST `/stop` tears down another user's session
- **Expected vs actual:** LAN trust assumed; no per-session secret beyond UUID
- **Suggested fix:** Require token query param or header on mutating session routes

---

### 4. `SESSION_TTL_SECONDS` duplicated at six layers; HTTP uses local constant

- **Severity:** medium
- **Title:** TTL 900 hard-coded outside contract module
- **Evidence:** table above; `web.py:101` `PLAYBACK_SESSION_TTL_SECONDS = 900`
- **Repro:** Change `contract.SESSION_TTL_SECONDS` to 1800 without updating `web.py` / SDK defaults → HTTP creates 900 s sessions while docs say 1800
- **Suggested fix:** Import `SESSION_TTL_SECONDS` in `web.py`, SDK, facade, command, and wire `PlaybackService(default_ttl_seconds=SESSION_TTL_SECONDS)` in composition
- **Cross-ref:** unit 1 finding #6

---

### 5. Heartbeat TTL reset ignores create-time TTL

- **Severity:** medium
- **Title:** HTTP always creates with 900 s; heartbeat resets to service default
- **Evidence:** `web.py:1692`; `service.py:304`; unit 1 finding #3
- **Repro:** If TTL were raised via SDK-only caller, first heartbeat shrinks window to 900 s
- **Suggested fix:** Persist `ttl_seconds` on session DTO; heartbeat uses stored value

---

### 6. HMAC token outlives session `expires_at`

- **Severity:** medium
- **Title:** Token verify window min 12 h vs session TTL 900 s
- **Evidence:** `service.py:228-231,240`; unit 1 finding #4
- **Repro:** Delayed cleanup + valid token + lingering session edge case
- **Suggested fix:** Align token expiry with session `expires_at`

---

### 7. Watch and progress routes skip LAN gate

- **Severity:** medium
- **Title:** Player shell and metadata accessible without streaming ACL
- **Evidence:** `web.py:1344-1388` (watch/watch.json), `1434-1460` (episode-progress) — no `_is_client_allowed_for_streaming`
- **Repro:** Any client reaching Next.js can fetch watch metadata and post progress without passing stream ACL (amplified by finding 1)
- **Suggested fix:** Apply consistent ACL or document that UI metadata is public while bytes are gated (currently inconsistent in web mode)

---

### 8. Episode-files JSON API exposes absolute filesystem paths

- **Severity:** low
- **Title:** `EpisodeFileDTO.path` serialized to clients
- **Evidence:** `application/dto/media_streaming.py:12`; `sdk.py:389-390` `asdict`; `app.py:393-395` no auth
- **Repro:** `GET /anime/1/episode-files` → items include full local paths
- **Suggested fix:** Strip `path` from HTTP responses; keep `file_id` only

---

### 9. `player_allow_public` / allowlist undocumented in settings template

- **Severity:** low
- **Title:** Stream ACL settings only in runtime `settings.web` dict
- **Evidence:** grep shows keys only in `web.py`; absent from repo `settings.json`
- **Repro:** Operator expects LAN restriction but cannot discover allowlist keys
- **Suggested fix:** Add `web.player_allow_public` (default false) and `web.player_allowlist` to settings template and settings UI
- **Note:** Config-dependent — default false preserves LAN-only intent for direct FastAPI access

---

### 10. `X-Forwarded-For` trusted without proxy allowlist

- **Severity:** low
- **Title:** First forwarded hop accepted as client IP
- **Evidence:** `web.py:540-542` — takes first `X-Forwarded-For` entry unconditionally
- **Repro:** Client hits exposed `:8081` directly with spoofed `X-Forwarded-For: 127.0.0.1` → streaming allowed
- **Suggested fix:** Only honor forwarded headers from trusted reverse proxies

---

### 11. Manifest missing token returns HTTP 422, not 401

- **Severity:** low
- **Title:** FastAPI validation vs domain unauthorized mismatch
- **Evidence:** `web.py:1765` `token: str` required; test `test_stream_manifest_requires_token` expects 422; service would return 401 for empty token on manifest resolve
- **Repro:** `GET .../index.m3u8` without token → 422 Unprocessable Entity
- **Suggested fix:** Use `token: str = ""` and map to 401 via service, or document 422 as intentional

---

### 12. `client_host` on session is proxy address in web mode

- **Severity:** low
- **Title:** Stored client_host is `127.0.0.1` for all web-mode plays
- **Evidence:** `web.py:1691` passes `_client_host(request)`; proxy path → loopback
- **Repro:** Player session logs show `client_host=127.0.0.1` for all viewers
- **Suggested fix:** Forward real client IP from Next.js (same as finding 1)

---

### 13. Proxy timeout aligned with resume wait (informational positive)

- **Severity:** info
- **Title:** 240 s proxy vs 180 s resume wait — adequate margin
- **Evidence:** `route.ts:6`, `contract.py:29`, `service.py:199-200`
- **Note:** AGENTS.md documents 240 s intentionally; no misalignment found

---

### 14. No JSON REST playback API

- **Severity:** info
- **Title:** Playback only on `/ui/*` legacy routes
- **Evidence:** `app.py` has episode-files but no play/stream routes; Next.js uses `/backend/ui/...`
- **Note:** By design per ADR embedded-runtime; clients must use UI routes or SDK in-process

---

### 15. SDK / facade add no playback policy

- **Severity:** info
- **Title:** All access control lives in HTTP layer + PlaybackService
- **Evidence:** `sdk.py:411-455`, `facade.py:355-396` — pure delegation
- **Note:** Tk or future clients bypass HTTP LAN gate entirely when using SDK in-process

---

## Summary counts

| Severity | Count |
|----------|-------|
| critical | 0 |
| high | 1 |
| medium | 6 |
| low | 5 |
| info | 3 |

**Total:** 15 findings

---

## Cross-reference index (unit 1)

| Unit 3 finding | Unit 1 finding |
|----------------|----------------|
| #2 Segment token optional | #2 |
| #4 TTL duplication | #6 |
| #5 Heartbeat TTL | #3 |
| #6 Token vs session expiry | #4 |
