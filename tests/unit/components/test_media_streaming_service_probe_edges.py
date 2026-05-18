"""Probe cache, auth, and listing tests for :class:`MediaStreamingService`."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import pytest

from application.commands import CreatePlaybackSessionCommand
from application.queries import GetPlaybackSessionQuery
from application.services.media_streaming_service import MediaStreamingService
from domain.errors import NotFoundError, UnauthorizedError, ValidationError


class _Library:
    def __init__(self, tmp_path: Path, rows: list[dict] | None = None):
        self._root = tmp_path / "streams"
        self._rows = rows or []

    def list_episode_files(self, anime_id: int):
        _ = anime_id
        return list(self._rows)

    def get_stream_cache_root(self) -> str:
        self._root.mkdir(parents=True, exist_ok=True)
        return str(self._root)

    def delete_episode_file(self, anime_id: int, file_id: str) -> bool:
        _ = (anime_id, file_id)
        return True


class _ProbeTranscoder:
    def __init__(self, *, metadata=None, duration=90.0, subs=None):
        self._metadata = metadata
        self._duration = duration
        self._subs = subs or []
        self.probe_calls = 0

    def ensure_hls_session(self, **kwargs):
        out = Path(kwargs["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        manifest = out / "index.m3u8"
        manifest.write_text("#EXTM3U\n", encoding="utf-8")
        return {"manifest_path": str(manifest)}

    def stop_hls_session(self, session_id: str) -> None:
        _ = session_id

    def probe_media_metadata(self, source_path: str):
        self.probe_calls += 1
        if self._metadata is not None:
            return self._metadata
        return (
            {"audio": [{"id": 0}], "subtitles": []},
            self._duration,
        )

    def probe_media_tracks(self, source_path: str):
        _ = source_path
        return {"audio": [{"id": 0}], "subtitles": []}

    def probe_media_duration(self, source_path: str) -> float:
        _ = source_path
        return self._duration

    def materialize_subtitle_tracks(self, *, source_path: str, output_dir: str):
        _ = (source_path, output_dir)
        return self._subs


def _service(tmp_path: Path, **kwargs) -> MediaStreamingService:
    return MediaStreamingService(
        media_library=_Library(tmp_path, kwargs.pop("rows", None)),
        transcoder=kwargs.pop("transcoder", _ProbeTranscoder()),
        token_secret="unit-test-secret",
        default_ttl_seconds=120,
        **kwargs,
    )


def test_list_episode_files_parallel_probe(tmp_path: Path):
    ep1 = tmp_path / "a.mkv"
    ep2 = tmp_path / "b.mkv"
    ep1.write_bytes(b"a")
    ep2.write_bytes(b"b")
    transcoder = _ProbeTranscoder()
    svc = _service(
        tmp_path,
        transcoder=transcoder,
        rows=[
            {"file_id": "ep-1", "path": str(ep1), "title": "A"},
            {"file_id": "ep-2", "path": str(ep2), "title": "B"},
        ],
        probe_parallel_workers=2,
    )
    from application.queries import ListEpisodeFilesQuery

    files = svc.list_episode_files(ListEpisodeFilesQuery(anime_id=1))
    assert len(files) == 2
    assert transcoder.probe_calls >= 2


def test_list_episode_files_skips_invalid_rows(tmp_path: Path):
    svc = _service(
        tmp_path,
        rows=[
            {"file_id": "", "path": "/missing"},
            {"file_id": "ok", "path": ""},
        ],
    )
    from application.queries import ListEpisodeFilesQuery

    assert svc.list_episode_files(ListEpisodeFilesQuery(anime_id=1)) == []


def test_resolve_manifest_rejects_bad_token(tmp_path: Path):
    ep = tmp_path / "ep.mkv"
    ep.write_bytes(b"v")
    svc = _service(
        tmp_path,
        rows=[{"file_id": "ep-1", "path": str(ep), "title": "E1"}],
    )
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
        )
    )
    with pytest.raises(UnauthorizedError):
        svc.resolve_media_path(
            GetPlaybackSessionQuery(
                session_id=session.session_id,
                token="not-a-valid-token",
            )
        )


def test_cleanup_stale_sessions_removes_expired(tmp_path: Path):
    ep = tmp_path / "ep.mkv"
    ep.write_bytes(b"v")
    svc = _service(
        tmp_path,
        rows=[{"file_id": "ep-1", "path": str(ep), "title": "E1"}],
    )
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=60,
        )
    )
    with svc._lock:
        stored = svc._sessions[session.session_id]
        svc._sessions[session.session_id] = replace(
            stored, expires_at=time.time() - 1
        )
    svc.cleanup_stale_sessions()
    assert session.session_id not in svc._sessions


def test_create_session_materializes_subtitles(tmp_path: Path):
    ep = tmp_path / "ep.mkv"
    ep.write_bytes(b"v")
    transcoder = _ProbeTranscoder(
        subs=[
            {
                "id": 0,
                "label": "EN",
                "filename": "sub_0.vtt",
                "codec": "subrip",
                "ass_filename": "sub_0.ass",
            },
            {"id": "bad", "filename": ""},
        ]
    )
    svc = _service(
        tmp_path,
        transcoder=transcoder,
        rows=[{"file_id": "ep-1", "path": str(ep), "title": "E1"}],
    )
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
        )
    )
    assert session.subtitle_tracks[0]["filename"] == "sub_0.vtt"


def test_create_session_missing_file_raises(tmp_path: Path):
    svc = _service(tmp_path, rows=[{"file_id": "ep-1", "path": "/nope/file.mkv", "title": "X"}])
    with pytest.raises(NotFoundError):
        svc.create_session(
            CreatePlaybackSessionCommand(
                anime_id=1,
                file_id="ep-1",
                client_host="127.0.0.1",
                ttl_seconds=120,
            )
        )


def test_validate_segment_name_rejects_unsafe_paths():
    from application.services.media_streaming_service import _validate_segment_name

    with pytest.raises(ValidationError):
        _validate_segment_name("../escape.ts")
