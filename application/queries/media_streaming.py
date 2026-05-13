"""Query objects for media streaming workflows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ListEpisodeFilesQuery:
    anime_id: int


@dataclass(slots=True)
class GetPlaybackSessionQuery:
    session_id: str
    token: str
    segment_name: str | None = None


__all__ = ["ListEpisodeFilesQuery", "GetPlaybackSessionQuery"]
