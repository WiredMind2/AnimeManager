# /big state - media player fix + simplify

**GOAL**: Fix audit highs/functional mediums and simplify playback stack (extract modules, dedupe constants, gate session lifecycle) while keeping seek-on-demand HLS, sidecar subtitles, audio track select, resume, max 2 sessions, hardware encoder auto.

**Mode**: parallel (shard wave after serial hub units)
**Hub worktree**: `C:\Users\willi\Documents\Python\AnimeManager\.worktrees\media-player-fix`
**Hub branch**: `big/media-player-fix`
**Base branch**: `big/media-player-audit` @ 6697fbd
**Max parallel**: 3
**Iterations**: hub-final PASS
**Criteria checked**: 9 / 9
**Hub tip after merge**: 403e06d

## Acceptance criteria (from plan)

- [x] All 10 high findings addressed (code or intentional wontfix with rationale in findings index)
- [x] Functional mediums listed in audit Phase 1-5 fixed or deferred with note (see findings index)
- [x] `SEGMENT_SECONDS` / session TTL imported from contract in Python wiring
- [x] `PlaybackService` segment logic extracted; scrub-after-resume works with tests
- [x] Next.js: no heartbeat on failed load; stop on unmount; recovery covers segment/scrub paths *(merged @ 0408cde)*
- [x] Proxy forwards client IP; LAN gate meaningful in web mode *(merged @ 27a54a3)*
- [x] Status change preserves position; legacy progress/resume corrected *(merged @ ac8562f)*
- [x] Docs match HLS architecture *(merged @ be95683)*
- [x] Features preserved: seek-on-demand HLS, sidecar subs, audio track select, resume, max 2 sessions, hardware encoder auto

## Work units

| # | Title | Mode | Branch | Worktree | Status |
|---|-------|------|--------|----------|--------|
| 1 | Constants + contracts | serial | big/media-player-fix | hub | pass |
| 2 | SegmentResolver + scrub fix | serial | big/media-player-fix | hub | pass |
| 3 | FFmpeg sidecar honesty + session policy | serial | big/media-player-fix | hub | pass |
| 4 | HTTP/proxy ACL | parallel shard | big/media-player-fix--u4 | shard | pass merged @ 27a54a3 |
| 5 | Next.js load/recovery | parallel shard | big/media-player-fix--u5 | shard | pass merged @ 0408cde |
| 6 | Progress / legacy HTMX | parallel shard | big/media-player-fix--u6 | shard | pass merged @ ac8562f |
| 7 | Docs | parallel shard | big/media-player-fix--u7 | shard | pass merged @ be95683 |
| 8 | Hub integration | serial | big/media-player-fix | hub | pass (pytest 95+7; vitest skipped no node_modules) |

## Deferred (not blockers)

- Token still outlives session record by design (`TOKEN_MIN_TTL` floor vs session TTL); session cleanup remains primary gate
- Segment HMAC / token optional on segment URLs (U1-2/U3-2) — deferred; documented in findings index

## Cheat log

- (none)