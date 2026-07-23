# Unit 1 — Backend playback core audit

## Scope and method

**Audited (read-only):**

- `application/playback/**` — contract, service, session store, playlist/resume/transcode wrappers
- `application/services/anime_service.py` — playback delegation (`create_playback_session`, `resolve_playback_media_path`, etc.)
- `application/commands|queries|dto/media_streaming*`
- `application/services/player_session_log.py`
- `ports/interfaces.py` — `MediaLibraryPort`, `MediaTranscoderPort`
- `composition/root.py` — wiring constants vs `application/playback/contract.py`

**Out of scope (noted for other units):** HTTP routes (`clients/http/web.py`), FFmpeg adapter internals (`adapters/media/ffmpeg_transcoder.py`), Next.js player.

**Method:** Static code review + existing unit tests (`tests/unit/playback/*`, `tests/unit/components/test_media_streaming_service.py` — 38 passed). Code-review-graph MCP was unavailable.

---

## Contract constants vs composition wiring

| Constant | `contract.py` | `PlaybackService` default | `composition/root.py` |
|----------|---------------|---------------------------|------------------------|
| `SEGMENT_SECONDS` | `4` | imports from contract | literal `_SEGMENT_SECONDS = 4` (not imported) |
| `SESSION_TTL_SECONDS` | `900` | `default_ttl_seconds=900` | **not passed** (relies on service default) |
| `token_secret` | — | random UUID if omitted | **not passed** |
| Wait timeouts (`RESUME_SEGMENT_WAIT_SECONDS`, etc.) | defined | imported & used | N/A |

**Finding:** Composition duplicates `SEGMENT_SECONDS` as a local literal instead of importing `application.playback.contract.SEGMENT_SECONDS`. Values match today but can drift silently. `SESSION_TTL_SECONDS` is never referenced at the wiring layer despite being documented as the single source of truth.

---

## Findings

### 1. Frozen playhead blocks intentional scrub-ahead on resume sessions

- **Severity:** high
- **Title:** `_is_speculative_far_request` uses immutable `playback_start_seconds` as playhead
- **Evidence:** `application/playback/service.py:465-488`, `application/playback/service.py:252` (set once at create); `playback_start_seconds` is never updated elsewhere in the codebase
- **Repro:** Create session with `start_time_seconds=708` (playhead segment 177). After encode is healthy at segment ~180, request `segment_00280.ts` (intentional scrub to ~18:40). Service raises `NotFoundError("too far ahead")` without restarting ffmpeg.
- **Expected vs actual:** Expected: user scrub within the episode after resume should trigger seek-on-demand restart. Actual: scrub more than `MAX_FORWARD_JUMP_SEGMENTS` (90) beyond the **initial** resume segment is treated as a Shaka live-edge probe and rejected permanently for that request.
- **Suggested fix:** Track a mutable playhead (heartbeat position, last resolved segment, or max of `transcode_start_segment` / `latest_existing_segment`) for speculative checks; keep initial `playback_start_seconds` only for manifest/`loadStartTime`.

---

### 2. Segment URLs do not require a valid token

- **Severity:** medium
- **Title:** HLS segment/subtitle requests allowed with empty token when `segment_name` is set
- **Evidence:** `application/playback/service.py:322-325`
- **Repro:** `GET resolve_media_path(session_id, token="", segment_name="segment_00001.ts")` succeeds if session exists. Manifest access (`segment_name=None`) correctly requires token.
- **Expected vs actual:** Expected: token required for all stream artifacts. Actual: possession of `session_id` (UUID hex) is sufficient for segment download; token is optional on segment path.
- **Suggested fix:** Require token verification for all resolve paths, or document as LAN-only trust model. **HTTP note for unit 3:** `clients/http/web.py:1843-1861` passes optional `token` query param through unchanged.

---

### 3. Heartbeat resets TTL to service default, ignoring per-session create TTL

