"""Missing ffmpeg must not be reported as an incomplete episode file."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.commands import CreatePlaybackSessionCommand
from application.playback.service import PlaybackService
from application.queries import ListEpisodeFilesQuery
from domain.errors import InfrastructureError, ValidationError


class _FakeLibrary:
    def __init__(self, root: Path) -> None:
        self._root = root
        ep = root / "ep.mkv"
        ep.write_bytes(b"not a real video")
        self._path = str(ep)

    def list_episode_files(self, anime_id: int):
        _ = anime_id
        return [
            {
                "file_id": "ep-1",
                "title": "ep.mkv",
                "path": self._path,
                "size_bytes": 16,
            }
        ]

    def delete_episode_file(self, anime_id: int, file_id: str) -> bool:
        _ = anime_id, file_id
        return False

    def get_stream_cache_root(self) -> str:
        cache = self._root / "stream-cache"
        cache.mkdir(exist_ok=True)
        return str(cache)


class _MissingToolsTranscoder:
    def probe_tools_available(self) -> bool:
        return False

    def require_probe_tools(self) -> None:
        raise InfrastructureError(
            "Playback is unavailable because ffmpeg/ffprobe was not found. "
            "Run `.venv/Scripts/python.exe scripts/install_ffmpeg.py` "
            "(or install ffmpeg on PATH), then restart the app."
        )

    def probe_media_tracks(self, source_path: str):
        _ = source_path
        self.require_probe_tools()

    def probe_media_duration(self, source_path: str) -> float:
        _ = source_path
        self.require_probe_tools()
        return 0.0

    def ensure_hls_session(self, **kwargs):
        _ = kwargs
        self.require_probe_tools()
        return {}

    def stop_hls_session(self, session_id: str) -> None:
        _ = session_id

    def is_hls_session_running(self, session_id: str) -> bool:
        _ = session_id
        return False

    def materialize_subtitle_tracks(self, **kwargs):
        _ = kwargs
        return []


class _UnreadableTranscoder:
    def probe_tools_available(self) -> bool:
        return True

    def require_probe_tools(self) -> None:
        return None

    def probe_media_tracks(self, source_path: str):
        _ = source_path
        return {"audio": [], "subtitles": []}

    def probe_media_duration(self, source_path: str) -> float:
        _ = source_path
        return 0.0

    def ensure_hls_session(self, **kwargs):
        _ = kwargs
        return {"manifest_path": ""}

    def stop_hls_session(self, session_id: str) -> None:
        _ = session_id

    def is_hls_session_running(self, session_id: str) -> bool:
        _ = session_id
        return False

    def materialize_subtitle_tracks(self, **kwargs):
        _ = kwargs
        return []


def test_list_episode_files_sets_ffmpeg_missing_blocker(tmp_path: Path):
    svc = PlaybackService(
        media_library=_FakeLibrary(tmp_path),
        transcoder=_MissingToolsTranscoder(),
        token_secret="test-secret",
    )
    rows = svc.list_episode_files(ListEpisodeFilesQuery(anime_id=1))
    assert len(rows) == 1
    assert rows[0].playback_blocker == "ffmpeg_missing"
    assert rows[0].audio_tracks == []
    assert rows[0].duration_seconds is None


def test_create_session_missing_ffmpeg_is_infrastructure_error(tmp_path: Path):
    svc = PlaybackService(
        media_library=_FakeLibrary(tmp_path),
        transcoder=_MissingToolsTranscoder(),
        token_secret="test-secret",
    )
    with pytest.raises(InfrastructureError, match=r"install_ffmpeg|ffprobe"):
        svc.create_session(
            CreatePlaybackSessionCommand(
                anime_id=1,
                file_id="ep-1",
                client_host="127.0.0.1",
                ttl_seconds=120,
            )
        )


def test_create_session_unreadable_media_still_validation_error(tmp_path: Path):
    svc = PlaybackService(
        media_library=_FakeLibrary(tmp_path),
        transcoder=_UnreadableTranscoder(),
        token_secret="test-secret",
    )
    with pytest.raises(ValidationError, match=r"can't be played yet"):
        svc.create_session(
            CreatePlaybackSessionCommand(
                anime_id=1,
                file_id="ep-1",
                client_host="127.0.0.1",
                ttl_seconds=120,
            )
        )
