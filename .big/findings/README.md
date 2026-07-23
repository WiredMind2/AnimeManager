# Media player audit — master findings index

Full audit of media player features (units 1–6). Findings are sorted by **severity** (critical → info), then unit number. Cross-references note duplicate root causes across layers.

**Audit date:** 2026-07-23  
**Hub branch:** `big/media-player-audit`

---
---

## Fix branch status (ig/media-player-fix)

Hub integration merge @ `be95683`. **Highs (10):** U1-1 fixed (segment resolver); U2-1/U5-1 **wontfix** (sidecar-only; burn-in param documented/honest); U3-1 fixed (XFF + trusted proxy + LAN gate); U4-1/U4-2 fixed (load pipeline + recovery); U5-4/U5-5/U5-9 fixed (legacy + repository); U6-1 fixed (media_playback.rst). **Deferred mediums:** optional segment HMAC (U1-2/U3-2), token/session TTL decoupling (U1-4), unwired proxy.ts middleware (U6-6), several client telemetry/recovery edge cases — see unit docs.


## Summary by unit

| Unit | Document | Total | Critical | High | Medium | Low | Info |
|------|----------|-------|----------|------|--------|-----|------|
| 1 | [Backend playback core](unit-1-backend-playback.md) | 16 | 0 | 1 | 5 | 7 | 3 |
| 2 | [FFmpeg transcoder & encoder](unit-2-ffmpeg-adapter.md) | 16 | 0 | 1 | 6 | 7 | 2 |
| 3 | [HTTP / SDK / proxy](unit-3-http-sdk-proxy.md) | 15 | 0 | 1 | 6 | 5 | 3 |
| 4 | [Next.js Shaka player](unit-4-nextjs-player.md) | 16 | 0 | 2 | 6 | 5 | 3 |
| 5 | [Subtitles, resume & progress](unit-5-subtitles-resume-progress.md) | 13 | 0 | 4 | 6 | 3 | 0 |
| 6 | [Tests, legacy, docs](unit-6-tests-legacy-docs.md) | 10 | 0 | 1 | 5 | 2 | 2 |
| **All** | | **86** | **0** | **10** | **34** | **29** | **13** |

*Some rows describe the same root cause at different layers (e.g. tokenless segments in units 1 and 3); counts are per-unit, not deduplicated.*

---

## Critical (0)

*(none)*

---

## High (10)

