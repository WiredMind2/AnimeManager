# Unit 2 — FFmpeg transcoder & encoder audit

## Scope and method

**Audited (read-only):**

- `adapters/media/ffmpeg_transcoder.py` — HLS session lifecycle, command construction, seek restarts, segment purge, probe cache, subtitle materialization, session limits
- `adapters/media/ffmpeg_encoder.py` — auto-selection, hardware IDR/keyframe flags, encode arg builders
- `adapters/media/__init__.py`
- `composition/root.py` — `FFmpegTranscoderAdapter` wiring (`max_active_sessions=2`, `segment_seconds=4`, `playback.video_encoder`)
- `settings.json` → `playback.video_encoder`
- `ports/interfaces.py` — `MediaTranscoderPort.ensure_hls_session` contract
- `application/playback/transcode_session.py` — passthrough of `subtitle_track` (cross-layer only)
- Unit tests: `tests/unit/adapters/media/test_ffmpeg_*.py` (29 passed)

**Cross-ref (Unit 1):** Finding #16 — `_ActiveTranscode` drops `subtitle_track`; confirmed and expanded below (#2, #3).

**Out of scope:** HTTP routes, Next.js player, `PlaybackService` speculative-seek logic (Unit 1), production fixes.

**Method:** Static code review + unit test run (`pytest tests/unit/adapters/media -v --no-cov`, 29 passed). Code-review-graph MCP unavailable.

---

## Composition & settings wiring

| Parameter | `composition/root.py` | `FFmpegTranscoderAdapter` default | `settings.json` |
|-----------|----------------------|-----------------------------------|-----------------|
| `max_active_sessions` | `2` (literal) | `2` | *(not configurable)* |
| `segment_seconds` | `4` (local `_SEGMENT_SECONDS`, not imported from contract) | `4` | *(not configurable)* |
| `video_encoder` | `playback_cfg.get("video_encoder", "auto")` | `"auto"` | `"auto"` |
| `ffmpeg_bin` / `ffprobe_bin` | defaults | `"ffmpeg"` / `"ffprobe"` | *(not configurable)* |
| `startup_timeout_seconds` | default `15` | `15` | *(not configurable)* |

Encoder choice is resolved **once** in `FFmpegTranscoderAdapter.__init__` via `resolve_video_encoder()`; changing `settings.json` requires process restart (documented in AGENTS.md).

---

## Findings

### 1. `subtitle_track` accepted but never applied to ffmpeg command

- **Severity:** high
- **Title:** Subtitle burn-in parameter is a no-op in `_build_command`
- **Evidence:** `adapters/media/ffmpeg_transcoder.py:502-604` — `subtitle_track` parameter unused; no `-vf subtitles=`, `-filter_complex`, or subtitle map. Unit test explicitly asserts no `-vf`: `tests/unit/adapters/media/test_ffmpeg_transcoder.py:69-71`
- **Repro:** Call `ensure_hls_session(..., subtitle_track=1)`; inspect `_ffmpeg.log` spawn line or `_build_command` output — identical to `subtitle_track=None`.
- **Expected vs actual:** Port and `TranscodeSession.start` pass `subtitle_track` through the stack; callers may assume selected subtitles are burned into HLS video. Actual: only sidecar WebVTT/ASS extraction via `materialize_subtitle_tracks` (separate from transcode).
- **Suggested fix:** Either implement burn-in (`-vf` / filter_complex with stream index from `subtitle_track`) or remove the parameter from the port and document sidecar-only subtitles.

---

### 2. Active session record discards `subtitle_track` (Unit 1 #16)

- **Severity:** medium
- **Title:** `_ActiveTranscode.subtitle_track` always stored as `None`
- **Evidence:** `adapters/media/ffmpeg_transcoder.py:235-245` — constructor receives `subtitle_track=subtitle_track` but assigns `subtitle_track=None`; log line also logs `subs=None`
- **Repro:** Start session with `subtitle_track=2`; inspect in-memory `_active[session_id].subtitle_track` → `None`.
- **Expected vs actual:** Session metadata should reflect the encode request for reuse/divergence checks. Actual: value is dropped immediately after spawn.
- **Suggested fix:** Store `subtitle_track=subtitle_track` on `_ActiveTranscode` (even if burn-in is unimplemented, needed for future reuse logic).

