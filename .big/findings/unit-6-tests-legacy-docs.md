# Unit 6 — Tests, legacy spot-check, docs & master index

## Scope and method

**Audited (read-only):**

- `tests/unit/playback/**` — contract, file_ids (11 tests)
- `tests/unit/adapters/media/**` — ffmpeg encoder + transcoder (29 tests)
- `tests/unit/components/test_media_streaming_service.py` — PlaybackService integration (28 tests)
- `tests/unit/components/test_player_session_log.py` — JSONL logging (2 tests)
- `tests/unit/clients/test_http_web_ui.py` — playback/stream routes (22 tests; **excluded from default pytest**)
- `tests/integration/test_playback_*.py` — real ffmpeg + SubsPlease fixture (3 files)
- `next-web/lib/playback/*.test.ts` — vitest session-guard + progress (8 cases)
- `clients/http/templates/watch_episode.html`, `clients/http/static/js/app.js` — legacy HTMX spot-check
- `docs/features/media_playback.rst` vs `AGENTS.md` playback section
- `next-web/proxy.ts` vs `next-web/app/backend/[...path]/route.ts` — XFF forwarding gap (unit 3 supplement)
- Cross-ref: units 1–5 findings (synthesized into master [README.md](README.md))

**Out of scope:** Re-auditing backend/player stack; full legacy JS line-by-line review.

**Method:** Coverage matrix, pytest run, integration skip check, vitest availability check, HTMX divergence spot-check vs Next.js, doc drift analysis.

---

## Verification run

| Command | Result |
|---------|--------|
| `pytest tests/unit/playback/ tests/unit/adapters/media/ tests/unit/components/test_media_streaming_service.py tests/unit/components/test_player_session_log.py -q --no-cov` | **69 passed** in ~7.5s |
| `pytest tests/integration/test_playback_*.py -q --no-cov` | **0 ran** — all skipped (fixture absent) |
| `npm test` / vitest | **Skipped** — `next-web/node_modules` absent in worktree |

---

## Coverage matrix

