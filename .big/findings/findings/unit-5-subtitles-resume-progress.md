# Unit 5 — Subtitles, resume & progress audit

## Scope and method

**Audited (read-only):**

- `application/playback/resume.py`, `contract.py` — resume math, clamps, anchor segments
- `application/playback/service.py` — session create with `start_time_seconds`, subtitle materialization
- `adapters/persistence/user_actions_repository.py` — `episode_progress` table
- `application/services/anime_service.py` — progress merge into `list_episode_files`
- `clients/http/web.py` — `/play`, `/episode-progress`, watch JSON context
- `next-web/lib/playback/progress.ts`, `subtitles.ts`, `use-playback.ts`, `shaka.ts`, `session-api.ts`
- `next-web/components/player/SubtitleBridge.tsx`, `WatchView.tsx`, `VideoPlayer.tsx`
- `next-web/app/anime/[id]/watch/page.tsx`, `EpisodePlayerTable.tsx`
- `clients/http/static/js/app.js` — legacy resume/progress/subtitle paths (comparison)
- Cross-ref: unit 2 (`subtitle_track` no-op), unit 4 (`episodeResumeMap` dead)

**Out of scope:** FFmpeg command internals (unit 2), Shaka load FSM / stale recovery (unit 4), HTTP LAN policy (unit 3).

**Method:** Static E2E trace DB → `/play` → Shaka → progress POST; compare Next.js vs legacy HTMX behavior.

---

## Resolved open item: subtitle burn-in vs sidecar

**Actual behavior: sidecar-only (client-rendered), not burn-in.**

