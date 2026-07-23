# Unit 1 — Constants + contracts

**GOAL ref**: GOAL §frozen (media player fix plan)
**Hub**: `C:\Users\willi\Documents\Python\AnimeManager\.worktrees\media-player-fix`
**Branch**: `big/media-player-fix`
**Ownership**: `application/playback/contract.py`, `composition/root.py`, `clients/http/web.py` TTL aliases, facade/commands/`anime_service` defaults
**Criteria** (subset):
- [x] Import `SEGMENT_SECONDS` / `SESSION_TTL_SECONDS` everywhere; add `TOKEN_MIN_TTL_SECONDS`
- [x] Align heartbeat to session TTL; document token floor vs session expiry
**Open / blurry**: (none)
**Last commit**: `9a80835` fix(big): unify playback contract constants and TTL
**Agent ids**: worker phase-1
**Iterations**: 1 / 5
