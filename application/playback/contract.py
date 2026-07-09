"""Shared playback constants — single source of truth for server and tests."""

from __future__ import annotations

SEGMENT_SECONDS = 4
PREFETCH_MARGIN = 2
MIN_RESUME_SECONDS = 10.0
# Restart from the beginning when the saved position is within this many
# seconds of the end. The on-demand HLS manifest is EVENT-typed (live) until
# transcoding completes, and Shaka's live-edge seek parked the playhead
# ~bufferingGoal (12s) before the end on fresh starts; that bogus position
# then got persisted as resume progress. Treating near-end positions as
# "finished" unsticks those episodes and matches normal video-app semantics.
NEAR_END_RESTART_SECONDS = 15.0

SESSION_TTL_SECONDS = 900
SESSION_CREATE_WAIT_SECONDS = 25.0
RESUME_SEGMENT_WAIT_SECONDS = 180.0
SEGMENT_WAIT_SECONDS = 20.0
FORWARD_WAIT_SECONDS = 2.5

RESERVED_INTERNAL_NAMES = frozenset({"_ffmpeg.m3u8"})

__all__ = [
    "SEGMENT_SECONDS",
    "PREFETCH_MARGIN",
    "MIN_RESUME_SECONDS",
    "NEAR_END_RESTART_SECONDS",
    "SESSION_TTL_SECONDS",
    "SESSION_CREATE_WAIT_SECONDS",
    "RESUME_SEGMENT_WAIT_SECONDS",
    "SEGMENT_WAIT_SECONDS",
    "FORWARD_WAIT_SECONDS",
    "RESERVED_INTERNAL_NAMES",
]
