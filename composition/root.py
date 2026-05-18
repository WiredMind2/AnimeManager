"""Canonical composition root.

This module is the single dependency-wiring point for the embedded
runtime. It is the source of truth for
:func:`build_embedded_facade`.

Layering: ``composition`` may import from ``adapters``, ``application``,
``ports``, ``shared`` and ``domain``. It must **not** be imported by
``domain``, ``application`` or ``ports`` -- the dependency edge goes
in one direction only.
"""

from __future__ import annotations

from adapters.legacy.runtime import (
    LegacyAnimeRepositoryAdapter,
    LegacyDownloadAdapter,
    LegacyMediaLibraryAdapter,
    LegacyMetadataProviderAdapter,
    LegacyRuntime,
    LegacyUserActionsAdapter,
)
from adapters.media import FFmpegTranscoderAdapter
from application.services.anime_service import AnimeApplicationService
from application.services.media_streaming_service import MediaStreamingService
from application.services.startup_jobs import StartupJobsService
from composition.facade import EmbeddedClientFacade


def build_embedded_facade() -> EmbeddedClientFacade:
    """Create the complete embedded backend graph."""
    runtime = LegacyRuntime()
    repository = LegacyAnimeRepositoryAdapter(runtime)
    metadata = LegacyMetadataProviderAdapter(runtime, repository)
    download = LegacyDownloadAdapter(runtime, repository=repository)
    user_actions = LegacyUserActionsAdapter(runtime)
    media_library = LegacyMediaLibraryAdapter(runtime, download_port=download)
    # Both layers must agree on the segment cadence — the service
    # pre-writes a VOD playlist that assumes every segment is exactly
    # this many seconds long, and the adapter sets the matching
    # ``-hls_time`` and force-keyframe interval so the .ts files line
    # up with the playlist's EXTINF entries.
    _SEGMENT_SECONDS = 4
    media_transcoder = FFmpegTranscoderAdapter(
        video_codec="h264_nvenc",
        require_hardware_acceleration=True,
        # Keep NVENC encode required, but do not force CUDA decode:
        # some source codecs/profiles fail early with mandatory HW decode
        # and no segments are emitted, which surfaces as Shaka 1003.
        use_cuda_hwaccel=False,
        max_active_sessions=2,
        segment_seconds=_SEGMENT_SECONDS,
    )
    media_streaming = MediaStreamingService(
        media_library=media_library,
        transcoder=media_transcoder,
        segment_seconds=_SEGMENT_SECONDS,
    )

    service = AnimeApplicationService(
        anime_repository=repository,
        metadata_provider=metadata,
        download_port=download,
        user_actions_port=user_actions,
        media_streaming_service=media_streaming,
    )

    # Startup jobs reuse the already-wired API coordinator / database
    # manager from the legacy adapters so we don't end up with two
    # parallel ingestion pipelines fighting for the executor.
    startup_jobs = StartupJobsService(
        api_coordinator=metadata._api_coordinator,
        database_manager=repository._db_manager,
        runtime=runtime,
    )

    return EmbeddedClientFacade(service, startup_jobs=startup_jobs)


__all__ = ["build_embedded_facade"]
