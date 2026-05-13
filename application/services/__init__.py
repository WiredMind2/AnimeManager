"""Application services namespace (canonical home)."""

from application.services.anime_service import AnimeApplicationService
from application.services.media_streaming_service import MediaStreamingService

__all__ = ["AnimeApplicationService", "MediaStreamingService"]