---

### 3. Session reuse ignores `subtitle_track` and `source_path`

- **Severity:** medium
- **Title:** Early-return reuse path compares only start index, segment length, and audio
- **Evidence:** `adapters/media/ffmpeg_transcoder.py:158-164` — guard checks `start_segment_index`, `segment_seconds`, `audio_track`, process alive; no `subtitle_track` or `source_path`
- **Repro:** With an active encode at segment 0, call `ensure_hls_session` again with same indices but different `subtitle_track` (or hypothetically different `source_path` if session_id were reused). Adapter returns without respawning ffmpeg.
- **Expected vs actual:** Divergent subtitle selection should terminate and respawn (especially once burn-in exists). Actual: silently reuses stale process.
- **Suggested fix:** Add `subtitle_track` (and `source_path`) to reuse guard; treat mismatch like audio-track change (terminate + optional purge).

---

### 4. `effective_subtitle_track` return field is always empty

- **Severity:** low
- **Title:** Misleading artifact metadata suggests burn-in was planned
- **Evidence:** `adapters/media/ffmpeg_transcoder.py:276` — `"effective_subtitle_track": ""` hard-coded in every success return
- **Repro:** Any successful `ensure_hls_session` call; returned dict always has empty string.
- **Expected vs actual:** Field should report the subtitle stream actually muxed/burned, or be omitted.
- **Suggested fix:** Populate from implemented burn-in logic or remove the key.

---

### 5. `h264_mf` lacks forced-IDR / keyframe alignment flags

- **Severity:** medium
- **Title:** Windows Media Foundation encoder may ignore segment cadence on seek restarts
- **Evidence:** `adapters/media/ffmpeg_encoder.py:151-152` — only `-rate_control quality -quality 50`; no `-forced_idr` / `-forced-idr` unlike `h264_nvenc`, `h264_qsv`, `h264_amf` (lines 116-149). Module docstring at `ffmpeg_encoder.py:98-100` states hardware encoders need forced-IDR for `-force_key_frames` to work.
- **Repro:** On Windows with `video_encoder: auto` selecting `h264_mf`, seek restart (`start_segment_index > 0`) and inspect segment boundaries — irregular `#EXTINF` vs actual keyframe spacing possible.
- **Expected vs actual:** All hardware paths should force IDR on segment cadence per design comments in `ffmpeg_transcoder.py:18-21`. Actual: MF path relies on `-force_key_frames` alone, which may be ignored.
- **Suggested fix:** Research MF encoder options (`-forced_idr` if supported) or document MF as unsupported for seek-on-demand and fall back to `libx264`.

---

### 6. LRU eviction by `started_at`, not viewer activity

- **Severity:** medium
- **Title:** Third concurrent transcode kills oldest *started* session, not idle session
- **Evidence:** `adapters/media/ffmpeg_transcoder.py:463-485` — `_evict_oldest_locked` uses `min(..., key=lambda item: item[1].started_at)`; `composition/root.py:80-81` sets `max_active_sessions=2`
- **Repro:** User A starts watching (session 1). User B starts (session 2). User A still playing; User C starts (session 3) → session 1 ffmpeg terminated despite active playback.
- **Expected vs actual:** Capacity policy should prefer evicting idle/expired encodes. Actual: long-running watch can be killed when a newer session starts elsewhere.
- **Suggested fix:** Evict by last heartbeat / `last_seen_at` from application layer, or raise `InfrastructureError` instead of silent kill; expose max sessions in settings.

---

### 7. Evicted sessions are not signaled to `PlaybackService`

- **Severity:** medium
- **Title:** Adapter evicts ffmpeg without application-layer teardown
- **Evidence:** `adapters/media/ffmpeg_transcoder.py:477-484` — `_terminate` + pop victim; no callback. `PlaybackService` discovers dead encode via `is_hls_session_running` on next segment request (`application/playback/service.py:414-424`).
- **Repro:** Evict scenario in #6; user A's player buffers until segment fetch triggers `_restart_at` — visible stall or error depending on race.
- **Expected vs actual:** Eviction should notify or mark session so client gets a structured error. Actual: silent process kill; recovery depends on lazy restart.
- **Suggested fix:** Port callback on eviction, or return error to caller when their session was evicted; document two-session limit in UI.

