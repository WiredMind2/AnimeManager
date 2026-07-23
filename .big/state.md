# /big state — media player fix + simplify

**GOAL**: Fix audit highs/functional mediums and simplify playback stack (extract modules, dedupe constants, gate session lifecycle) while keeping seek-on-demand HLS, sidecar subtitles, audio track select, resume, max 2 sessions, hardware encoder auto.

**Mode**: parallel (shard wave after serial hub units)
**Hub worktree**: `C:\Users\willi\Documents\Python\AnimeManager\.worktrees\media-player-fix`
**Hub branch**: `big/media-player-fix`
**Base branch**: `big/media-player-audit` @ 6697fbd
**Max parallel**: 3
**Iterations**: 0 / 15

## Acceptance criteria (from plan)

- [ ] All 10 high findings addressed (code or intentional wontfix with rationale in findings index)
- [ ] Functional mediums listed in audit Phase 1–5 fixed or deferred with note
- [ ] `SEGMENT_SECONDS` / session TTL imported from contract in Python wiring
- [ ] `PlaybackService` segment logic extracted; scrub-after-resume works with tests
- [ ] Next.js: no heartbeat on failed load; stop on unmount; recovery covers segment/scrub paths *(U5 shard)*
- [ ] Proxy forwards client IP; LAN gate meaningful in web mode *(U4 shard)*
- [ ] Status change preserves position; legacy progress/resume corrected *(U6 shard)*
- [ ] Docs match HLS architecture *(U7 shard)*
- [ ] Features preserved: seek-on-demand HLS, sidecar subs, audio track select, resume, max 2 sessions, hardware encoder auto

## Work units

| # | Title | Mode | Branch | Worktree | Status |
|---|-------|------|--------|----------|--------|
| 1 | Constants + contracts | serial | big/media-player-fix | hub | in_progress |
| 2 | SegmentResolver + scrub fix | serial | big/media-player-fix | hub | pending |
| 3 | FFmpeg sidecar honesty + session policy | serial | big/media-player-fix | hub | pending |
| 4 | HTTP/proxy ACL | parallel shard | big/media-player-fix--u4 | shard | pending |
| 5 | Next.js load/recovery | parallel shard | big/media-player-fix--u5 | shard | pending |
| 6 | Progress / legacy HTMX | parallel shard | big/media-player-fix--u6 | shard | pending |
| 7 | Docs | parallel shard | big/media-player-fix--u7 | shard | pending |
| 8 | Hub integration | serial | big/media-player-fix | hub | pending |

## Open items

- Subtitles: sidecar-only; no ffmpeg burn-in (plan default)
- Frozen playhead scrub: fix with live playhead tracking (U2)
- Shard worktrees not created in Phase 1

## Cheat log

- (none)