| Layer | Behavior |
|-------|----------|
| **Transcode** | HLS video has **no** burned-in subtitles. `subtitle_track` on `CreatePlaybackSessionCommand` is passed to `TranscodeSession.start` but ffmpeg `_build_command` ignores it (unit 2 #1). |
| **Session create** | After transcode starts, `PlaybackService._materialize_subtitles` extracts **WebVTT sidecars** per text track and optional **ASS copies** for SSA/ASS codecs (`ffmpeg_transcoder.py:632-723`). |
| **HTTP `/play` response** | Each track gets `url` (VTT) and optional `ass_url`; fields `subtitle_requested` / `subtitle_applied` expose the form param vs stored session value (applied is always unused for encode). |
| **Next.js player** | `attachSubtitleTracks` → Shaka `addTextTrackAsync` (VTT). `applySubtitleSelection` prefers **libass SubtitlesOctopus** when `ass_url` exists and WASM is available; otherwise Shaka text track. Shaka native cues hidden while libass active (`subtitles.ts:53-145`, `SubtitleBridge.tsx`). |
| **Legacy HTMX** | Same sidecar model; subtitle `<select>` changes call `applySubtitleSelection()` in-place — **no** new `/play` (correct for sidecars). |

**Intent inference:** Sidecar + libass for styled ASS is the **designed** path. The `subtitle_track` form field and DTO field look like a **planned burn-in feature** that was never wired (unit 2 #1, #4). Operators should not expect soft-sub selection to affect the encoded HLS video stream.

---

## E2E resume trace

```text
episode_progress (SQLite/MySQL)
  └─ user_actions_repository.get_episode_progress_map
       └─ anime_service.list_episode_files (merges position_seconds, watch_status)
            └─ POST /ui/anime/{id}/play  [web.py:1662-1695]
                 └─ start_time_seconds if DB position ≥ 10s
                      └─ sdk.create_playback_session(start_time_seconds=…)
                           └─ PlaybackService.create_session
                                ├─ clamp_resume_seconds (MIN 10s, NEAR_END 15s restart)
                                ├─ resume_segment_index → hls_anchor_segment
                                ├─ transcode from anchor segment
                                └─ DTO.playback_start_seconds
                                     └─ JSON { playback_start_seconds, hls_anchor_segment, segment_seconds, … }
                                          └─ use-playback loadPlayback
                                               ├─ loadStartTimeFromPayload → player.load(manifest, loadStartTime)
                                               └─ postEpisodeProgress on resume if playback_start_seconds > 0

During playback:
  video timeupdate → saveLocalPosition (localStorage)
                   → maybePostProgressThrottled (≥5s, not paused, 20s throttle)
                   → POST /ui/anime/{id}/episode-progress { file_id, status, position_seconds }
                        └─ set_episode_progress → episode_progress UPDATE/INSERT
```

### Key thresholds

| Constant | Value | Where applied |
|----------|-------|---------------|
| `MIN_RESUME_SECONDS` | 10 | Server resume (`resume.py`, `web.py:1673`) |
| `NEAR_END_RESTART_SECONDS` | 15 | Server only — `clamp_resume_seconds` restarts near-end to 0 |
| Progress POST minimum | 5s video time | Client `maybePostProgressThrottled` |
| Server POST throttle | 20s | `createProgressReporter` |
| Pause / ended POST | immediate | `onPause` (if t>5), `onEnded` (SEEN) |

### Shaka start time

- `loadStartTimeFromPayload` returns `playback_start_seconds` when > 0, else `undefined`; caller passes `?? 0` for fresh starts to avoid live-edge seek on EVENT manifests (`shaka.ts:31-36`, `use-playback.ts:428-433`, `:560`).
- `buildShakaConfig(resume)` sets `segmentPrefetchLimit: 0` on resume to reduce far-ahead probes (`shaka.ts:4-7`).

### Anchored HLS progress conversion (Next.js only)

When `hls_anchor_segment > 0`, manifest time may be offset. Next.js converts before server POST and localStorage via `toAbsoluteSourceSeconds` (`progress.ts:16-34`, `use-playback.ts:134-141`). Legacy HTMX uses raw `video.currentTime` (finding #5).

---

## localStorage vs server divergence

| Store | Key | Written | Read for resume | Authority |
|-------|-----|---------|-----------------|-----------|
| **localStorage** | `animePlayer:{animeId}:{fileId}` | Next.js + legacy on timeupdate | Legacy: yes (merged with server map); Next.js: **never** | Cache only |
| **episode_progress DB** | `(anime_id, user_id, file_id)` | POST `/episode-progress`, `/play` side effects | `/play` on both UIs (server-side) | **Source of truth for ffmpeg anchor** |

**Divergence scenarios:**

1. **Next.js write-only localStorage** — progress saved locally every timeupdate but resume always from DB on next `/play`. Stale localStorage after cross-device or DB-ahead reload is harmless (unused). If DB POST fails/throttles, resume lags behind what user watched (#3).
2. **Legacy merges max(localStorage, serverResumeMap) for Shaka `load()`** but `/play` ignores client `start_time` (tests: `test_play_ignores_client_start_time_even_when_higher`) — ffmpeg starts at **DB only**. If localStorage > DB, Shaka seeks ahead of encoded segments (#4).
3. **Legacy sends obsolete `start_time` form field** — ignored by server; comment at `app.js:872-875` is stale (#6).
4. **Client vs server clamp** — client `clampPlaybackSeconds` allows up to `duration × 1.1`; server `clamp_resume_seconds` clears positions within 15s of end. Client can persist near-end corruption; server clears on next play (#7).
5. **20s server throttle vs continuous localStorage** — up to ~20s gap between stores on Next.js; legacy same for server, localStorage continuous (#8).

---

## Findings

### 1. Subtitle burn-in parameter is end-to-end no-op

- **Severity:** high
- **Title:** `subtitle_track` on `/play` does not affect ffmpeg output — sidecar-only architecture
- **Evidence:** Unit 2 #1; `web.py:1753-1754` returns `subtitle_requested` / `subtitle_applied`; `PlaybackService.create_session` passes `subtitle_track` to transcode but encode ignores it
- **Cross-ref:** Unit 2 findings #1, #2, #3, #4
- **Expected vs actual:** Form param suggests burned-in HLS subs. Actual: WebVTT/ASS sidecars only; video stream never includes selected subs.
- **Suggested fix:** Remove param or implement burn-in; until then document in UI that subtitles are overlay-only.

---

### 2. Next.js never sends `subtitle_track` on session create

- **Severity:** medium
- **Title:** `createSession` FormData omits subtitle selection — server always gets `subtitle_idx=None`
- **Evidence:** `use-playback.ts:399-401` sets only `file_id` and `audio_track`; subtitle changes use in-player `applySubtitleSelection` only
- **Note:** Correct for sidecar model today; misleading given `/play` accepts `subtitle_track` and response includes `subtitle_requested`.
- **Suggested fix:** Either stop advertising `subtitle_track` on API or pass selection for future burn-in/logging.

---

### 3. Next.js localStorage is write-only for resume

- **Severity:** medium
- **Title:** `saveLocalPosition` writes cache; no `readLocalPosition` — resume is DB-only
- **Evidence:** `progress.ts:56-76` write path only; `use-playback.ts:399-405` never reads localStorage before `/play`; server loads resume at `web.py:1662-1675`
- **Repro:** Watch 30 minutes; clear DB row; reload — resumes at 0 despite localStorage value.
- **Expected vs actual:** localStorage key matches legacy naming but serves no resume purpose in Next.js. Orphan writes on every timeupdate.
- **Suggested fix:** Remove dead writes, or read max(localStorage, server) before play like legacy (with server agreement on encode start).

---

### 4. Legacy resume: Shaka load position can exceed ffmpeg encode start

- **Severity:** high
- **Title:** Client merges localStorage + server map for Shaka; server encodes from DB only
- **Evidence:** `app.js:503-527` `readResumeSeconds` → `Math.max(local, server)`; `app.js:876` `shakaPlayer.load(manifestUrl, resumeSeconds)`; `web.py:1662-1675` DB-only `start_time_seconds`; tests confirm client `start_time` form ignored
- **Repro:** localStorage at 1800s, DB at 600s — ffmpeg encodes from ~600s; Shaka seeks to 1800s → buffer/segment failures until seek-on-demand catches up.
- **Suggested fix:** Use `payload.playback_start_seconds` for Shaka load (like Next.js), or re-enable trusted client start_time when higher than DB after merge policy review.

---

### 5. Legacy progress POST uses manifest-relative time on anchored resume

- **Severity:** high
- **Title:** No `toAbsoluteSourceSeconds` equivalent — wrong DB positions after mid-file resume
- **Evidence:** `app.js:456-463`, `:1012-1025` — raw `video.currentTime`; Next.js uses anchor-aware conversion (`use-playback.ts:134-141`)
- **Repro:** Resume at 708s (anchor segment 175); video reports small relative times early in window — legacy POSTs ~0–8s positions, overwriting DB resume.
- **Suggested fix:** Port `toAbsoluteSourceSeconds` to legacy player or share module.

---

### 6. Legacy still sends ignored `start_time` form field

- **Severity:** medium
- **Title:** Dead client field + stale comment imply server honors client resume hint
- **Evidence:** `app.js:693-697` sets `start_time`; `web.py:1636-1643` form has no `start_time` param; comment `app.js:872-875`; `test_http_web_ui.py:1561-1571`
- **Suggested fix:** Remove form field and update comments; rely on DB + immediate progress POST after load.

---

### 7. Client progress clamp lacks server near-end restart

- **Severity:** medium
- **Title:** Bogus near-end positions can be persisted to DB from client
- **Evidence:** Server `clamp_resume_seconds` + `NEAR_END_RESTART_SECONDS=15` (`resume.py:53-54`, `contract.py:14`); client `clampPlaybackSeconds` only caps at `maxSeconds * 1.1` (`progress.ts:7-13`) — no near-end reset
- **Cross-ref:** `test_contract.py:178-195` documents server fix for live-edge corruption; client never applies same rule
- **Repro:** Player reports time 12s before end → client POST persists → DB stores; server clears on next play but watch UI shows wrong % until then.
- **Suggested fix:** Mirror `NEAR_END_RESTART_SECONDS` in `clampPlaybackSeconds` when `maxSeconds` known.

---

### 8. `episodeResumeMap` fetched but unused (unit 4 #5)

- **Severity:** medium
- **Title:** Watch page loads resume map; player never consumes it
- **Evidence:** `watch/page.tsx:54`; `WatchView.tsx:25` destructures unused; resume only via server `/play` DB lookup
- **Cross-ref:** Unit 4 finding #5
- **Suggested fix:** Show resume hints in `EpisodePicker` or remove prop.

---

### 9. Manual status change clears stored position

- **Severity:** high
- **Title:** `EpisodePlayerTable` POSTs status-only — repository writes `position_seconds=NULL`
- **Evidence:** `EpisodePlayerTable.tsx:40-43` — no `position_seconds`; `user_actions_repository.py:315-336` sets `pos_val=None` → UPDATE clears column
- **Repro:** Watch halfway; on detail page change status dropdown to "Seen" — resume position wiped; next play starts near 0 (unless status logic differs).
- **Suggested fix:** Omit `position_seconds` from UPDATE when not provided (COALESCE), or send current position from UI.

---

### 10. Auto-enables first subtitle track after session load

- **Severity:** low
- **Title:** Payload hook selects first subtitle even when UI default is "Off"
- **Evidence:** `use-playback.ts:601-607` — if `payloadSubs[0]` exists, sets `activeSubId` and applies; initial `subtitleTrackId` is `""`; `VideoPlayer.tsx:203` shows "Off" option first
- **Repro:** Brief flash or mismatch: selector may show Off while libass/VTT already active until state sync.
- **Suggested fix:** Default to Off unless user preference stored; align selector with applied track.

---

### 11. Image subtitles (PGS) silently unavailable

- **Severity:** medium
- **Title:** Materialization skips non-text codecs with no user feedback
- **Evidence:** Unit 2 #12 — `materialize_subtitle_tracks` stderr discarded; tracks without VTT file omitted from payload
- **Repro:** MKV with PGS only — empty subtitle list; player shows no subs, no error.
- **Suggested fix:** Return track metadata with `available: false` and surface in UI.

---

### 12. Libass sync uses raw `video.currentTime`

- **Severity:** medium
- **Title:** SubtitlesOctopus may desync on anchored HLS resume windows
- **Evidence:** `SubtitleBridge.tsx:80-99` — `setCurrentTime(video.currentTime)`; ASS cues are authored in absolute source time
- **Cross-ref:** Progress conversion handles anchor in Next.js; libass path does not
- **Suggested fix:** Pass absolute source seconds (same helper as progress) into libass sync.

---

### 13. Progress POST errors swallowed

- **Severity:** low
- **Title:** Client fire-and-forget; server logs warning and returns HTML partial
- **Evidence:** `progress.ts:100` `void uiPost(...)`; `web.py:1458-1459` logs warning; no client retry
- **Suggested fix:** Log client-side failure; optional retry queue for IN_PROGRESS updates.

---

### 14. `toAbsoluteSourceSeconds` has no unit tests

- **Severity:** low
- **Title:** Anchor conversion is critical for resume accuracy but untested in vitest
- **Evidence:** `progress.test.ts` only covers `shouldRecoverTimelineJump`; no cases for `anchor > 0` branch
- **Suggested fix:** Add vitest cases mirroring server resume segment math.

---

### 15. Positive design notes (non-findings)

- **Server-authoritative resume for Next.js** — `/play` reads DB only; Shaka `loadStartTime` from `playback_start_seconds` keeps encode start and player seek aligned (`use-playback.ts:426-433`, `:560`).
- **Resume segment wait** — `PlaybackService` blocks session create until playhead segment exists (`service.py:196-207`).
- **Subtitle sidecar + libass** — sensible split: VTT for plain text, ASS sidecar + WASM for styled subs without re-encode.
- **Legacy subtitle change without replay** — correct for sidecar architecture (`app.js:1004-1009`).

---

## Cross-layer matrix

| Issue | Unit | Severity |
|-------|------|----------|
| `subtitle_track` ffmpeg no-op | 2 #1 | high |
| `episodeResumeMap` dead | 4 #5 | medium |
| Legacy resume / DB mismatch | 5 #4 | high |
| Anchor progress (legacy) | 5 #5 | high |
| Next.js localStorage orphan | 5 #3 | medium |

---

## Summary counts

| Severity | Count |
|----------|-------|
| critical | 0 |
| high | 4 |
| medium | 6 |
| low | 3 |
| info | 0 |

**Total:** 13 findings (+ positive design section)

*(Open item “subtitle burn-in vs sidecar” resolved in dedicated section above — sidecar-only, burn-in not implemented.)*

---

## Criteria mapping

| Criterion | Status |
|-----------|--------|
| E2E resume/progress trace | ✅ Diagram + thresholds |
| localStorage vs server divergence | ✅ Table + scenarios |
| Subtitle burn-in vs sidecar | ✅ Resolved — sidecar-only documented |
| Cross-ref unit 2 `subtitle_track` | ✅ Findings #1, #2 |
| Cross-ref unit 4 `episodeResumeMap` | ✅ Finding #8 |

---

## Verification

Audit-only — no test commands required. Cross-checked against `tests/unit/clients/test_http_web_ui.py` play resume tests and `tests/unit/playback/test_contract.py` clamp tests (static review).
