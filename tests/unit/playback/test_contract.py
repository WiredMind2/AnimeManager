"""Contract tests for the playback rewrite."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from application.commands import CreatePlaybackSessionCommand
from application.playback.contract import PREFETCH_MARGIN, SEGMENT_SECONDS
from application.playback.playlist import render_manifest
from application.playback.resume import anchor_segment, resume_segment_index
from application.playback.service import PlaybackService
from application.dto import PlaybackSessionDTO
from application.queries import GetPlaybackSessionQuery


class _FakeLibrary:
    def __init__(self, tmp_path: Path) -> None:
        self._root = tmp_path / "streams"
        self._episode = tmp_path / "episode.mkv"
        self._episode.write_bytes(b"video")

    def list_episode_files(self, anime_id: int):
        _ = anime_id
        return [
            {
                "file_id": "ep-1",
                "path": str(self._episode),
                "title": "Episode 1",
                "season": 1,
                "episode": 1,
            }
        ]

    def get_stream_cache_root(self) -> str:
        self._root.mkdir(parents=True, exist_ok=True)
        return str(self._root)

    def delete_episode_file(self, anime_id: int, file_id: str) -> bool:
        _ = (anime_id, file_id)
        return False


class _IncrementalFakeTranscoder:
    def __init__(self, duration: float, *, delay_seconds: float = 0.05) -> None:
        self._duration = duration
        self._delay = delay_seconds
        self.calls: list[dict[str, object]] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def ensure_hls_session(
        self,
        *,
        session_id: str,
        source_path: str,
        output_dir: str,
        audio_track: int | None = None,
        subtitle_track: int | None = None,
        start_segment_index: int = 0,
        segment_seconds: int | None = None,
        duration_seconds: float | None = None,
    ):
        _ = (session_id, source_path, audio_track, subtitle_track, duration_seconds)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.calls.append(
                {"start_segment_index": start_segment_index, "segment_seconds": segment_seconds}
            )
            self._stop_event.set()
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=2.0)
            self._stop_event = threading.Event()

            def _encode() -> None:
                idx = start_segment_index
                while not self._stop_event.is_set():
                    path = out / f"segment_{idx:05d}.ts"
                    if not path.is_file():
                        path.write_bytes(b"seg")
                    idx += 1
                    time.sleep(self._delay)

            self._thread = threading.Thread(target=_encode, daemon=True)
            self._thread.start()
        return {"manifest_path": str(out / "index.m3u8")}

    def stop_hls_session(self, session_id: str) -> None:
        _ = session_id
        self._stop_event.set()

    def probe_media_tracks(self, source_path: str):
        _ = source_path
        return {"audio": [{"id": 0, "label": "UND"}], "subtitles": []}

    def probe_media_duration(self, source_path: str) -> float:
        _ = source_path
        return self._duration


def _service(tmp_path: Path, duration: float = 3600.0) -> tuple[PlaybackService, _IncrementalFakeTranscoder]:
    transcoder = _IncrementalFakeTranscoder(duration)
    svc = PlaybackService(
        media_library=_FakeLibrary(tmp_path),
        transcoder=transcoder,
        token_secret="test-secret",
        segment_seconds=SEGMENT_SECONDS,
    )
    return svc, transcoder


def test_manifest_has_no_ext_x_start_and_full_timeline(tmp_path: Path):
    session = PlaybackSessionDTO(
        session_id="s",
        anime_id=1,
        file_id="ep-1",
        file_title="Ep",
        manifest_path=str(tmp_path / "index.m3u8"),
        output_dir=str(tmp_path),
        token="t",
        expires_at=0.0,
        created_at=0.0,
        last_seen_at=0.0,
        duration_seconds=130.0,
        segment_seconds=4,
        total_segments=33,
    )
    text = render_manifest(session)
    assert "#EXT-X-START" not in text
    assert "#EXT-X-MEDIA-SEQUENCE:0" in text
    assert "segment_00000.ts" in text
    assert "segment_00032.ts" in text
    assert "#EXTINF:2.000," in text


def test_resume_segment_and_anchor_math():
    assert resume_segment_index(708.0, total_segments=900, segment_seconds=4) == 177
    assert anchor_segment(177) == 177 - PREFETCH_MARGIN
    assert resume_segment_index(1420.0, total_segments=900, segment_seconds=4) == 355
    assert anchor_segment(355) == 355 - PREFETCH_MARGIN


def test_create_session_waits_for_resume_playhead_segment(tmp_path: Path):
    svc, transcoder = _service(tmp_path)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
            start_time_seconds=708.0,
        )
    )
    assert session.playback_start_seconds == pytest.approx(708.0)
    assert session.hls_anchor_segment == anchor_segment(177)
    assert (Path(session.output_dir) / "segment_00177.ts").is_file()
    assert transcoder.calls


def test_far_ahead_segment_on_fresh_start_restarts_encoder(tmp_path: Path):
    """Fresh sessions anchor at 0; far-ahead segments restart ffmpeg rather than 404."""
    svc, transcoder = _service(tmp_path)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
        )
    )
    assert session.hls_anchor_segment == 0
    assert session.playback_start_seconds == 0.0
    _session, seg_path = svc.resolve_media_path(
        GetPlaybackSessionQuery(
            session_id=session.session_id,
            token=session.token,
            segment_name="segment_00050.ts",
        )
    )
    assert Path(seg_path).is_file()
    assert len(transcoder.calls) >= 2
