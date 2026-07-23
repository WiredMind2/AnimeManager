"""On-demand HLS playback package."""

from application.playback.contract import SEGMENT_SECONDS

__all__ = ["PlaybackService", "MediaStreamingService", "SEGMENT_SECONDS"]


def __getattr__(name: str):
    if name in ("PlaybackService", "MediaStreamingService"):
        from application.playback.service import MediaStreamingService, PlaybackService

        if name == "PlaybackService":
            return PlaybackService
        return MediaStreamingService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
