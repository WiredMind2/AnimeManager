# Unit 4 — Next.js Shaka player lifecycle audit

## Scope and method

**Audited (read-only):**

- `next-web/lib/playback/**` — `use-playback.ts` (load FSM, stale recovery, timeline/startup handlers), `shaka.ts`, `session-api.ts`, `session-guard.ts`, `progress.ts`, `subtitles.ts`, `types.ts`
- `next-web/lib/player-log.ts` — client player telemetry / session log ingest
- `next-web/components/player/**` — `WatchView.tsx`, `VideoPlayer.tsx`, `EpisodePicker.tsx`, `SubtitleBridge.tsx` (read for wiring only)
- `next-web/app/anime/[id]/watch/page.tsx` — watch page data plumbing
- Cross-ref: `next-web/lib/config.ts`, `next-web/app/backend/[...path]/route.ts` (proxy context), unit 1 backend playback, unit 3 HTTP/LAN (#1)
- Tests: `session-guard.test.ts`, `progress.test.ts` (static review; `npm test` blocked — no `next-web/node_modules` in worktree)

**Out of scope:** Backend `PlaybackService` speculative seek (unit 1 #1), FFmpeg adapter (unit 2), full subtitle/libass bridge internals.

**Method:** Static code review of load lifecycle, session-guard races, recovery limits, and telemetry paths.

---

## Load phase FSM (`use-playback.ts`)

Phases are recorded via `markLoadPhase` → `loadPhaseRef` + `playerLoggerRef.log("load_phase", …)`.

| Phase | When set | Notes |
|-------|----------|-------|
| `idle` | initial ref | not logged until first load |
| `load_requested` | start of `loadPlayback` | bumps module `playbackLoadEpoch` |
| `stopping_previous_session` | before `stopSession()` | explicit stop uses session-guard |
| `creating_session` | before `POST /ui/anime/{id}/play` | |
| `session_created` | after payload parsed | sets refs, anchor, duration |
| `session_create_failed` | createSession throw | early return, no heartbeat |
| `shaka_script_loaded` | after `createShakaPlayer` | CDN script 4.10.9 |
| `shaka_configuring` / `shaka_configured` | `buildShakaConfig` + `configure` | resume vs fresh prefetch differs |
| `shaka_attach_start` / `shaka_attached` | `player.attach(video)` | `shakaAttachInProgressRef` guards stall detector |
| `manifest_loaded` | after `player.load` succeeds | resets `sessionRecoveryAttemptsRef` to 0 |
| `startup_ready` | subtitles attached | UI status “Ready · press play” |
| `startup_failed` | catch around Shaka attach/load | **does not return** — see finding #1 |
| `shaka_error_event` | Shaka `error` listener | sets `explicitPlaybackErrorRef` |
| `startup_stalled_without_explicit_error` | `waiting` @ t≈0 in startup phases | see finding #3 |
| `playing` | `playing` event | clears explicit error + stall flag |

**Stale-load invalidation:** module-global `playbackLoadEpoch` (line 43) incremented on each `loadPlayback` and on auto-load effect cleanup (line 916). In-flight loads call `abortIfStale(stage)` and return without tearing down a session created by a superseded generation **if** the newer load already ran `stopSession` (session-guard allows gen N−1 stop when gen N is active).

**Evidence:** `next-web/lib/playback/use-playback.ts:43-44`, `:157-160`, `:354-394`, `:662-670`, `:899-918`.

`LoadPhase` in `types.ts` omits runtime-only phases (`startup_stalled_without_explicit_error`, `shaka_error_event`) — see finding #12.

---

## Shaka configuration (`shaka.ts`)

`buildShakaConfig(resume: boolean)` (`shaka.ts:4-28`):

| Key | Fresh start | Resume (`loadStartTime > 0`) |
|-----|-------------|------------------------------|
| `streaming.segmentPrefetchLimit` | `2` | `0` (avoid speculative far segments on anchored window) |
| `streaming.bufferingGoal` | `12` | `12` |
| `streaming.rebufferingGoal` | `4` | `4` |
| `streaming.retryParameters.maxAttempts` | `6` | `6` |
| `manifest.hls.ignoreManifestProgramDateTime` | `true` | `true` |

`loadStartTimeFromPayload` returns `undefined` for zero start; caller passes `loadStartTime ?? 0` so fresh EVENT manifests seek to 0 instead of live edge (`use-playback.ts:428-433`, `:560`).

`createShakaPlayer` loads Shaka **4.10.9** from cdnjs, installs polyfills, skips `setVideoContainer` (hang workaround, comment at `shaka.ts:68-70`).

---

## Session-guard & stop races (`session-guard.ts`)

`shouldStopSession` prevents POST `/stop` from killing a session a newer in-flight load still needs (Fast Refresh / overlapping loads).

| Scenario | `postStop` | Evidence |
|----------|------------|----------|
| Unmount, load in progress, same generation | **false** | `session-guard.ts:32-34`, test line 19-28 |
| Unmount, stale generation (session gen < active epoch) | **false** | test line 7-16 |
| Unmount, load complete, generations match | **true** | lines 32-35 |
| Explicit stop at load start, prior generation | **true** (`sessionGen < activeGen`) | lines 38-39 |
| Explicit stop, same gen, load in progress | **false** | lines 40-41 |
| No `stopUrl` or null `sessionLoadGeneration` | **false** | lines 29-30 |

**Unmount during active load:** cleanup effect logs `session_stop_skipped` and **returns without** `stopSession` (`use-playback.ts:882-887`) — backend session can outlive React unmount until TTL (finding #7).

**Tests:** 4 cases in `session-guard.test.ts`; missing explicit “tear down prior generation during load” case (finding #11).

---

## Stale-session recovery

**Constants:** `MAX_SESSION_RECOVERY_ATTEMPTS = 3`, `STALE_SESSION_RECOVERY_DELAY_MS = 250` (`use-playback.ts:45-46`).

**Triggers:**

1. HLS manifest HTTP 404 — response filter on `/ui/stream/` URIs containing `index.m3u8` → `scheduleStaleSessionRecovery("manifest_404")` (`use-playback.ts:474-495`).
2. Heartbeat HTTP 404 — `startHeartbeat` → `onSessionLost` → `"heartbeat_404"` (`session-api.ts:74-76`, `use-playback.ts:663-664`).

**Flow:** debounced timer → increment attempt counter → `queueReplayCurrent()` (120 ms coalesce) → full `loadPlayback` for current file.

**Reset:** counter cleared only on successful `player.load` (`use-playback.ts:562`).

**Gaps:** see findings #2, #6, #9, #10.

---

## Timeline jump recovery (`progress.ts`)

- Threshold: `TIMELINE_JUMP_THRESHOLD_SECONDS = 30`.
- `shouldRecoverTimelineJump`: true when `|t − last| > 30` or `t > knownDuration × 1.2`, unless `userSeeking` (`progress.ts:36-54`).
- Handler snaps `video.currentTime` to `lastSaneCurrentTimeRef` (`use-playback.ts:745-764`).
- Post-load sanity seek for absurd duration/time when starting from zero (`use-playback.ts:565-590`).
- `VideoPlayer` pins media-chrome duration when MSE reports UINT32-scale values (`VideoPlayer.tsx:31-62`).

**Tests:** 4 cases in `progress.test.ts` (jump, over-duration, user seek exempt, small delta ignored).

---

## Startup stall detection

`onWaiting` calls `reportStartupStall` when (`use-playback.ts:798-812`):

- no `explicitPlaybackErrorRef`
- `video.currentTime ≤ 0.05`
- `isStartupPhase(phase)` — **only** `shaka_script_loaded` … `shaka_attach_start` (excludes `shaka_attached`, `manifest_loaded`)
- not `shakaAttachInProgressRef`

Sets fault class `startup_stall`, UI error, logs `startup_stalled_without_explicit_error`.

---

## Client telemetry (`player-log.ts`)

- Console: all levels always.
- Server ingest: `POST /ui/stream/{sessionId}/log` via `sendBeacon` / `fetch` (batch ≤200, flush every 2s, on visibility hidden / beforeunload / session change).
- **Requires `sessionId`** — events before `setSessionId` are console-only (finding #4).
- Fault taxonomy: `playerFaultFields` → `startup_config_warning`, `startup_stall`, `playback_runtime_error`, `rebuffering`.
- **Does not** honor `NEXT_PUBLIC_TELEMETRY_ENABLED` (unlike `lib/telemetry/client.ts`) — finding #8.
- Player faults are **not** duplicated to `/ui/telemetry/events` (general CLIENT category).

---

## Cross-ref: unit 3 #1 (LAN / proxy)

Streaming routes remain LAN-gated on the backend; the Next.js player always uses same-origin `/backend/...` proxy (`session-api.ts:28`, `player-log.ts:193`). This audit does not re-open LAN policy; segment token optionalily (unit 3 auth matrix) means manifest 404 recovery may be triggered by session expiry while segments could still be probed with session id alone on trusted networks.

---

## Findings

### 1. Heartbeat starts after Shaka startup failure

- **Severity:** high
- **Title:** Failed attach/load still starts 30s heartbeat — orphan session + misleading “unavailable” UI
- **Evidence:** `use-playback.ts:626-665` — `catch` sets error/`startup_failed` but does not `return`; execution reaches `startHeartbeat` unless `abortIfStale`
- **Repro:** Force Shaka load failure (bad manifest, unsupported browser). Session created; UI shows “Playback unavailable”; heartbeat keeps session alive until TTL.
- **Expected vs actual:** Expected: stop heartbeat or POST `/stop` on startup failure after session create. Actual: heartbeat runs; `stopSession` not called until user retries or navigates away.
- **Suggested fix:** `return` after startup failure before heartbeat, or call `stopSession()` in the failure path.

---

### 2. No client recovery for segment errors / backend scrub rejection

- **Severity:** high
- **Title:** Stale recovery only on manifest 404 and heartbeat 404 — segment failures leave user stuck
- **Evidence:** Response filter logs segment ≥400 but only schedules recovery for `index.m3u8` 404 (`use-playback.ts:476-495`); Shaka errors set UI error without auto-replay
- **Cross-ref:** Unit 1 #1 — backend rejects far-ahead segments without ffmpeg restart; client does not map segment 404 / Shaka `HTTP_ERROR` to `scheduleStaleSessionRecovery`
- **Repro:** Resume session; scrub beyond backend forward window; segment GET 404 or Shaka error — no auto `queueReplayCurrent` unless manifest also 404.
- **Suggested fix:** Classify recoverable Shaka/network errors (segment 404, specific codes) and invoke stale recovery with attempt cap; optionally pass scrub target to backend on replay.

---

### 3. Startup stall detector misses post-attach phases

- **Severity:** medium
- **Title:** `isStartupPhase` excludes `shaka_attached` / pre-`manifest_loaded` waiting at t=0
- **Evidence:** `use-playback.ts:143-150`, `:805-812` — stall check uses phases ending at `shaka_attach_start`
- **Repro:** Slow `player.load` (ffmpeg resume blocking on first segment); video fires `waiting` at 0 while phase is `shaka_attached` — no `startup_stalled_without_explicit_error`.
- **Suggested fix:** Extend startup phases through `manifest_loaded` or use time-budget watchdog from `session_created`.

---

### 4. Pre-session player logs never reach server

- **Severity:** medium
- **Title:** `createPlayerLogger` drops queued events when `sessionId` is empty
- **Evidence:** `player-log.ts:255-257`, `:188-191` — `load_requested`, `stopping_previous_session`, `creating_session`, `session_create_failed` are console-only
- **Repro:** Inspect `/ui/stream/{id}/log` ingest during failed startup — missing early phases that explain failure.
- **Suggested fix:** Buffer pre-session events and flush after `setSessionId`, or attach logs to anime/file context endpoint.

---

### 5. `episodeResumeMap` fetched but unused in watch UI

- **Severity:** medium
- **Title:** Dead prop — resume positions not shown in episode picker
- **Evidence:** `watch/page.tsx:54` passes map; `WatchView.tsx:25` destructures but never uses; `EpisodePicker.tsx` has no resume column
- **Repro:** Open watch page — table shows no saved position per file; resume only via backend `/play` defaulting (if server applies stored progress).
- **Suggested fix:** Display resume hints in picker or pass map into progress UX; remove dead prop if intentional.

---

### 6. `replayInFlight` suppresses stale recovery entirely

- **Severity:** medium
- **Title:** Heartbeat 404 during replay is ignored — no queued recovery
- **Evidence:** `use-playback.ts:716-718` — early return when `replayInFlightRef.current`
- **Repro:** Stale recovery replay in progress; heartbeat 404 fires — `scheduleStaleSessionRecovery` no-ops; replay may still fail against dead session.
- **Suggested fix:** Set `replayQueuedRef` or defer recovery until replay completes (mirror `queueReplayCurrent` queue pattern).

---

### 7. Unmount during active load skips backend stop

- **Severity:** medium
- **Title:** Fast navigation mid-load leaves server session until TTL
- **Evidence:** `use-playback.ts:882-887` — unmount with `activeLoadGenerationRef !== null` skips `stopSession`
- **Repro:** Start watch auto-load; navigate away before `manifest_loaded` — no POST `/stop` (logged as `unmount_during_active_load`).
- **Suggested fix:** POST stop when session refs were set even if load incomplete, or rely on session-guard with generation match after load flag cleared.

---

### 8. Player logger ignores global telemetry toggle

- **Severity:** medium
- **Title:** `NEXT_PUBLIC_TELEMETRY_ENABLED` not checked in `player-log.ts`
- **Evidence:** `player-log.ts:188-211` always POSTs when `sessionId` set; compare `lib/telemetry/client.ts:19-25`
- **Repro:** Set `NEXT_PUBLIC_TELEMETRY_ENABLED=false`; player session logs still sent to `/ui/stream/.../log`.
- **Suggested fix:** Gate server flush on same flag (keep console logs optional).

---

### 9. Recovery attempt counter not reset on manual retry after exhaustion

- **Severity:** low
- **Title:** After 3 auto recoveries, user must reload page — `playFile` does not reset counter
- **Evidence:** `sessionRecoveryAttemptsRef` reset only at `manifest_loaded` (`use-playback.ts:562`); cap message at `:720-723`
- **Repro:** Exhaust auto recovery; click Play on another episode or same — counter still ≥3, immediate error message.
- **Suggested fix:** Reset counter on explicit `playFile` / user gesture.

---

### 10. Segment HTTP errors do not trigger stale recovery

- **Severity:** low
- **Title:** Response filter logs stream 404s but only manifest schedules recovery
- **Evidence:** `use-playback.ts:489-495` vs `:476-488` logging
- **Suggested fix:** Treat session-scoped segment 404 (not subtitle static assets) as recoverable when not in user seek.

---

### 11. Session-guard test gap for load-start teardown

- **Severity:** low
- **Title:** Missing test: prior generation stop allowed while `isLoadInProgress`
- **Evidence:** `session-guard.ts:38-39`; tests cover unmount stale gen but not explicit stop path during overlapping load
- **Suggested fix:** Add vitest case `sessionLoadGeneration: 4, activeLoadGeneration: 5, isLoadInProgress: true, isUnmountDuringLoad: false` → expect `true`.

---

### 12. `LoadPhase` type incomplete

- **Severity:** low
- **Title:** TypeScript `LoadPhase` union missing runtime phases
- **Evidence:** `types.ts:7-21` vs `markLoadPhase("startup_stalled_without_explicit_error")`, `"shaka_error_event"`
- **Suggested fix:** Extend union or derive from const array.

---

### 13. Heartbeat errors swallowed

- **Severity:** low
- **Title:** Heartbeat `fetch` failure silently ignored
- **Evidence:** `session-api.ts:72-78` — `.catch(() => {})` on network failure; no offline/stale detection except 404
- **Suggested fix:** Log client-side; optional consecutive-failure recovery.

---

### 14. Audio track change replays; subtitle change does not

- **Severity:** info
- **Title:** By design — audio requires new transcode session; subtitles are sidecar
- **Evidence:** `VideoPlayer.tsx:179-201` — audio `onChange` → `queueReplayCurrent()`; subtitle only `setSubtitleTrackId`
- **Note:** Correct given backend audio track on create; document for operators.

---

### 15. Module-global `playbackLoadEpoch` complicates testing

- **Severity:** info
- **Title:** Load invalidation state lives outside hook instance
- **Evidence:** `use-playback.ts:43`, `:916` increment on auto-load cleanup
- **Note:** Intentional for Fast Refresh; unit/integration tests need module reset or accept shared epoch.

---

### 16. Stale recovery timing constants

- **Severity:** info
- **Title:** Documented recovery budget — 3 attempts, 250 ms debounce, 120 ms replay coalesce
- **Evidence:** `use-playback.ts:45-46`, `:695-710`, `:726-734`
- **Note:** With 30s heartbeat, up to ~90s+ before user sees “Press play again or reload”.

---

## Summary table

| # | Severity | Title |
|---|----------|-------|
| 1 | high | Heartbeat after Shaka startup failure |
| 2 | high | No recovery for segment / scrub errors |
| 3 | medium | Startup stall misses post-attach phases |
| 4 | medium | Pre-session logs not ingested |
| 5 | medium | `episodeResumeMap` unused |
| 6 | medium | `replayInFlight` blocks recovery |
| 7 | medium | Unmount mid-load skips stop |
| 8 | medium | Player log ignores telemetry toggle |
| 9 | low | Recovery counter stuck after exhaustion |
| 10 | low | Segment 404 no recovery |
| 11 | low | Session-guard test gap |
| 12 | low | `LoadPhase` type incomplete |
| 13 | low | Heartbeat network errors ignored |
| 14 | info | Audio replay vs subtitle in-place |
| 15 | info | Global load epoch |
| 16 | info | Recovery timing constants |

**Totals:** 16 findings — **high 2**, **medium 6**, **low 5**, **info 3**.

---

## Criteria mapping

| Criterion | Status |
|-----------|--------|
| Load FSM documented with evidence | ✅ Phase table + line refs |
| Session-guard stop races documented | ✅ Decision table + tests |
| Stale recovery documented | ✅ Triggers, caps, gaps (#2, #6, #9, #10) |
| Shaka config documented | ✅ Resume vs fresh table |
| Timeline jump recovery | ✅ Threshold + handler refs |
| Startup stall detection | ✅ Documented + gap (#3) |
| MAX_SESSION_RECOVERY_ATTEMPTS | ✅ §Stale-session recovery |
| Client telemetry | ✅ player-log paths + gaps (#4, #8) |
