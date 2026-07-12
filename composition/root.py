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

from adapters.file.local_media_library import LocalMediaLibraryAdapter
from adapters.media import FFmpegTranscoderAdapter
from adapters.metadata.anime_hydration_adapter import AnimeHydrationAdapter
from adapters.metadata.api_coordinator_adapter import ApiCoordinatorAdapter
from adapters.persistence.anime_repository import AnimeRepositoryAdapter
from adapters.persistence.user_actions_repository import UserActionsRepository
from adapters.torrent.download_adapter import DownloadAdapter
from application.playback import PlaybackService
from application.services.anime_hydration import AnimeHydrationService
from application.services.anime_service import AnimeApplicationService
from application.services.anime_write_service import AnimeWriteService
from application.services.startup_jobs import StartupJobsService
from composition.bootstrap import bootstrap_embedded_deps
from composition.facade import EmbeddedClientFacade


def build_embedded_facade() -> EmbeddedClientFacade:
    """Create the complete embedded backend graph."""
    deps = bootstrap_embedded_deps()

    repository = AnimeRepositoryAdapter(deps.db_manager, deps.config, api=deps.api)
    user_actions = UserActionsRepository(deps.database)
    media_library = LocalMediaLibraryAdapter(
        scanner=deps.scanner,
        file_manager=deps.file_manager,
        db_manager=deps.db_manager,
    )
    download = DownloadAdapter(
        torrent_manager=deps.torrent_manager,
        file_manager=deps.file_manager,
        db_manager=deps.db_manager,
        scanner=deps.scanner,
        user_actions=user_actions,
        repository=repository,
    )
    media_library.set_on_torrents_deleted(download.remove_torrents_from_client)
    anime_write = AnimeWriteService(
        db_manager=deps.db_manager,
        log_fn=lambda msg: deps.logger.log("ANIME_WRITE", msg),
    )
    metadata = ApiCoordinatorAdapter(
        deps.api,
        deps.db_manager,
        write_service=anime_write,
    )
    if hasattr(deps.api, "set_write_service"):
        deps.api.set_write_service(anime_write)

    hydration_port = AnimeHydrationAdapter(
        deps.api,
        deps.database,
        write_service=anime_write,
        log_fn=lambda msg: deps.logger.log("ANIME_HYDRATION", msg),
    )
    hydration = AnimeHydrationService(
        hydration_port,
        repository,
        catalog_enrich_fn=deps.db_manager.enrich_catalog_identities_for_ids,
        log_fn=lambda msg: deps.logger.log("ANIME_HYDRATION", msg),
    )
    hydration.start()

    _SEGMENT_SECONDS = 4
    playback_cfg = deps.config.settings.get("playback", {}) or {}
    media_transcoder = FFmpegTranscoderAdapter(
        max_active_sessions=2,
        segment_seconds=_SEGMENT_SECONDS,
        video_encoder=str(playback_cfg.get("video_encoder", "auto")),
    )
    media_streaming = PlaybackService(
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
        hydration_service=hydration,
    )

    anime_cfg = deps.config.settings.get("anime", {}) or {}
    try:
        schedule_limit = int(anime_cfg.get("maxTrendingAnime", 50))
    except (TypeError, ValueError):
        schedule_limit = 50
    startup_jobs = StartupJobsService(
        api_coordinator=metadata.api_coordinator,
        database_manager=deps.db_manager,
        config=deps.config,
        torrent_manager=deps.torrent_manager,
        logger=deps.logger,
        download_adapter=download,
        write_service=anime_write,
        schedule_limit=max(1, schedule_limit),
    )

    return EmbeddedClientFacade(service, startup_jobs=startup_jobs, hydration=hydration)


__all__ = ["build_embedded_facade"]