| ID | Title | Unit | Details |
|----|-------|------|---------|
| U1-1 | Frozen playhead blocks intentional scrub-ahead on resume | 1 | [`service.py` speculative check uses immutable `playback_start_seconds`](unit-1-backend-playback.md#1-frozen-playhead-blocks-intentional-scrub-ahead-on-resume-sessions) |
| U2-1 | `subtitle_track` accepted but never applied to ffmpeg command | 2 | [Burn-in param is no-op; sidecar-only architecture](unit-2-ffmpeg-adapter.md#1-subtitle_track-accepted-but-never-applied-to-ffmpeg-command) — also U5-1 |
| U3-1 | LAN streaming gate neutralized in default web mode (Next.js proxy) | 3 | [Backend sees loopback for all proxied clients](unit-3-http-sdk-proxy.md#1-lan-streaming-gate-neutralized-in-default-web-mode-nextjs-proxy) — see U6-6 for `proxy.ts` |
| U4-1 | Heartbeat starts after Shaka startup failure | 4 | [Orphan session when attach/load fails](unit-4-nextjs-player.md#1-heartbeat-starts-after-shaka-startup-failure) |
| U4-2 | No client recovery for segment errors / backend scrub rejection | 4 | [Stale recovery only on manifest/heartbeat 404](unit-4-nextjs-player.md#2-no-client-recovery-for-segment-errors--backend-scrub-rejection) — pairs with U1-1 |
| U5-1 | Subtitle burn-in parameter is end-to-end no-op | 5 | [Cross-ref U2-1](unit-5-subtitles-resume-progress.md#1-subtitle-burn-in-parameter-is-end-to-end-no-op) |
| U5-4 | Legacy resume: Shaka load position can exceed ffmpeg encode start | 5 | [`Math.max(localStorage, server)` vs DB-only encode](unit-5-subtitles-resume-progress.md#4-legacy-resume-shaka-load-position-can-exceed-ffmpeg-encode-start) |
| U5-5 | Legacy progress POST uses manifest-relative time on anchored resume | 5 | [No `toAbsoluteSourceSeconds` in HTMX player](unit-5-subtitles-resume-progress.md#5-legacy-progress-post-uses-manifest-relative-time-on-anchored-resume) |
| U5-9 | Manual status change clears stored position | 5 | [`EpisodePlayerTable` status-only POST → NULL position](unit-5-subtitles-resume-progress.md#9-manual-status-change-clears-stored-position) |
| U6-1 | `docs/features/media_playback.rst` describes pre-HLS architecture | 6 | [Shell-exec doc contradicts AGENTS.md / code](unit-6-tests-legacy-docs.md#1-docsfeaturesmedia_playbackrst-describes-pre-hls-architecture) |

---

## Medium (34)

| ID | Title | Unit | Details |
|----|-------|------|---------|
| U1-2 | Segment URLs do not require a valid token | 1 | [Token optional when `segment_name` set](unit-1-backend-playback.md#2-segment-urls-do-not-require-a-valid-token) — also U3-2 |
| U1-3 | Heartbeat resets TTL to service default | 1 | [Ignores per-create TTL](unit-1-backend-playback.md#3-heartbeat-resets-ttl-to-service-default-ignoring-per-session-create-ttl) — also U3-5 |
| U1-4 | Token expiry and session expiry are decoupled | 1 | [HMAC min 12h vs session 900s](unit-1-backend-playback.md#4-token-expiry-and-session-expiry-are-decoupled) — also U3-6 |
| U1-5 | Composition omits stable `token_secret` | 1 | [Random UUID per process start](unit-1-backend-playback.md#5-composition-omits-stable-token_secret) |
| U1-6 | `SEGMENT_SECONDS` / `SESSION_TTL_SECONDS` not wired from contract | 1 | [Duplicate literals in `root.py`](unit-1-backend-playback.md#6-segment_seconds--session_ttl_seconds-not-wired-from-contract-in-composition) — also U3-4 |
| U2-2 | Active session record discards `subtitle_track` | 2 | [`_ActiveTranscode.subtitle_track=None`](unit-2-ffmpeg-adapter.md#2-active-session-record-discards-subtitle_track-unit-1-16) |
| U2-3 | Session reuse ignores `subtitle_track` and `source_path` | 2 | [Early-return reuse guard incomplete](unit-2-ffmpeg-adapter.md#3-session-reuse-ignores-subtitle_track-and-source_path) |
| U2-5 | `h264_mf` lacks forced-IDR / keyframe alignment flags | 2 | [Windows MF encoder segment cadence risk](unit-2-ffmpeg-adapter.md#5-h264_mf-lacks-forced-idr--keyframe-alignment-flags) |
| U2-6 | LRU eviction by `started_at`, not viewer activity | 2 | [Third session kills oldest encode](unit-2-ffmpeg-adapter.md#6-lru-eviction-by-started_at-not-viewer-activity) |
| U2-7 | Evicted sessions not signaled to PlaybackService | 2 | [Silent ffmpeg kill](unit-2-ffmpeg-adapter.md#7-evicted-sessions-are-not-signaled-to-playbackservice) |
| U2-12 | `materialize_subtitle_tracks` swallows errors silently | 2 | [PGS/image subs invisible](unit-2-ffmpeg-adapter.md#12-materialize_subtitle_tracks-swallows-errors-silently) — also U5-11 |
| U3-2 | HLS segments do not require HMAC token | 3 | [HTTP mirrors service behavior](unit-3-http-sdk-proxy.md#2-hls-segments-do-not-require-hmac-token) — U1-2 |
| U3-3 | Heartbeat, stop, client-log routes lack session token | 3 | [session_id-only auth](unit-3-http-sdk-proxy.md#3-heartbeat-stop-and-client-log-routes-lack-session-token) |
| U3-4 | `SESSION_TTL_SECONDS` duplicated at six layers | 3 | [900 hard-coded outside contract](unit-3-http-sdk-proxy.md#4-session_ttl_seconds-duplicated-at-six-layers-http-uses-local-constant) — U1-6 |
| U3-5 | Heartbeat TTL reset ignores create-time TTL | 3 | [U1-3 at HTTP layer](unit-3-http-sdk-proxy.md#5-heartbeat-ttl-reset-ignores-create-time-ttl) |
| U3-6 | HMAC token outlives session `expires_at` | 3 | [U1-4 at HTTP layer](unit-3-http-sdk-proxy.md#6-hmac-token-outlives-session-expires_at) |
| U3-7 | Watch and progress routes skip LAN gate | 3 | [Metadata public while bytes gated](unit-3-http-sdk-proxy.md#7-watch-and-progress-routes-skip-lan-gate) |
| U4-3 | Startup stall detector misses post-attach phases | 4 | [`isStartupPhase` ends at attach_start](unit-4-nextjs-player.md#3-startup-stall-detector-misses-post-attach-phases) |
| U4-4 | Pre-session player logs never reach server | 4 | [Events before sessionId dropped](unit-4-nextjs-player.md#4-pre-session-player-logs-never-reach-server) |
| U4-5 | `episodeResumeMap` fetched but unused in watch UI | 4 | [Dead prop in WatchView](unit-4-nextjs-player.md#5-episoderesumemap-fetched-but-unused-in-watch-ui) — also U5-8 |
| U4-6 | `replayInFlight` suppresses stale recovery entirely | 4 | [Heartbeat 404 ignored during replay](unit-4-nextjs-player.md#6-replayinflight-suppresses-stale-recovery-entirely) |
| U4-7 | Unmount during active load skips backend stop | 4 | [Session lingers until TTL](unit-4-nextjs-player.md#7-unmount-during-active-load-skips-backend-stop) |
| U4-8 | Player logger ignores global telemetry toggle | 4 | [`NEXT_PUBLIC_TELEMETRY_ENABLED` not checked](unit-4-nextjs-player.md#8-player-logger-ignores-global-telemetry-toggle) |
| U5-2 | Next.js never sends `subtitle_track` on session create | 5 | [FormData omits subtitle](unit-5-subtitles-resume-progress.md#2-nextjs-never-sends-subtitle_track-on-session-create) |
| U5-3 | Next.js localStorage is write-only for resume | 5 | [No read before `/play`](unit-5-subtitles-resume-progress.md#3-nextjs-localstorage-is-write-only-for-resume) |
| U5-6 | Legacy still sends ignored `start_time` form field | 5 | [Stale comment implies server honors client hint](unit-5-subtitles-resume-progress.md#6-legacy-still-sends-ignored-start_time-form-field) |
| U5-7 | Client progress clamp lacks server near-end restart | 5 | [Near-end positions can persist to DB](unit-5-subtitles-resume-progress.md#7-client-progress-clamp-lacks-server-near-end-restart) |
| U5-8 | `episodeResumeMap` unused (unit 4 cross-ref) | 5 | [U4-5](unit-5-subtitles-resume-progress.md#8-episoderesumemap-fetched-but-unused-unit-4-5) |
| U5-11 | Image subtitles (PGS) silently unavailable | 5 | [U2-12](unit-5-subtitles-resume-progress.md#11-image-subtitles-pgs-silently-unavailable) |
| U5-12 | Libass sync uses raw `video.currentTime` | 5 | [Desync on anchored HLS windows](unit-5-subtitles-resume-progress.md#12-libass-sync-uses-raw-videocurrenttime) |
| U6-2 | Integration playback tests require absent machine-local fixture | 6 | [All 3 integration modules skipped](unit-6-tests-legacy-docs.md#2-integration-playback-tests-require-absent-machine-local-fixture) |
| U6-3 | Default pytest excludes HTTP playback tests | 6 | [`tests/unit/clients` ignored](unit-6-tests-legacy-docs.md#3-default-pytest-excludes-http-playback-tests) |
| U6-4 | No automated test for frozen-playhead scrub rejection | 6 | [U1-1 untested](unit-6-tests-legacy-docs.md#4-no-automated-test-for-frozen-playhead-scrub-rejection) |
| U6-5 | Next.js `use-playback.ts` has no unit/integration tests | 6 | [Load FSM / recovery untested](unit-6-tests-legacy-docs.md#5-nextjs-use-playbackts-has-no-unitintegration-tests) |
| U6-6 | `next-web/proxy.ts` XFF helper unwired | 6 | [Partial XFF in unused module; route.ts lacks IP injection](unit-6-tests-legacy-docs.md#6-next-webproxyts-xff-helper-unwired-route-handler-lacks-client-ip-injection) — extends U3-1 |

---

## Low (29)

| ID | Title | Unit | Details |
|----|-------|------|---------|
| U1-7 | `_restart_at` swallows transcoder failures | 1 | [unit-1 #7](unit-1-backend-playback.md#7-_restart_at-swallows-transcoder-failures) |
| U1-8 | `TranscodeSession.is_running` defaults True on probe failure | 1 | [unit-1 #8](unit-1-backend-playback.md#8-transcodesessionis_running-defaults-to-true-on-probe-failure) |
| U1-9 | Prefetch window uses magic `+3` vs `PREFETCH_MARGIN` | 1 | [unit-1 #9](unit-1-backend-playback.md#9-prefetch-window-uses-magic-3-instead-of-prefetch_margin) |
| U1-10 | Stale sessions only cleaned on create/resolve | 1 | [unit-1 #10](unit-1-backend-playback.md#10-stale-sessions-only-cleaned-on-createresolve) |
| U1-11 | `list_episode_files` probes every file on each call | 1 | [unit-1 #11](unit-1-backend-playback.md#11-list_episode_files-probes-every-file-on-each-call) |
| U1-12 | `player_session_log` directory locks never evicted | 1 | [unit-1 #12](unit-1-backend-playback.md#12-player_session_log-directory-locks-never-evicted) |
| U1-13 | Unknown-duration sessions disable segment guardrails | 1 | [unit-1 #13](unit-1-backend-playback.md#13-unknown-duration-sessions-disable-segment-guardrails) |
| U2-4 | `effective_subtitle_track` return field always empty | 2 | [unit-2 #4](unit-2-ffmpeg-adapter.md#4-effective_subtitle_track-return-field-is-always-empty) |
| U2-8 | `max_active_sessions` not configurable via settings | 2 | [unit-2 #8](unit-2-ffmpeg-adapter.md#8-max_active_sessions-not-configurable-via-settings) |
| U2-9 | Global `RLock` held for full spawn path | 2 | [unit-2 #9](unit-2-ffmpeg-adapter.md#9-global-rlock-held-for-full-spawn-path-including-subprocess-start) |
| U2-10 | No adapter startup health check when manifest pre-exists | 2 | [unit-2 #10](unit-2-ffmpeg-adapter.md#10-no-adapter-startup-health-check-when-canonical-manifest-pre-exists) |
| U2-11 | Failed ffprobe results not cached (tracks) | 2 | [unit-2 #11](unit-2-ffmpeg-adapter.md#11-failed-ffprobe-results-are-not-cached-tracks) |
| U2-13 | Subtitle materialization O(tracks) full-file ffmpeg reads | 2 | [unit-2 #13](unit-2-ffmpeg-adapter.md#13-subtitle-materialization-runs-otracks-full-file-ffmpeg-reads) |
| U2-14 | Input seek (`-ss` before `-i`) trades accuracy for speed | 2 | [unit-2 #14](unit-2-ffmpeg-adapter.md#14-input-seek--ss-before--i-trades-accuracy-for-speed) |
| U2-16 | Encoder detection failure assumes `libx264` available | 2 | [unit-2 #16](unit-2-ffmpeg-adapter.md#16-encoder-detection-failure-assumes-libx264-available) |
| U3-8 | Episode-files JSON API exposes absolute filesystem paths | 3 | [unit-3 #8](unit-3-http-sdk-proxy.md#8-episode-files-json-api-exposes-absolute-filesystem-paths) |
| U3-9 | `player_allow_public` / allowlist undocumented in settings template | 3 | [unit-3 #9](unit-3-http-sdk-proxy.md#9-player_allow_public--allowlist-undocumented-in-settings-template) |
| U3-10 | `X-Forwarded-For` trusted without proxy allowlist | 3 | [unit-3 #10](unit-3-http-sdk-proxy.md#10-x-forwarded-for-trusted-without-proxy-allowlist) |
| U3-11 | Manifest missing token returns HTTP 422, not 401 | 3 | [unit-3 #11](unit-3-http-sdk-proxy.md#11-manifest-missing-token-returns-http-422-not-401) |
| U3-12 | `client_host` on session is proxy address in web mode | 3 | [unit-3 #12](unit-3-http-sdk-proxy.md#12-client_host-on-session-is-proxy-address-in-web-mode) |
| U4-9 | Recovery counter not reset on manual retry after exhaustion | 4 | [unit-4 #9](unit-4-nextjs-player.md#9-recovery-attempt-counter-not-reset-on-manual-retry-after-exhaustion) |
| U4-10 | Segment HTTP errors do not trigger stale recovery | 4 | [unit-4 #10](unit-4-nextjs-player.md#10-segment-http-errors-do-not-trigger-stale-recovery) |
| U4-11 | Session-guard test gap for load-start teardown | 4 | [unit-4 #11](unit-4-nextjs-player.md#11-session-guard-test-gap-for-load-start-teardown) |
| U4-12 | `LoadPhase` type incomplete | 4 | [unit-4 #12](unit-4-nextjs-player.md#12-loadphase-type-incomplete) |
| U4-13 | Heartbeat errors swallowed | 4 | [unit-4 #13](unit-4-nextjs-player.md#13-heartbeat-errors-swallowed) |
| U5-10 | Auto-enables first subtitle track after session load | 5 | [unit-5 #10](unit-5-subtitles-resume-progress.md#10-auto-enables-first-subtitle-track-after-session-load) |
| U5-13 | Progress POST errors swallowed | 5 | [unit-5 #13](unit-5-subtitles-resume-progress.md#13-progress-post-errors-swallowed) |
| U5-14 | `toAbsoluteSourceSeconds` has no unit tests | 5 | [unit-5 #14](unit-5-subtitles-resume-progress.md#14-toabsolutesourceseconds-has-no-unit-tests) — also U6-8 |
| U6-8 | `toAbsoluteSourceSeconds` / `clampPlaybackSeconds` untested in vitest | 6 | [unit-6 #8](unit-6-tests-legacy-docs.md#8-toabsolutesourceseconds-and-clampplaybackseconds-untested-in-vitest) |
| U6-10 | AGENTS.md omits test-run caveats for playback | 6 | [unit-6 #10](unit-6-tests-legacy-docs.md#10-agentsmd-omits-test-run-caveats-for-playback) |

---

## Info (13)

| ID | Title | Unit | Details |
|----|-------|------|---------|
| U1-14 | In-memory session store — no cross-process sharing | 1 | [unit-1 #14](unit-1-backend-playback.md#14-in-memory-session-store--no-cross-process-sharing) |
| U1-15 | `MediaStreamingService` alias retained | 1 | [unit-1 #15](unit-1-backend-playback.md#15-mediastreamingservice-alias-retained) |
| U1-16 | FFmpeg adapter drops `subtitle_track` on session record | 1 | [unit-1 #16 → unit 2](unit-1-backend-playback.md#16-cross-layer-note--ffmpeg-adapter-drops-subtitle_track-on-session-record) |
| U2-15 | Backward seek segment purge path lacks regression test | 2 | [unit-2 #15](unit-2-ffmpeg-adapter.md#15-backward-seek-segment-purge-path-lacks-regression-test) |
| U2-17 | `settings.json` playback section minimal vs AGENTS.md | 2 | [unit-2 #17](unit-2-ffmpeg-adapter.md#17-settingsjson-playback-section-minimal-vs-agentsmd) |
| U3-13 | Proxy timeout aligned with resume wait (positive) | 3 | [240s vs 180s — OK](unit-3-http-sdk-proxy.md#13-proxy-timeout-aligned-with-resume-wait-informational-positive) |
| U3-14 | No JSON REST playback API | 3 | [By design — `/ui/*`](unit-3-http-sdk-proxy.md#14-no-json-rest-playback-api) |
| U3-15 | SDK / facade add no playback policy | 3 | [LAN gate HTTP-only](unit-3-http-sdk-proxy.md#15-sdk--facade-add-no-playback-policy) |
| U4-14 | Audio track change replays; subtitle change does not | 4 | [By design](unit-4-nextjs-player.md#14-audio-track-change-replays-subtitle-change-does-not) |
| U4-15 | Module-global `playbackLoadEpoch` complicates testing | 4 | [Fast Refresh tradeoff](unit-4-nextjs-player.md#15-module-global-playbackloadepoch-complicates-testing) |
| U4-16 | Stale recovery timing constants documented | 4 | [3 attempts, 250ms debounce](unit-4-nextjs-player.md#16-stale-recovery-timing-constants) |
| U6-7 | Vitest suite not runnable without `npm install` | 6 | [unit-6 #7](unit-6-tests-legacy-docs.md#7-vitest-suite-not-runnable-without-npm-install) |
| U6-9 | Legacy HTMX retains high-severity resume/progress bugs | 6 | [Spot-check confirms U5 #4–#6](unit-6-tests-legacy-docs.md#9-legacy-htmx-player-retains-high-severity-resumeprogress-bugs) |

---

## Top cross-layer themes

1. **Security / access (U3-1, U1-2, U3-2, U6-6):** Web-mode proxy collapses client identity; segment URLs need no token; optional unwired XFF helper.
2. **Resume alignment (U1-1, U4-2, U5-4, U5-5, U5-9):** Frozen playhead, legacy Shaka vs encode mismatch, wrong progress times, status wipe.
3. **Subtitles (U2-1, U5-1, U5-11, U5-12):** Sidecar-only; burn-in param misleading; PGS silent; libass desync on anchor.
4. **Session lifecycle (U4-1, U4-7, U1-3, U2-6):** Orphan sessions, TTL drift, eviction without notification.
5. **Docs & tests (U6-1, U6-2, U6-3, U6-4, U6-5):** Stale RST doc, skipped integration, coverage holes on highest-severity bugs.

---

## Verification commands (unit 6)

```powershell
# Default playback unit suite (69 tests)
.\.venv\Scripts\python.exe -m pytest tests/unit/playback/ tests/unit/adapters/media/ `
  tests/unit/components/test_media_streaming_service.py `
  tests/unit/components/test_player_session_log.py -q --no-cov

# HTTP playback tests (not in default pytest)
.\.venv\Scripts\python.exe -m pytest tests/unit/clients/test_http_web_ui.py -q --no-cov -k "play or stream"

# Integration (requires local SubsPlease MKV fixture)
.\.venv\Scripts\python.exe -m pytest tests/integration/test_playback_*.py -q --no-cov

# Next.js vitest (requires cd next-web && npm install)
cd next-web; npm test
```

---

## Unit documents

- [Unit 1 — Backend playback core](unit-1-backend-playback.md)
- [Unit 2 — FFmpeg transcoder & encoder](unit-2-ffmpeg-adapter.md)
- [Unit 3 — HTTP / SDK / proxy](unit-3-http-sdk-proxy.md)
- [Unit 4 — Next.js Shaka player](unit-4-nextjs-player.md)
- [Unit 5 — Subtitles, resume & progress](unit-5-subtitles-resume-progress.md)
- [Unit 6 — Tests, legacy, docs](unit-6-tests-legacy-docs.md)
