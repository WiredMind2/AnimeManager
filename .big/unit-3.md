# Unit 3 — FFmpeg adapter: sidecar honesty + session policy

**GOAL ref**: GOAL §frozen
**Hub**: same
**Branch**: `big/media-player-fix`
**Ownership**: `adapters/media/ffmpeg_transcoder.py`, `adapters/media/ffmpeg_encoder.py`, ports/DTO/`web.py` response fields as needed
**Criteria** (subset):
- [x] Remove/clarify dead burn-in param; keep `materialize_subtitle_tracks`
- [x] Surface PGS/image-sub failures; forced-IDR for `h264_mf`; eviction notify + prefer idle
**Open / blurry**: (none)
**Last commit**: `f0da5b3` fix(big): ffmpeg sidecar honesty and session policy
**Agent ids**: worker phase-1
**Iterations**: 1 / 5
