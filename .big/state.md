# /big state — media player fix + simplify

**GOAL**: Fix audit highs/functional mediums and simplify playback stack (extract modules, dedupe constants, gate session lifecycle) while keeping seek-on-demand HLS, sidecar subtitles, audio track select, resume, max 2 sessions, hardware encoder auto.

**Mode**: parallel (shard wave after serial hub units)
**Hub worktree**: `C:\Users\willi\Documents\Python\AnimeManager\.worktrees\media-player-fix`
**Hub branch**: `big/media-player-fix`
**Base branch**: `big/media-player-audit` @ 6697fbd
**Max parallel**: 3
**Iterations**: 1 / 15

## Acceptance criteria (from plan)

- [ ] All 10 high findings addressed (code or intentional wontfix with rationale in findings index)
- [ ] Functional mediums listed in audit Phase 1–5 fixed or deferred with note
- [x] `SEGMENT_SECONDS` / session TTL imported from contract in Python wiring
- [x] `PlaybackService` segment logic extracted; scrub-after-resume works with tests
- [ ] Next.js: no heartbeat on failed load; stop on unmount; recovery covers segment/scrub paths *(U5 shard)*
- [ ] Proxy forwards client IP; LAN gate meaningful in web mode *(U4 shard)*
- [ ] Status change preserves position; legacy progress/resume corrected *(U6 shard)*
- [x] Docs match HLS architecture *(U7 shard @ 7235ae1)*
- [x] Features preserved: seek-on-demand HLS, sidecar subs, audio track select, resume, max 2 sessions, hardware encoder auto

## Work units

| # | Title | Mode | Branch | Worktree | Status |
|---|-------|------|--------|----------|--------|
| 1 | Constants + contracts | serial | big/media-player-fix | hub | pass |
| 2 | SegmentResolver + scrub fix | serial | big/media-player-fix | hub | pass |
| 3 | FFmpeg sidecar honesty + session policy | serial | big/media-player-fix | hub | pass |
| 4 | HTTP/proxy ACL | parallel shard | big/media-player-fix--u4 | `C:\Users\willi\Documents\Python\AnimeManager\.worktrees\media-player-fix--u4` | running |
| 5 | Next.js load/recovery | parallel shard | big/media-player-fix--u5 | `C:\Users\willi\Documents\Python\AnimeManager\.worktrees\media-player-fix--u5` | running |
| 6 | Progress / legacy HTMX | parallel shard | big/media-player-fix--u6 | `C:\Users\willi\Documents\Python\AnimeManager\.worktrees\media-player-fix--u6` | pass (75d23f4) |
| 7 | Docs | parallel shard | big/media-player-fix--u7 | `C:\Users\willi\Documents\Python\AnimeManager\.worktrees\media-player-fix--u7` | pass (7235ae1) |
| 8 | Hub integration | serial | big/media-player-fix | hub | pending |

## Open items

- Shard wave u4-u6 still in progress; u7 pass @ shard 7235ae1 (not merged)
- Token still outlives session record by design (TOKEN_MIN_TTL floor); session cleanup remains primary gate
- Segment token optional on segment URLs deferred to U4

## Cheat log

- (none)
