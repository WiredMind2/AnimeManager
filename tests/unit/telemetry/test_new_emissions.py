"""Unit tests for the new telemetry emissions (downloads, torrents, playback, ffmpeg).

These tests exercise the counter / gauge / span instrumentation added to the
backend process. They never hit the network, never start real ffmpeg, and never
touch disk (a tmp path is used only as an opaque string where needed).
"""

from __future__ import annotations

import queue
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from shared.telemetry import get_telemetry, reset_telemetry


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class _RecordingSpan:
    def __init__(self, name: str, attributes: dict | None) -> None:
        self.name = name
        self.attributes = dict(attributes or {})
        self.ended = False

    def set_attribute(self, key: str, value) -> None:
        self.attributes[key] = value

    def set_attributes(self, attributes: dict | None) -> None:
        self.attributes.update(attributes or {})

    def record_exception(self, exception: BaseException) -> None:
        pass

    def set_status(self, status) -> None:
        pass

    def end(self) -> None:
        self.ended = True

    def __enter__(self) -> "_RecordingSpan":
        return self

    def __exit__(self, *exc) -> bool:
        self.end()
        return False


class _RecordingTracer:
    def __init__(self) -> None:
        self.spans: list[_RecordingSpan] = []

    @contextmanager
    def start_as_current_span(self, name: str, *args, attributes=None, **kwargs):
        span = _RecordingSpan(name, attributes)
        self.spans.append(span)
        yield span


@pytest.fixture(autouse=True)
def _reset_telemetry():
    reset_telemetry()
    yield
    reset_telemetry()


def _silent_log(*_a, **_kw):
    return None


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------


@pytest.fixture
def DownloadManager():
    from application.services.download_manager import DownloadManager as _DM

    return _DM


@pytest.fixture
def DownloadTask():
    from application.services.download_manager import DownloadTask as _DT

    return _DT


def _wire_manager(mgr) -> None:
    mgr.log = _silent_log
    mgr._prepare_torrent = lambda task: SimpleNamespace(name="n", hash="h", size=10)
    mgr._get_anime_folder = lambda anime_id: "/tmp/anime"
    mgr._save_torrent = lambda *a, **k: None
    mgr._set_user_tag = lambda *a, **k: None
    mgr._start_download = lambda anime_id, torrent: True


def test_download_success_emits_started_completed_and_active_gauge(
    DownloadManager, DownloadTask
):
    mgr = DownloadManager(max_concurrent_downloads=2)
    _wire_manager(mgr)
    try:
        task = DownloadTask(11, hash_value="abc")
        mgr._execute_download(task)

        snap = get_telemetry().snapshot()
        assert snap["counters"]["download.started"] == 1
        assert snap["counters"]["download.completed"] == 1
        assert snap["counters"].get("download.failed", 0) == 0
        # Success keeps the task visible so the active gauge stays at 1.
        assert snap["gauges"]["download.active"] == 1.0
    finally:
        mgr.close()


def test_download_start_failure_emits_failed_and_zeroes_active(
    DownloadManager, DownloadTask
):
    mgr = DownloadManager(max_concurrent_downloads=2)
    _wire_manager(mgr)
    mgr._start_download = lambda anime_id, torrent: False
    try:
        mgr._execute_download(DownloadTask(12, hash_value="abc"))

        snap = get_telemetry().snapshot()
        assert snap["counters"]["download.started"] == 1
        assert snap["counters"]["download.failed"] == 1
        assert snap["counters"].get("download.completed", 0) == 0
        # Failure evicts the task so the active gauge returns to 0.
        assert snap["gauges"]["download.active"] == 0.0
    finally:
        mgr.close()


def test_download_prepare_failure_emits_failed(DownloadManager, DownloadTask):
    mgr = DownloadManager(max_concurrent_downloads=2)
    _wire_manager(mgr)
    mgr._prepare_torrent = lambda task: None
    try:
        mgr._execute_download(DownloadTask(13, hash_value="abc"))

        snap = get_telemetry().snapshot()
        assert snap["counters"]["download.started"] == 1
        assert snap["counters"]["download.failed"] == 1
        assert snap["gauges"]["download.active"] == 0.0
    finally:
        mgr.close()