- **Severity:** medium
- **Title:** Heartbeat ignores original `ttl_seconds` from session creation
- **Evidence:** `application/playback/service.py:148` (per-command TTL at create), `application/playback/service.py:304` (heartbeat always `now + self._default_ttl_seconds`)
- **Repro:** Create with `ttl_seconds=3600`; heartbeat after 10 minutes sets `expires_at = now + 900`.
- **Expected vs actual:** Expected: heartbeat extends the session by its original TTL window. Actual: custom TTL is shortened to 900s on first heartbeat.
- **Suggested fix:** Store `session.ttl_seconds` on DTO and use it in heartbeat/cleanup.

---

### 4. Token expiry and session expiry are decoupled

- **Severity:** medium
- **Title:** HMAC token lifetime (min 12h) exceeds session `expires_at` (default 900s)
- **Evidence:** `application/playback/service.py:228-231` (`max(ttl_seconds, 12 * 3600)` for token), `application/playback/service.py:240` (`expires_at=now + ttl_seconds`)
- **Repro:** Session cleaned up at 900s idle (`cleanup_stale_sessions`); token would still verify if session object still existed.
- **Expected vs actual:** Token outlives session record in design; after cleanup, `NotFoundError` gates access first. Residual risk: if cleanup is delayed/skipped, stale token remains valid up to 12h while `expires_at` says expired.
- **Suggested fix:** Align token `expires_at` with session `expires_at`, or reject resolve when `time.time() > session.expires_at` explicitly before token check.

---

### 5. Composition omits stable `token_secret`

- **Severity:** medium
- **Title:** Process-local random HMAC secret on every startup
- **Evidence:** `application/playback/session_store.py:18-19`, `composition/root.py:85-89` (no `token_secret` passed)
- **Repro:** N/A in single process — tokens are in-memory bound anyway.
- **Expected vs actual:** Sessions are in-memory, so restart invalidates sessions regardless; a stable secret would matter only if session store becomes persistent/shared.
- **Suggested fix:** Wire secret from settings/env when multi-worker or persistent sessions are introduced.

---

### 6. `SEGMENT_SECONDS` / `SESSION_TTL_SECONDS` not wired from contract in composition

- **Severity:** medium
- **Title:** Duplicate literal constants at composition root
- **Evidence:** `composition/root.py:78-88`, `application/playback/contract.py:5,27`
- **Repro:** Change `contract.SEGMENT_SECONDS` to 6 without updating `root.py` → playlist cadence mismatch between `PlaybackService` and `FFmpegTranscoderAdapter`.
- **Expected vs actual:** Contract module claims “single source of truth”; composition bypasses it.
- **Suggested fix:** `from application.playback.contract import SEGMENT_SECONDS, SESSION_TTL_SECONDS` and pass both into `PlaybackService(...)`.

---

### 7. `_restart_at` swallows transcoder failures

- **Severity:** low
- **Title:** Seek-on-demand restart errors are logged but not propagated
- **Evidence:** `application/playback/service.py:509-537` (`except Exception: _LOG.warning(...)` with no re-raise)
- **Repro:** Force `ensure_hls_session` to raise (e.g. max active sessions exceeded); caller waits then returns `NotFoundError("not available")` with no distinction from slow encode.
- **Expected vs actual:** Expected: infrastructure failure surfaces as `InfrastructureError`. Actual: generic not-found after timeout.
- **Suggested fix:** Re-raise `InfrastructureError`; only swallow transient/expected cases.

---

### 8. `TranscodeSession.is_running` defaults to `True` on probe failure

- **Severity:** low
- **Title:** Optimistic encoder-running assumption when adapter probe fails
- **Evidence:** `application/playback/transcode_session.py:40-47`
- **Repro:** Adapter raises from `is_hls_session_running`; prefetch path skips restart (`in_prefetch` branch) assuming encode is active.
- **Expected vs actual:** May suppress needed restart when probe is broken.
- **Suggested fix:** Default to `False` on exception, or treat as unknown and fall through to restart logic.

---

### 9. Prefetch window uses magic `+3` instead of `PREFETCH_MARGIN`

- **Severity:** low
- **Title:** Inconsistent prefetch constant in segment resolve
- **Evidence:** `application/playback/service.py:411` (`latest + 3`), `application/playback/contract.py:6` (`PREFETCH_MARGIN = 2`)
- **Repro:** N/A — behavioral drift if `PREFETCH_MARGIN` is tuned.
- **Suggested fix:** Use `latest + PREFETCH_MARGIN + 1` or named constant with comment.

