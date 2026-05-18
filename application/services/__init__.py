"""Application services namespace (canonical home)."""

from __future__ import annotations

__all__ = ["AnimeApplicationService", "MediaStreamingService"]


def __getattr__(name: str):
    if name == "AnimeApplicationService":
        from application.services.anime_service import AnimeApplicationService

        return AnimeApplicationService
    if name == "MediaStreamingService":
        from application.services.media_streaming_service import MediaStreamingService

        return MediaStreamingService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
