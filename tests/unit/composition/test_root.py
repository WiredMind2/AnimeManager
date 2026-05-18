"""Tests for :mod:`composition.root` dependency wiring.

Heavy collaborators (legacy runtime, database, torrent, FFmpeg) are mocked
so these tests only verify the composition graph, not adapter behaviour.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import composition
from composition.facade import EmbeddedClientFacade
from composition.root import build_embedded_facade

_SEGMENT_SECONDS = 4


@pytest.fixture
def wiring_mocks():
    """Patch every concrete adapter/service constructed by the composition root."""
    patches = {
        "runtime": patch("composition.root.LegacyRuntime"),
        "repository": patch("composition.root.LegacyAnimeRepositoryAdapter"),
        "metadata": patch("composition.root.LegacyMetadataProviderAdapter"),
        "download": patch("composition.root.LegacyDownloadAdapter"),
        "user_actions": patch("composition.root.LegacyUserActionsAdapter"),
        "media_library": patch("composition.root.LegacyMediaLibraryAdapter"),
        "transcoder": patch("composition.root.FFmpegTranscoderAdapter"),
        "media_streaming": patch("composition.root.MediaStreamingService"),
        "service": patch("composition.root.AnimeApplicationService"),
        "startup_jobs": patch("composition.root.StartupJobsService"),
    }
    started = {name: p.start() for name, p in patches.items()}
    try:
        runtime = MagicMock(name="runtime")
        started["runtime"].return_value = runtime

        repository = MagicMock(name="repository")
        repository._db_manager = MagicMock(name="db_manager")
        started["repository"].return_value = repository

        metadata = MagicMock(name="metadata")
        metadata._api_coordinator = MagicMock(name="api_coordinator")
        started["metadata"].return_value = metadata

        download = MagicMock(name="download")
        started["download"].return_value = download

        user_actions = MagicMock(name="user_actions")
        started["user_actions"].return_value = user_actions

        media_library = MagicMock(name="media_library")
        started["media_library"].return_value = media_library

        transcoder = MagicMock(name="transcoder")
        started["transcoder"].return_value = transcoder

        media_streaming = MagicMock(name="media_streaming")
        started["media_streaming"].return_value = media_streaming

        service = MagicMock(name="anime_service")
        started["service"].return_value = service

        startup_jobs = MagicMock(name="startup_jobs")
        started["startup_jobs"].return_value = startup_jobs

        yield SimpleNamespace(
            runtime=runtime,
            repository=repository,
            metadata=metadata,
            download=download,
            user_actions=user_actions,
            media_library=media_library,
            transcoder=transcoder,
            media_streaming=media_streaming,
            service=service,
            startup_jobs=startup_jobs,
            classes=started,
        )
    finally:
        for p in reversed(list(patches.values())):
            p.stop()


def test_build_embedded_facade_returns_embedded_client_facade(wiring_mocks):
    facade = build_embedded_facade()

    assert isinstance(facade, EmbeddedClientFacade)
    assert facade._service is wiring_mocks.service
    assert facade._startup_jobs is wiring_mocks.startup_jobs


def test_build_embedded_facade_instantiates_legacy_graph(wiring_mocks):
    build_embedded_facade()

    wiring_mocks.classes["runtime"].assert_called_once_with()
    wiring_mocks.classes["repository"].assert_called_once_with(
        wiring_mocks.runtime
    )
    wiring_mocks.classes["metadata"].assert_called_once_with(
        wiring_mocks.runtime,
        wiring_mocks.repository,
    )
    wiring_mocks.classes["download"].assert_called_once_with(
        wiring_mocks.runtime,
        repository=wiring_mocks.repository,
    )
    wiring_mocks.classes["user_actions"].assert_called_once_with(
        wiring_mocks.runtime
    )
    wiring_mocks.classes["media_library"].assert_called_once_with(
        wiring_mocks.runtime,
        download_port=wiring_mocks.download,
    )


def test_build_embedded_facade_configures_nvenc_transcoder(wiring_mocks):
    build_embedded_facade()

    wiring_mocks.classes["transcoder"].assert_called_once_with(
        video_codec="h264_nvenc",
        require_hardware_acceleration=True,
        use_cuda_hwaccel=False,
        max_active_sessions=2,
        segment_seconds=_SEGMENT_SECONDS,
    )


def test_build_embedded_facade_aligns_media_streaming_segment_seconds(wiring_mocks):
    build_embedded_facade()

    wiring_mocks.classes["media_streaming"].assert_called_once_with(
        media_library=wiring_mocks.media_library,
        transcoder=wiring_mocks.transcoder,
        segment_seconds=_SEGMENT_SECONDS,
    )


def test_build_embedded_facade_wires_anime_application_service(wiring_mocks):
    build_embedded_facade()

    wiring_mocks.classes["service"].assert_called_once_with(
        anime_repository=wiring_mocks.repository,
        metadata_provider=wiring_mocks.metadata,
        download_port=wiring_mocks.download,
        user_actions_port=wiring_mocks.user_actions,
        media_streaming_service=wiring_mocks.media_streaming,
    )


def test_build_embedded_facade_startup_jobs_share_legacy_pipeline(wiring_mocks):
    build_embedded_facade()

    wiring_mocks.classes["startup_jobs"].assert_called_once_with(
        api_coordinator=wiring_mocks.metadata._api_coordinator,
        database_manager=wiring_mocks.repository._db_manager,
        runtime=wiring_mocks.runtime,
    )


def test_composition_package_exports_build_embedded_facade():
    assert composition.build_embedded_facade is build_embedded_facade
    assert composition.__all__ == ["build_embedded_facade"]