---

### 8. `max_active_sessions` not configurable via settings

- **Severity:** low
- **Title:** Concurrent transcode cap hardcoded in composition root
- **Evidence:** `composition/root.py:80-81` — literal `max_active_sessions=2`; `settings.json:260-262` only defines `video_encoder`
- **Repro:** N/A — design limitation.
- **Suggested fix:** Add `playback.max_active_sessions` to settings template and wire through `root.py`.

---

### 9. Global `RLock` held for full spawn path including subprocess start

- **Severity:** low
- **Title:** Transcode operations serialized under `_lock`
- **Evidence:** `adapters/media/ffmpeg_transcoder.py:155-255` — lock held from reuse check through `_spawn_ffmpeg` and `_active` registration
- **Repro:** Two sessions starting simultaneously; second blocks until first completes spawn setup.
- **Expected vs actual:** Independent sessions could spawn in parallel with per-session locking. Actual: global serialization may add latency under concurrent play.
- **Suggested fix:** Narrow critical sections; spawn outside lock after slot reservation.

---

### 10. No adapter startup health check when canonical manifest pre-exists

- **Severity:** low
- **Title:** VOD path skips `_wait_for_initial_manifest`
- **Evidence:** `adapters/media/ffmpeg_transcoder.py:257-267` — when `index.m3u8` already exists (normal `PlaybackService` flow), returns immediately without verifying ffmpeg survived startup
- **Repro:** Spawn ffmpeg that dies instantly (bad source); `ensure_hls_session` returns success dict while process already exited (reaped on next lock entry).
- **Expected vs actual:** Adapter should confirm process alive briefly or first segment progress. Actual: relies on `PlaybackService` resume segment wait at create time (`application/playback/service.py:196-207`).
- **Suggested fix:** Optional short poll for process liveness even when manifest pre-written; or document application-layer responsibility.

---

### 11. Failed ffprobe results are not cached (tracks)

- **Severity:** low
- **Title:** Repeated ffprobe on every episode listing when probe fails
- **Evidence:** `adapters/media/ffmpeg_transcoder.py:309-318` — cache only on success; `tests/unit/adapters/media/test_ffmpeg_transcoder.py:354-368` documents double-invocation on failure
- **Repro:** Point `probe_media_tracks` at unreadable path; call twice → two ffprobe subprocesses (15s timeout each).
- **Expected vs actual:** Negative cache with short TTL would reduce load on library scans. Actual: hammering on persistent failures.
- **Suggested fix:** Cache empty result with signature + short TTL, or distinguish "file missing" vs "probe error".

---

### 12. `materialize_subtitle_tracks` swallows errors silently

- **Severity:** medium
- **Title:** Per-track extract failures invisible (stderr discarded)
- **Evidence:** `adapters/media/ffmpeg_transcoder.py:674-683` — `stdout=DEVNULL, stderr=DEVNULL`; bare `except Exception: continue`
- **Repro:** Episode with PGS (`hdmv_pgs_subtitle`) or other non-text subs; materialize returns partial/empty list with no log.
- **Expected vs actual:** Failures should log at warning with track id/codec. Actual: silent skip — UI shows fewer subtitles with no diagnostic.
- **Suggested fix:** Log failures; optionally surface codec in returned metadata with `available: false`.

---

### 13. Subtitle materialization runs O(tracks) full-file ffmpeg reads

- **Severity:** low
- **Title:** Each subtitle track spawns independent demux+convert
- **Evidence:** `adapters/media/ffmpeg_transcoder.py:651-723` — loop with separate `-i source_path` per track (plus optional ASS copy pass)
- **Repro:** MKV with 8 subtitle tracks → up to 16 ffmpeg invocations on session create.
- **Expected vs actual:** Acceptable for small track counts; large files may add multi-second startup. Actual: no batching or parallel limit.
- **Suggested fix:** Document performance characteristic; consider single-pass multi-map extract for text codecs.