def test_download_exception_emits_failed(DownloadManager, DownloadTask):
    mgr = DownloadManager(max_concurrent_downloads=2)
    _wire_manager(mgr)

    def _boom(anime_id, torrent):
        raise RuntimeError("boom")

    mgr._start_download = _boom
    try:
        mgr._execute_download(DownloadTask(14, hash_value="abc"))

        snap = get_telemetry().snapshot()
        assert snap["counters"]["download.started"] == 1
        assert snap["counters"]["download.failed"] == 1
        assert snap["gauges"]["download.active"] == 0.0
    finally:
        mgr.close()


def test_cancel_download_updates_active_gauge(DownloadManager, DownloadTask):
    mgr = DownloadManager(max_concurrent_downloads=2)
    _wire_manager(mgr)
    try:
        task = DownloadTask(15, hash_value="abc")
        with mgr._lock:
            mgr._active_downloads[15] = task
        get_telemetry().set_gauge("download.active", 1.0)

        assert mgr.cancel_download(15) is True

        snap = get_telemetry().snapshot()
        assert snap["gauges"]["download.active"] == 0.0
    finally:
        mgr.close()


# ---------------------------------------------------------------------------
# Torrents (LibTorrentRemote)
# ---------------------------------------------------------------------------


def _response(payload):
    mock = MagicMock()
    mock.status_code = 200
    mock.content = b"{}"
    mock.json.return_value = payload
    return mock


def test_torrent_restore_count_and_active_gauge(monkeypatch):
    from adapters.torrent.libtorrent_remote import LibTorrentRemote

    monkeypatch.setenv("LIBTORRENT_DAEMON_URL", "http://torrent:8090")
    monkeypatch.setenv("LIBTORRENT_DAEMON_TOKEN", "secret")

    def _request(method, url, **kwargs):
        if url.endswith("/health"):
            return _response({"ready": True})
        if url.endswith("/session/ensure-restored"):
            return _response({"ok": True, "torrent_count": 2})
        if url.endswith("/torrents") and method == "GET":
            return _response({"torrents": [{"hash": "a"}, {"hash": "b"}]})
        raise AssertionError((method, url))

    with patch("adapters.torrent.libtorrent_remote.requests.request", side_effect=_request):
        mgr = LibTorrentRemote({}, update=False)
        mgr.set_restore_callback(lambda: [])
        mgr.ensure_restored()

    snap = get_telemetry().snapshot()
    assert snap["counters"]["torrent.restore_count"] == 1
    assert snap["gauges"]["torrent.active"] == 2.0


def test_torrent_active_gauge_zero_when_no_handles(monkeypatch):
    from adapters.torrent.libtorrent_remote import LibTorrentRemote

    monkeypatch.setenv("LIBTORRENT_DAEMON_URL", "http://torrent:8090")
    monkeypatch.setenv("LIBTORRENT_DAEMON_TOKEN", "secret")

    def _request(method, url, **kwargs):
        if url.endswith("/health"):
            return _response({"ready": True})
        if url.endswith("/torrents") and method == "GET":
            return _response({"torrents": []})
        raise AssertionError((method, url))

    with patch("adapters.torrent.libtorrent_remote.requests.request", side_effect=_request):
        mgr = LibTorrentRemote({}, update=False)
        mgr._refresh_handles()

    snap = get_telemetry().snapshot()
    assert snap["gauges"]["torrent.active"] == 0.0


