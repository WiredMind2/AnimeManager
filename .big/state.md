# /big state

**GOAL**: Full audit of media player features — find all bugs and issues
**Mode**: serial
**Hub worktree**: C:\Users\willi\Documents\Python\AnimeManager\.worktrees\media-player-audit
**Hub branch**: ig/media-player-audit
**Worker model**: composer-2.5-fast
**Max parallel**: 4
**Iterations**: 0 / 15
**Criteria checked**: 0 / 7

## Acceptance criteria
- [ ] Each unit produces .big/findings/unit-N-*.md with severity, title, evidence paths, repro (when applicable), expected vs actual, optional suggested fix (not implemented)
- [ ] Master index .big/findings/README.md lists all findings sorted by severity with cross-links
- [ ] Unit 1 covers playback contract constants and wiring vs composition/HTTP
- [ ] Unit 2 documents encoder selection + ffmpeg restart/purge behavior with evidence
- [ ] Unit 3 documents route table, auth matrix, proxy timeout alignment
- [ ] Unit 4 documents Shaka load FSM, session-guard, stale-session recovery
- [ ] Unit 5 traces resume/progress end-to-end and flags localStorage/server divergence; Unit 6 coverage matrix + legacy spot-check + doc drift

## Work units
| # | Title | Mode | Branch | Worktree | Ownership | Status |
|---|-------|------|--------|----------|-----------|--------|
| 1 | Backend playback core | serial | big/media-player-audit | hub | .big/findings/unit-1-backend-playback.md, read pplication/playback/** | pass |
| 2 | FFmpeg transcoder & encoder | serial | big/media-player-audit | hub | .big/findings/unit-2-ffmpeg-adapter.md, read dapters/media/** | pass |
| 3 | HTTP/SDK/proxy & access control | serial | big/media-player-audit | hub | .big/findings/unit-3-http-sdk-proxy.md, read clients/http/web.py, clients/sdk.py, proxy | pass |
| 4 | Next.js Shaka player lifecycle | serial | big/media-player-audit | hub | .big/findings/unit-4-nextjs-player.md, read 
ext-web/lib/playback/**, 
ext-web/components/player/** | pending |
| 5 | Subtitles, resume & progress | serial | big/media-player-audit | hub | .big/findings/unit-5-subtitles-resume-progress.md | pending |
| 6 | Tests, legacy spot-check, docs | serial | big/media-player-audit | hub | .big/findings/unit-6-tests-legacy-docs.md, .big/findings/README.md | pending |

## Open items
- unit-3 findings omit next-web/proxy.ts partial XFF forward — optional unit-6 note
- Legacy HTMX: spot-check divergences only (manager) — unit 6
- Integration fixture path may be missing — skip integration if absent; note in unit 6 (user/config)
- Subtitle burn-in vs sidecar intent — unit 5 worker
- player_allow_public production intent — document as config-dependent finding (user/config)
- Frozen playhead scrub limit: may be intentional Shaka anti-probe tradeoff — prioritize at fix time (manager/user)

## Cheat log
- (none)
