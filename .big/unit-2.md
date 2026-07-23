# Unit 2 — Backend resume/scrub + SegmentResolver extract

**GOAL ref**: GOAL §frozen
**Hub**: same
**Branch**: `big/media-player-fix`
**Ownership**: `application/playback/service.py`, new `application/playback/segment_resolver.py`, related tests
**Criteria** (subset):
- [ ] Fix U1-1: speculative gate uses current playhead, not frozen create-time seconds
- [ ] Pure extract of segment ensure / speculative / restart lock
- [ ] Tests in `tests/unit/playback/` + `tests/unit/components/test_media_streaming_service.py`
**Open / blurry**: (none)
**Last commit**: none
**Agent ids**: worker phase-1
**Iterations**: 0 / 5
