# Unit 4 — HTTP/proxy ACL (shard)

**GOAL ref**: GOAL §frozen
**Hub**: `C:\Users\willi\Documents\Python\AnimeManager\.worktrees\media-player-fix`
**Worktree**: `C:\Users\willi\Documents\Python\AnimeManager\.worktrees\media-player-fix--u4`
**Branch**: `big/media-player-fix--u4`
**Mode**: parallel shard
**Ownership**: next-web/app/backend/[...path]/route.ts, next-web/proxy.ts, clients/http/web.py _client_host / allowlist
**Status**: merged (7079d02)
**Last commit**: 7079d02 fix(big): forward client IP and tighten playback ACL
**Iterations**: 1 / 5
**Agent ids**: worker-u4

## Open / blurry

- `proxy.ts` middleware helper is improved but still unwired (no `middleware.ts`); route handler is the active injection point.
- `test_watch_page_renders_player_view` fails with pre-existing Jinja `TemplateResponse` cache error (unrelated to ACL edits).
