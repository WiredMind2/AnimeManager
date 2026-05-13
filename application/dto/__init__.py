"""Application DTOs namespace.

Re-exports the canonical DTOs from :mod:`domain.dto`. (DTOs live in
the domain layer because they describe the request/response shapes
exchanged with clients; the application layer constructs them.)
"""

from __future__ import annotations

from domain.dto import (
    AnimeListRequest,
    AnimeListResponse,
    DownloadRequest,
    SearchRequest,
)
from application.dto.media_streaming import EpisodeFileDTO, PlaybackSessionDTO

__all__ = [
    "AnimeListRequest",
    "AnimeListResponse",
    "DownloadRequest",
    "SearchRequest",
    "EpisodeFileDTO",
    "PlaybackSessionDTO",
]