---

### 14. Input seek (`-ss` before `-i`) trades accuracy for speed

- **Severity:** low
- **Title:** Seek restarts use fast input seek, not output seek
- **Evidence:** `adapters/media/ffmpeg_transcoder.py:545-547` — `-ss` before `-i`; tests lock this in (`test_ffmpeg_transcoder.py:32-41`, `90-97`)
- **Repro:** Seek restart to non-keyframe boundary; first segment may start slightly before/after requested timeline vs frame-accurate output seek.
- **Expected vs actual:** Documented tradeoff for ~2s segment availability. Acceptable for HLS but may cause brief A/V or subtitle sync drift at seek point.
- **Suggested fix:** Optional output-seek mode for resume-critical paths; or document as intentional.

---

### 15. Backward seek segment purge path lacks regression test

- **Severity:** info
- **Title:** `_purge_ts_segments` on backward restart untested in unit suite
- **Evidence:** Purge triggered at `ffmpeg_transcoder.py:186-202` when `start_index < existing.start_segment_index`; forward non-purge covered by `test_forward_restart_does_not_purge_segments`; no `test_backward_restart_purges_segments`
- **Repro:** N/A — coverage gap.
- **Suggested fix:** Add unit test asserting `_purge_ts_segments` called when restarting from lower segment index (resume prefetch → segment 0 scenario per comments at lines 177-183).

---

### 16. Encoder detection failure assumes `libx264` available

- **Severity:** low
- **Title:** `list_h264_encoders` returns `{libx264}` on any subprocess error
- **Evidence:** `adapters/media/ffmpeg_encoder.py:47-48` — bare `except Exception: return {SOFTWARE_ENCODER}`
- **Repro:** `ffmpeg` missing from PATH; auto mode selects `libx264` then spawn fails at runtime with opaque error.
- **Expected vs actual:** Fail fast at adapter init with clear `InfrastructureError`. Actual: deferred failure on first transcode.
- **Suggested fix:** Validate ffmpeg/ffprobe executables at init; surface resolution errors in telemetry.

---

### 17. `settings.json` playback section minimal vs AGENTS.md

- **Severity:** info
- **Title:** Template documents encoder only; other transcoder knobs undocumented in settings
- **Evidence:** `settings.json:260-262` vs AGENTS.md playback table (encoder values documented; max sessions / segment seconds not in settings)
- **Repro:** N/A
- **Suggested fix:** Align settings template and AGENTS.md with configurable knobs if added (#8).

---

### 18. Positive design notes (non-findings)

Seek-restart engineering is generally sound and well-tested:

- `-output_ts_offset` + no `-avoid_negative_ts make_zero` on seek path (`ffmpeg_transcoder.py:545-551`, tests `test_seek_without_subtitles_uses_input_seek_and_output_ts_offset`)
- Zero-based `-force_key_frames expr:gte(t,n_forced*N)` after input seek (`ffmpeg_transcoder.py:552`, test `test_seek_keyframe_expression_is_zero_based`)
- Forward restart preserves anchor segments; backward/audio change purges stale TS (`test_forward_restart_does_not_purge_segments`)
- Probe cache keyed by `(mtime_ns, size)` with isolated copies (`test_probe_media_*`)
- NVENC/QSV/AMF forced-IDR paths covered in unit tests

---

## Cross-layer notes (for other units)

| Topic | Layer | Note |
|-------|-------|------|
| Subtitle sidecars vs burn-in | Unit 4/5 (frontend) | Player uses WebVTT/ASS sidecars; `subtitle_track` on session may not match user expectation if burn-in was intended |
| Eviction UX | Unit 3 (HTTP) / Unit 5 (UI) | Two-session cap invisible to clients until stall |
| Segment wait on create | Unit 1 | `PlaybackService` waits for resume segment; compensates for #10 |

---

## Summary counts

| Severity | Count |
|----------|-------|
| critical | 0 |
| high | 1 |
| medium | 6 |
| low | 7 |
| info | 2 |

**Total:** 16 findings (+ positive design section)

---

## Verification

```text
pytest tests/unit/adapters/media -v --no-cov → 29 passed in ~5s
```