def test_reconcile_deleted_emits_counter(DownloadManager):
    mgr = DownloadManager(max_concurrent_downloads=1)
    mgr.log = _silent_log
    try:
        rows = [
            {"hash": "h1", "status": "complete", "anime_id": 1, "save_path": "/gone"},
        ]

        db = MagicMock()
        db.list_torrents_for_reconcile.return_value = rows
        updates: list[tuple] = []

        def _update(hash_val, status):
            updates.append((hash_val, status))

        db.update_torrent_status = _update
        mgr._database_manager = db
        mgr._lookup_live_torrent = lambda h: None
        mgr._remove_torrent_from_client = lambda h, delete_files=False: None
        # No video files on disk -> reconcile marks the torrent deleted.
        mgr._scanner = SimpleNamespace(resolve_anime_folder=lambda aid: "/missing")

        marked = mgr.reconcile_deleted_torrents(lambda aid: "/missing")

        assert marked == 1
        snap = get_telemetry().snapshot()
        assert snap["counters"]["torrent.reconcile_deleted"] == 1
        assert ("h1", "deleted") in updates
    finally:
        mgr.close()


# ---------------------------------------------------------------------------
# Playback spans
# ---------------------------------------------------------------------------


def _build_playback_service():
    from application.playback.service import PlaybackService

    media_library = MagicMock()
    transcoder = MagicMock()
    service = PlaybackService(
        media_library=media_library,
        transcoder=transcoder,
        token_secret="test-secret",
    )
    return service


def test_playback_create_session_span_records_anime_and_session():
    from application.commands.media_streaming import CreatePlaybackSessionCommand

    service = _build_playback_service()
    tracer = _RecordingTracer()
    service._tracer = tracer

    captured = {}

    def _impl(command, span):
        captured["span"] = span
        span.set_attribute("session_id", "sess-123")
        return MagicMock(session_id="sess-123")

    service._create_session_impl = _impl

    cmd = CreatePlaybackSessionCommand(anime_id=42, file_id="file-7")
    service.create_session(cmd)

    assert len(tracer.spans) == 1
    span = tracer.spans[0]
    assert span.name == "playback.create_session"
    assert span.attributes["anime_id"] == 42
    assert span.attributes["session_id"] == "sess-123"


def test_playback_resolve_segment_span_records_session_and_segment(tmp_path):
    from application.dto.media_streaming import PlaybackSessionDTO
    from application.queries.media_streaming import GetPlaybackSessionQuery

    service = _build_playback_service()
    tracer = _RecordingTracer()
    service._tracer = tracer
    service._ensure_segment = lambda session, segment_name, target: None

    session_id = "sess-abc"
    output_dir = str(tmp_path)
    segment_name = "segment_00000.ts"
    target = tmp_path / segment_name
    target.write_bytes(b"ts")

    token = service._tokens.build(session_id=session_id, expires_at=time.time() + 3600)
    dto = PlaybackSessionDTO(
        session_id=session_id,
        anime_id=42,
        file_id="file-7",
        file_title="ep1",
        manifest_path=str(tmp_path / "index.m3u8"),
        output_dir=output_dir,
        token=token,
        expires_at=time.time() + 3600,
        created_at=time.time(),
        last_seen_at=time.time(),
        total_segments=10,
        segment_seconds=4,
    )
    with service._lock:
        service._sessions[session_id] = dto

    service.resolve_media_path(
        GetPlaybackSessionQuery(session_id=session_id, token=token, segment_name=segment_name)
    )

    span_names = [s.name for s in tracer.spans]
    assert "playback.resolve_segment" in span_names
    seg_span = next(s for s in tracer.spans if s.name == "playback.resolve_segment")
    assert seg_span.attributes["session_id"] == session_id
    assert seg_span.attributes["segment"] == segment_name


# ---------------------------------------------------------------------------
# FFmpeg
# ---------------------------------------------------------------------------


def _ffmpeg_adapter(tmp_path, *, max_active=2):
    from adapters.media.ffmpeg_transcoder import FFmpegTranscoderAdapter

    adapter = FFmpegTranscoderAdapter(
        video_encoder="libx264", max_active_sessions=max_active
    )
    return adapter


