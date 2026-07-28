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

# Incomplete EVENT manifests only advertise this many segments past the
# encode/playhead head. Stops Shaka from probing the fictional live edge
# of a fully-listed-but-unencoded playlist (which yanked ffmpeg mid-resume).
EVENT_MANIFEST_LOOKAHEAD = 15

# Refuse seek-on-demand ffmpeg restarts more than this many segments ahead of
# the session playhead while the playhead encode is still healthy (~6 min).
# Blocks half-file live-edge probes (e.g. segment 177/193) while still
# allowing normal scrub-ahead (e.g. segment 50 from a fresh start).
MAX_FORWARD_JUMP_SEGMENTS = 90

SESSION_TTL_SECONDS = 900
# HMAC playback tokens must outlive a single browser tab's idle gaps but
# still track session cleanup. ``PlaybackService`` uses
# ``max(session.ttl_seconds, TOKEN_MIN_TTL_SECONDS)`` when minting tokens
# while ``session.expires_at`` uses the per-session TTL only (heartbeat
# extends by ``session.ttl_seconds``).
TOKEN_MIN_TTL_SECONDS = 12 * 3600
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
    "EVENT_MANIFEST_LOOKAHEAD",
    "MAX_FORWARD_JUMP_SEGMENTS",
    "SESSION_TTL_SECONDS",
    "TOKEN_MIN_TTL_SECONDS",
    "SESSION_CREATE_WAIT_SECONDS",
    "RESUME_SEGMENT_WAIT_SECONDS",
    "SEGMENT_WAIT_SECONDS",
    "FORWARD_WAIT_SECONDS",
    "RESERVED_INTERNAL_NAMES",
]
