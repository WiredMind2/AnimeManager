# Unit 2 — Backend resume/scrub + SegmentResolver extract

**GOAL ref**: GOAL §frozen
**Hub**: same
**Branch**: `big/media-player-fix`
**Ownership**: `application/playback/service.py`, `application/playback/segment_resolver.py`, related tests
**Criteria** (subset):
- [x] Fix U1-1: speculative gate uses current playhead, not frozen create-time seconds
- [x] Pure extract of segment ensure / speculative / restart lock
- [x] Tests in `tests/unit/playback/` + `tests/unit/components/test_media_streaming_service.py`
**Open / blurry**: (none)
**Last commit**: `655c79d` fix(big): extract SegmentResolver and fix resume scrub
**Agent ids**: worker phase-1
**Iterations**: 1 / 5