def test_ffmpeg_transcodes_started_counter_and_span(tmp_path):
    adapter = _ffmpeg_adapter(tmp_path)
    tracer = _RecordingTracer()
    adapter._tracer = tracer

    output_dir = tmp_path / "sess-1"
    output_dir.mkdir()
    # Pre-write the manifest so the legacy "wait for initial manifest" path
    # is skipped — we only want to assert the spawn counter + span.
    (output_dir / "index.m3u8").write_text("#EXTM3U\n")

    fake_process = MagicMock()
    fake_process.poll.return_value = None  # still running

    adapter._spawn_ffmpeg = lambda command, log_path: fake_process
    adapter._write_spawn_record = lambda *a, **k: None

    adapter.ensure_hls_session(
        session_id="sess-1",
        source_path=str(tmp_path / "sample.mkv"),
        output_dir=str(output_dir),
        start_segment_index=0,
        segment_seconds=4,
    )

    snap = get_telemetry().snapshot()
    assert snap["counters"]["ffmpeg.transcodes_started"] == 1
    assert snap["counters"].get("ffmpeg.failures", 0) == 0
    span_names = [s.name for s in tracer.spans]
    assert "ffmpeg.transcode" in span_names
    span = next(s for s in tracer.spans if s.name == "ffmpeg.transcode")
    assert span.attributes["session_id"] == "sess-1"
    assert span.attributes["encoder"] == "libx264"


def test_ffmpeg_failures_incremented_on_crashed_reap():
    from adapters.media.ffmpeg_transcoder import FFmpegTranscoderAdapter, _ActiveTranscode

    adapter = FFmpegTranscoderAdapter(video_encoder="libx264")

    crashed = MagicMock()
    crashed.poll.return_value = 1
    crashed.returncode = 1
    adapter._active["sess-dead"] = _ActiveTranscode(
        session_id="sess-dead",
        output_dir="/tmp/sess-dead",
        manifest_path="/tmp/sess-dead/index.m3u8",
        process=crashed,
        started_at=time.time(),
        start_segment_index=0,
        segment_seconds=4,
        source_path="/tmp/sample.mkv",
        audio_track=None,
        subtitle_track=None,
    )

    with adapter._lock:
        adapter._reap_finished_locked()

    snap = get_telemetry().snapshot()
    assert snap["counters"]["ffmpeg.failures"] == 1


def test_ffmpeg_failures_not_incremented_on_clean_exit():
    from adapters.media.ffmpeg_transcoder import FFmpegTranscoderAdapter, _ActiveTranscode

    adapter = FFmpegTranscoderAdapter(video_encoder="libx264")

    clean = MagicMock()
    clean.poll.return_value = 0
    clean.returncode = 0
    adapter._active["sess-ok"] = _ActiveTranscode(
        session_id="sess-ok",
        output_dir="/tmp/sess-ok",
        manifest_path="/tmp/sess-ok/index.m3u8",
        process=clean,
        started_at=time.time(),
        start_segment_index=0,
        segment_seconds=4,
        source_path="/tmp/sample.mkv",
        audio_track=None,
        subtitle_track=None,
    )

    with adapter._lock:
        adapter._reap_finished_locked()

    snap = get_telemetry().snapshot()
    assert snap["counters"].get("ffmpeg.failures", 0) == 0


def test_ffmpeg_failures_incremented_on_early_manifest_exit():
    from adapters.media.ffmpeg_transcoder import FFmpegTranscoderAdapter
    from domain.errors import InfrastructureError

    adapter = FFmpegTranscoderAdapter(video_encoder="libx264")

    dead = MagicMock()
    dead.poll.return_value = 1
    dead.returncode = 1
    adapter._active["sess-early"] = MagicMock()

    with pytest.raises(InfrastructureError):
        adapter._wait_for_initial_manifest(
            session_id="sess-early",
            process=dead,
            manifest_path="/tmp/sess-early/index.m3u8",
        )

    snap = get_telemetry().snapshot()
    assert snap["counters"]["ffmpeg.failures"] == 1
