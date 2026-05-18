"""DTOs for web media streaming sessions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class EpisodeFileDTO:
    file_id: str
    title: str
    path: str
    size_bytes: int | None = None
    season: int | None = None
    episode: int | None = None
    audio_tracks: list[dict[str, object]] = field(default_factory=list)
    subtitle_tracks: list[dict[str, object]] = field(default_factory=list)
    watch_status: str = "UNSEEN"
    position_seconds: float | None = None
    duration_seconds: float | None = None


@dataclass(slots=True)
class PlaybackSessionDTO:
    session_id: str
    anime_id: int
    file_id: str
    file_title: str
    manifest_path: str
    output_dir: str
    token: str
    expires_at: float
    created_at: float
    last_seen_at: float
    playlist_url: str | None = None
    audio_track: int | None = None
    subtitle_track: int | None = None
    subtitle_tracks: list[dict[str, object]] = field(default_factory=list)
    # Source-side bookkeeping needed for seek-on-demand transcoding.
    # ``source_path`` lets the service relaunch ffmpeg without going
    # back to the media library; ``duration_seconds`` /
    # ``segment_seconds`` / ``total_segments`` describe the canonical
    # VOD playlist served to the client (zero/None values mean the
    # source did not advertise a duration and the session falls back
    # to live-style behaviour).
    source_path: str = ""
    duration_seconds: float = 0.0
    segment_seconds: int = 0
    total_segments: int = 0
    extra: dict[str, str] = field(default_factory=dict)


__all__ = ["EpisodeFileDTO", "PlaybackSessionDTO"]
