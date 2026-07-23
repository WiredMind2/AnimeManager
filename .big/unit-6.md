# Unit 6 — Progress / legacy HTMX (shard)

**GOAL ref**: GOAL §frozen
**Hub**: `C:\Users\willi\Documents\Python\AnimeManager\.worktrees\media-player-fix`
**Worktree**: `C:\Users\willi\Documents\Python\AnimeManager\.worktrees\media-player-fix--u6`
**Branch**: `big/media-player-fix--u6`
**Mode**: parallel shard
**Ownership**: EpisodePlayerTable.tsx, user_actions_repository.py, clients/http/static/js/app.js, progress.ts
**Status**: done
**Last commit**: (see git log) fix(big): preserve position on status and fix legacy resume
**Iterations**: 1 / 5
**Agent ids**: worker-u6

## Completed

- **U5-9**: `set_episode_progress` skips `position_seconds` on UPDATE when omitted; status-only POSTs preserve stored position.
- **U5-4**: Legacy `app.js` uses `payload.playback_start_seconds` for Shaka `load()`; removed ignored `start_time` form field and dead client resume merge.
- **U5-5**: Legacy progress/localStorage uses inline `toAbsoluteSourceSeconds` with `hls_anchor_segment` / `segment_seconds` from session payload.
- **Cleanup**: Removed unused `episodeResumeMap` prop from `WatchView` / watch page.

## Open / blurry

- (none)