| Area | Test location | Cases | Gaps vs known bugs |
|------|---------------|-------|-------------------|
| Resume math / clamps | `test_contract.py`, `test_media_streaming_service.py` | ✅ anchor, near-end, MIN_RESUME | — |
| Playlist manifest | `test_contract.py` | ✅ render_manifest | — |
| File ID hashing | `test_file_ids.py` | ✅ | — |
| FFmpeg seek restart | `test_ffmpeg_transcoder.py` | ✅ input seek, keyframes, forward no-purge | ❌ backward purge untested (unit 2 #15) |
| Encoder selection | `test_ffmpeg_encoder.py` | ✅ auto, forced-IDR per HW | ❌ `h264_mf` IDR gap not asserted |
| `subtitle_track` param | `test_ffmpeg_transcoder.py:69-71` | ✅ asserts **no** `-vf` | Documents no-op; no burn-in test |
| PlaybackService create/wait/resolve | `test_media_streaming_service.py` | ✅ resume wait, seek restart, token | ❌ frozen playhead / speculative far-ahead (unit 1 #1); ❌ tokenless segment path; ❌ heartbeat TTL shrink |
| Session store / transcode_session | — | **none** | Isolated modules untested |
| HTTP play/stream/LAN | `test_http_web_ui.py` | 22 playback-related | Default pytest **ignores** `tests/unit/clients`; tokenless segment **intentionally** tested |
| Integration E2E ffmpeg | `test_playback_subsplease_ep11.py`, `test_playback_diagnostics.py`, `test_playback_gpu_encoder.py` | Skipped without fixture | No CI-portable fixture path |
| Next.js session-guard | `session-guard.test.ts` | 4 cases | ❌ load-start teardown case (unit 4 #11) |
| Next.js progress | `progress.test.ts` | 4 timeline-jump cases | ❌ `toAbsoluteSourceSeconds` / anchor (unit 5 #14); ❌ `clampPlaybackSeconds` near-end |
| Next.js use-playback / shaka / subtitles | — | **none** | Load FSM, stale recovery, heartbeat-after-failure (unit 4 #1–#2) |
| Playwright smoke | `npm run test:playback-smoke` | script exists | Not run (no node_modules) |
| Player session log | `test_player_session_log.py` | 2 | ❌ unbounded `_dir_locks` (unit 1 #12) |

**Summary:** Backend unit coverage is strong for happy-path HLS and seek-restart; highest-risk gaps align with unit 1 #1 (scrub-ahead), unit 3 #1 (LAN/proxy), unit 4 #1–#2 (client lifecycle), unit 5 #4–#5 (legacy resume/progress).

---

## Integration fixture status

All three integration modules share one **machine-local** path:

```text
C:\Users\willi\Documents\Anime\Animes\Classroom of the Elite …\S4 - 11 (720p) [7CA0682C].mkv
```

- `pytestmark = skipif(not EPISODE_PATH.is_file(), …)` — no repo-bundled fixture, no env override.
- On this machine: **fixture absent** → `no tests ran` (exit 5).
- No `tests/integration/fixtures/` directory in repo.

**Suggested fix:** Ship a tiny synthetic MKV in repo or document `PLAYBACK_FIXTURE_PATH` env var for CI/local.

---

## Frontend test status

- `next-web/node_modules`: **missing** in worktree → vitest not executed.
- Existing vitest: `session-guard.test.ts` (4), `progress.test.ts` (4) — 8 cases total.
- No component tests for `WatchView`, `VideoPlayer`, `use-playback.ts`.
- `package.json` scripts: `test`, `test:session-guard`, `test:playback-smoke` (Playwright).

---

## Legacy HTMX spot-check (divergences only)

Compared `watch_episode.html` + `app.js` player block to Next.js `use-playback.ts` / unit 5 trace.

| Topic | Legacy HTMX | Next.js | Severity ref |
|-------|-------------|---------|--------------|
| Resume source for `/play` | DB only (server) | DB only | ✅ aligned |
| Shaka `load()` start time | `readResumeSeconds` → max(localStorage, server map) | `playback_start_seconds` from payload | **U5 #4** high |
| Progress POST time base | raw `video.currentTime` | `toAbsoluteSourceSeconds` when anchored | **U5 #5** high |
| `start_time` form field | sent but **ignored** by server | not sent | **U5 #6** medium |
| `episode_resume_map` | template `data-episode-resume-map` → `serverResumeMap` used | fetched but **unused** in WatchView | **U4 #5 / U5 #8** medium |
| Subtitle change | in-place `applySubtitleSelection`, no replay | same | ✅ aligned (sidecar model) |
| Audio change | `queueReplayCurrent()` | `queueReplayCurrent()` | ✅ aligned |
| Stale session recovery | none observed | manifest 404 + heartbeat 404, max 3 | Next.js only |
| Startup failure + heartbeat | not audited in depth | heartbeat after Shaka fail | **U4 #1** high |
| Timeline jump guard | none | `shouldRecoverTimelineJump` | Next.js only |
| localStorage resume | read + write | write-only | **U5 #3** medium |

Legacy comment at `app.js:872-875` claims server encoder started at client offset; server actually ignores client `start_time` and uses DB only — comment is **stale/misleading**.

---

## Doc drift

### `docs/features/media_playback.rst` — obsolete (critical doc drift)

- Describes **shell-launched external players** (`mpv`, `vlc`, `ffplay`) and empty `adapters/media` namespace.
- References deleted `media_players/` package, future `MediaPlayerPort`, Discord presence removal.
- **Does not mention** HLS, FFmpeg transcoder, Shaka, Next.js watch UI, session tokens, or `/ui/stream/*` routes.
- Contradicts current `AGENTS.md` § Playback and streaming and actual `adapters/media/ffmpeg_*.py`.

### `AGENTS.md` playback section — mostly accurate

- Correctly documents HLS stack, routes, segment cadence, encoder settings, Next.js proxy 240s timeout.
- **Omits:** legacy HTMX resume divergences (U5 #4–#6), integration fixture requirement, `next-web/proxy.ts` vs route handler XFF gap, default pytest ignoring HTTP client tests.

### `settings.json` template vs docs

- Cross-ref unit 2 #17, unit 3 #9 — playback section minimal; `web.player_allow_public` absent.

---

## Supplement: `next-web/proxy.ts` (unit 3 gap)

Unit 3 documented LAN bypass via `route.ts` not forwarding client IP. Additional note:

- **`next-web/proxy.ts`** exports middleware-style `proxy()` that sets `x-forwarded-for` from incoming `x-forwarded-for` / `x-real-ip` (partial chain preservation).
- **`next-web/app/backend/[...path]/route.ts`** is the **actual** backend proxy — forwards headers but does **not** inject browser IP when absent.
- **No `middleware.ts`** found in worktree — `proxy.ts` appears **unwired**; Next.js 16 `proxy.ts` at package root may not be active without explicit middleware registration.
- Even if wired, logic only forwards **existing** upstream XFF — direct browser→Next.js connections still lack client IP unless Next dev injects it.

Cross-ref: [unit-3-http-sdk-proxy.md](unit-3-http-sdk-proxy.md) finding #1, #12.

---

## Unit 6 findings

### 1. `docs/features/media_playback.rst` describes pre-HLS architecture

- **Severity:** high (contributor-facing doc drift)
- **Title:** Feature doc still documents shell-exec external players, not in-app HLS
- **Evidence:** `docs/features/media_playback.rst:1-149` — subprocess mpv/vlc; `adapters/media` “empty namespace”; no FFmpeg/Shaka
- **Expected vs actual:** Doc should describe current HLS pipeline or redirect to AGENTS.md. Actual: actively misleading for new contributors.
- **Suggested fix:** Rewrite `media_playback.rst` for HLS stack or add deprecation banner + link to AGENTS.md.

---

### 2. Integration playback tests require absent machine-local fixture

- **Severity:** medium
- **Title:** No portable integration fixture — entire suite skipped on clean/CI machines
- **Evidence:** `tests/integration/test_playback_subsplease_ep11.py:10-21`; run result `no tests ran`
- **Suggested fix:** Repo fixture or env-configurable path; mark slow + optional in CI.

---

### 3. Default pytest excludes HTTP playback tests

- **Severity:** medium
- **Title:** `pytest.ini` ignores `tests/unit/clients` — 22 stream/play tests not in default run
- **Evidence:** `pytest.ini` `--ignore=tests/unit/clients`; `test_http_web_ui.py` playback tests exist
- **Repro:** `pytest` green while LAN/token/stream regressions in HTTP layer untested by default.
- **Suggested fix:** Document in AGENTS.md; or move playback HTTP tests under `tests/unit/backend/`.

---

### 4. No automated test for frozen-playhead scrub rejection

- **Severity:** medium
- **Title:** Unit 1 #1 high finding has zero regression test
- **Evidence:** grep `speculative|too far ahead` in `tests/` — no matches; `test_media_streaming_service.py` covers seek restart but not far-ahead guard
- **Cross-ref:** [unit-1-backend-playback.md](unit-1-backend-playback.md) #1
- **Suggested fix:** Add test: resume session, request segment > MAX_FORWARD_JUMP beyond initial anchor → expect restart or NotFound.

---

### 5. Next.js `use-playback.ts` has no unit/integration tests

- **Severity:** medium
- **Title:** Core player hook untested — load FSM, stale recovery, heartbeat paths
- **Evidence:** no `use-playback.test.ts`; vitest only covers `session-guard` + `progress` helpers
- **Cross-ref:** unit 4 findings #1, #2, #7
- **Suggested fix:** Extract testable pure functions or add vitest with mocked fetch/Shaka.

---

### 6. `next-web/proxy.ts` XFF helper unwired; route handler lacks client IP injection

- **Severity:** medium
- **Title:** Partial XFF forwarding exists in dead/unused proxy module
- **Evidence:** `next-web/proxy.ts:16-23`; `route.ts:17-22` deletes host only; no `middleware.ts`
- **Cross-ref:** unit 3 #1, #12
- **Suggested fix:** Wire middleware or merge XFF logic into route handler; trust only proxy hops.

---

### 7. Vitest suite not runnable without `npm install`

- **Severity:** info
- **Title:** Worktree lacks `node_modules` — 8 vitest cases unverified this audit
- **Evidence:** `Test-Path next-web/node_modules` → False
- **Note:** Static review of `session-guard.test.ts` / `progress.test.ts` only.

---

### 8. `toAbsoluteSourceSeconds` and `clampPlaybackSeconds` untested in vitest

- **Severity:** low
- **Title:** Anchor-aware progress helpers lack unit tests
- **Evidence:** `progress.test.ts` — only `shouldRecoverTimelineJump`; unit 5 #14
- **Suggested fix:** Add cases mirroring server resume segment math.

---

### 9. Legacy HTMX player retains high-severity resume/progress bugs

- **Severity:** info (spot-check confirmation)
- **Title:** Legacy watch path not parity with Next.js for resume alignment
- **Evidence:** `app.js:503-527`, `:693-697`, `:876`, `:1012-1025`; see spot-check table
- **Cross-ref:** unit 5 #4, #5, #6
- **Note:** HTMX still shipped under `/ui/anime/{id}/watch` when Next.js redirect disabled.

---

### 10. AGENTS.md omits test-run caveats for playback

- **Severity:** low
- **Title:** Testing section does not mention client-test ignore or integration fixture
- **Evidence:** `AGENTS.md` § Testing — no `tests/unit/clients` note for playback; no integration fixture path
- **Suggested fix:** Add subsection under Testing for playback verification checklist.

---

## Summary counts (unit 6 only)

| Severity | Count |
|----------|-------|
| critical | 0 |
| high | 1 |
| medium | 5 |
| low | 2 |
| info | 2 |

**Total:** 10 unit-6 findings

---

## Criteria mapping

| Criterion | Status |
|-----------|--------|
| Coverage matrix | ✅ Table + gap mapping to units 1–5 |
| Legacy spot-check | ✅ Divergence table (HTMX vs Next.js) |
| Doc drift | ✅ `media_playback.rst`, AGENTS.md gaps |
| Master findings index | ✅ [README.md](README.md) |
| Integration fixture note | ✅ Absent — skipped |
| proxy.ts XFF supplement | ✅ Finding #6 |
| pytest run | ✅ 69 passed |
| vitest/npm | ✅ Skipped — noted |
