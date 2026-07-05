"""Application services namespace (canonical home)."""

from application.services.anime_service import AnimeApplicationService
from application.playback import PlaybackService as MediaStreamingService

__all__ = ["AnimeApplicationService", "MediaStreamingService"]
