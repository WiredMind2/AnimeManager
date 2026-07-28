"""Command objects for media streaming workflows."""

from __future__ import annotations

from dataclasses import dataclass

from application.playback.contract import SESSION_TTL_SECONDS


@dataclass(slots=True)
class CreatePlaybackSessionCommand:
    anime_id: int
    file_id: str
    client_host: str = ""
    ttl_seconds: int = SESSION_TTL_SECONDS
    audio_track: int | None = None
    subtitle_track: int | None = None
    # Optional client hint: "I'm about to play from this offset, so
    # start the encoder there." Used to avoid a wasted seek-on-demand
    # round trip when the user has a saved resume position.
    start_time_seconds: float | None = None


@dataclass(slots=True)
class HeartbeatPlaybackSessionCommand:
    session_id: str
    # Optional client playhead hint (absolute source seconds).
    position_seconds: float | None = None


@dataclass(slots=True)
class StopPlaybackSessionCommand:
    session_id: str


__all__ = [
    "CreatePlaybackSessionCommand",
    "HeartbeatPlaybackSessionCommand",
    "StopPlaybackSessionCommand",
]