---

### 10. Stale sessions only cleaned on create/resolve

- **Severity:** low
- **Title:** No background janitor for idle playback sessions
- **Evidence:** `application/playback/service.py:354-369` called from `create_session` and `resolve_media_path` only; `anime_service.cleanup_playback_sessions` exists but no startup/periodic caller found in audited scope
- **Repro:** Start session, stop heartbeating; ffmpeg may run until next unrelated playback request triggers cleanup.
- **Expected vs actual:** Idle sessions/transcodes linger until another playback operation.
- **Suggested fix:** Periodic cleanup from startup jobs or FastAPI lifespan (unit 3).

---

### 11. `list_episode_files` probes every file on each call

- **Severity:** low
- **Title:** Double ffprobe per episode at list time (tracks + duration)
- **Evidence:** `application/playback/service.py:99-121` (`probe_media_tracks` + `_probe_duration` per row); adapter caches by mtime but first list still spawns subprocesses per file
- **Repro:** Open anime detail with 24 episodes → up to 48 ffprobe invocations (cached on repeat).
- **Suggested fix:** Lazy-probe on play, or batch/cache at library scan layer.

---

### 12. `player_session_log` directory locks never evicted

- **Severity:** low
- **Title:** Unbounded `_dir_locks` dict growth
- **Evidence:** `application/services/player_session_log.py:26-40`
- **Repro:** Many unique session output dirs over long runtime → one lock entry per dir retained forever.
- **Suggested fix:** LRU cap or weakref; locks are cheap but unbounded.

---

### 13. Unknown-duration sessions disable segment guardrails

- **Severity:** low
- **Title:** `total_segments=0` bypasses end-of-stream and speculative checks
- **Evidence:** `application/playback/service.py:388-390`, `application/playback/service.py:248` (`segment_seconds=0`)
- **Repro:** File with tracks but `probe_media_duration=0` → live-style path; segment index checks skipped.
- **Expected vs actual:** By design for incomplete downloads; user can still start playback if tracks exist (`service.py:140-145`).
- **Suggested fix:** Document; optionally cap wait/retry differently for unknown duration.

---

### 14. In-memory session store — no cross-process sharing

- **Severity:** info
- **Title:** Playback sessions not durable or multi-worker safe
- **Evidence:** `application/playback/service.py:94-96` (`dict` under process lock)
- **Repro:** Run two uvicorn workers → session created on worker A fails resolve on worker B.
- **Suggested fix:** Document single-worker assumption or externalize session store.

---

### 15. `MediaStreamingService` alias retained

- **Severity:** info
- **Title:** Legacy alias may confuse callers
- **Evidence:** `application/playback/service.py:603-604`
- **Repro:** N/A
- **Suggested fix:** Deprecation comment or remove when all imports migrated.

---

### 16. Cross-layer note — FFmpeg adapter drops `subtitle_track` on session record

- **Severity:** info (adapter, out of unit ownership)
- **Title:** `_ActiveTranscode` stores `subtitle_track=None` despite parameter
- **Evidence:** `adapters/media/ffmpeg_transcoder.py:245` (comment in audit notes only)
- **Repro:** Subtitle burn-in selection may not survive seek-on-demand session reuse checks (`existing.subtitle_track` comparison omitted at `:158-164`).
- **Suggested fix:** Track in unit 2 adapter audit.

---

## HTTP duplication notes (for unit 3)

- Default `ttl_seconds=900` duplicated in `CreatePlaybackSessionCommand`, `anime_service.create_playback_session`, and `PlaybackService`.
- Stream routes proxy to SDK without re-implementing logic; LAN gate `_is_client_allowed_for_streaming` is HTTP-only (not in playback service).
- Manifest/segment URLs built in `clients/http/web.py` with `token` query param; segment route allows empty token matching service behavior.

---

## Summary counts

| Severity | Count |
|----------|-------|
| critical | 0 |
| high | 1 |
| medium | 5 |
| low | 7 |
| info | 3 |

**Total:** 16 findings
