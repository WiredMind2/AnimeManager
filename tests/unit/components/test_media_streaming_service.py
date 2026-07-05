from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from application.commands import (
    CreatePlaybackSessionCommand,
    HeartbeatPlaybackSessionCommand,
    StopPlaybackSessionCommand,
)
from application.queries import GetPlaybackSessionQuery
from application.playback.resume import anchor_segment, resume_segment_index
from application.playback.service import PlaybackService
from domain.errors import NotFoundError, UnauthorizedError, ValidationError


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


class _SeekableFakeTranscoder:
    """A modern adapter that supports the seek-on-demand API: it
    records each ``ensure_hls_session`` call and produces the first
    couple of segments starting from ``start_segment_index`` so the
    test can drive the service into a restart."""

    def __init__(self, duration: float) -> None:
        self._duration = duration
        self.calls: list[dict[str, object]] = []
        self._output_dir: Path | None = None

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
        _ = duration_seconds
        _ = (session_id, source_path, audio_track, subtitle_track)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        self._output_dir = out
        self.calls.append(
            {
                "start_segment_index": start_segment_index,
                "segment_seconds": segment_seconds,
            }
        )
        # Materialise the anchor run through playhead + prefetch slack.
        for offset in range(8):
            seg = out / f"segment_{start_segment_index + offset:05d}.ts"
            seg.write_bytes(b"seg")
        return {
            "manifest_path": str(out / "index.m3u8"),
            "output_dir": str(out),
            "start_segment_index": str(start_segment_index),
            "segment_seconds": str(segment_seconds),
        }

    def stop_hls_session(self, session_id: str) -> None:
        _ = session_id

    def probe_media_tracks(self, source_path: str):
        _ = source_path
        return {"audio": [{"id": 0, "label": "UND"}], "subtitles": []}

    def probe_media_duration(self, source_path: str) -> float:
        _ = source_path
        return self._duration


class _IncrementalFakeTranscoder:
    """Simulates real ffmpeg: segments appear one-by-one after a delay.

    Restarts cancel the in-flight encode thread, mirroring process kill."""

    def __init__(self, duration: float, *, delay_seconds: float = 2.0) -> None:
        self._duration = duration
        self._delay = delay_seconds
        self.calls: list[dict[str, object]] = []
        self._lock = threading.Lock()
        self._encoder_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False
        self._session_id: str | None = None

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
        _ = duration_seconds
        _ = (source_path, audio_track, subtitle_track)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.calls.append(
                {
                    "start_segment_index": start_segment_index,
                    "segment_seconds": segment_seconds,
                }
            )
            self._stop_event.set()
            if self._encoder_thread is not None and self._encoder_thread.is_alive():
                self._encoder_thread.join(timeout=3.0)
            self._stop_event = threading.Event()
            self._session_id = session_id
            self._running = True
            self._encoder_thread = threading.Thread(
                target=self._encode_loop,
                args=(out, start_segment_index, self._stop_event),
                daemon=True,
            )
            self._encoder_thread.start()
        return {
            "manifest_path": str(out / "index.m3u8"),
            "output_dir": str(out),
            "start_segment_index": str(start_segment_index),
            "segment_seconds": str(segment_seconds),
        }

    def _encode_loop(
        self,
        out: Path,
        start_index: int,
        stop: threading.Event,
    ) -> None:
        for offset in range(8):
            if stop.is_set():
                return
            if offset == 0:
                if stop.wait(0.05):
                    return
            else:
                if stop.wait(self._delay):
                    return
            if stop.is_set():
                return
            seg = out / f"segment_{start_index + offset:05d}.ts"
            seg.write_bytes(b"segment-bytes")
        with self._lock:
            self._running = False

    def is_hls_session_running(self, session_id: str) -> bool:
        with self._lock:
            return self._running and self._session_id == session_id

    def stop_hls_session(self, session_id: str) -> None:
        _ = session_id
        with self._lock:
            self._stop_event.set()
            self._running = False

    def probe_media_tracks(self, source_path: str):
        _ = source_path
        return {"audio": [{"id": 0, "label": "UND"}], "subtitles": []}

    def probe_media_duration(self, source_path: str) -> float:
        _ = source_path
        return self._duration


def _legacy_service(tmp_path: Path) -> PlaybackService:
    return _seekable_service(tmp_path, duration=600.0)[0]


def _seekable_service(
    tmp_path: Path,
    duration: float,
    *,
    segment_seconds: int = 4,
) -> tuple[PlaybackService, _SeekableFakeTranscoder]:
    transcoder = _SeekableFakeTranscoder(duration=duration)
    svc = PlaybackService(
        media_library=_FakeLibrary(tmp_path),
        transcoder=transcoder,
        token_secret="test-secret",
        default_ttl_seconds=120,
        segment_seconds=segment_seconds,
    )
    return svc, transcoder


def _incremental_service(
    tmp_path: Path,
    duration: float,
    *,
    segment_seconds: int = 4,
    delay_seconds: float = 2.0,
) -> tuple[PlaybackService, _IncrementalFakeTranscoder]:
    transcoder = _IncrementalFakeTranscoder(duration, delay_seconds=delay_seconds)
    svc = PlaybackService(
        media_library=_FakeLibrary(tmp_path),
        transcoder=transcoder,
        token_secret="test-secret",
        default_ttl_seconds=120,
        segment_seconds=segment_seconds,
    )
    return svc, transcoder


class _ZeroProbeFakeTranscoder(_SeekableFakeTranscoder):
    """Probe returns zero duration but tracks are present (incomplete metadata)."""

    def __init__(self) -> None:
        super().__init__(duration=0.0)


class _ProbeSequenceFakeTranscoder(_SeekableFakeTranscoder):
    """Returns probe durations from a sequence — simulates list vs create re-probe."""

    def __init__(self, durations: list[float]) -> None:
        super().__init__(duration=durations[0] if durations else 0.0)
        self._durations = list(durations)
        self._probe_calls = 0

    def probe_media_duration(self, source_path: str) -> float:
        _ = source_path
        idx = min(self._probe_calls, len(self._durations) - 1)
        self._probe_calls += 1
        return self._durations[idx]


class _DeadEncoderResumeFake(_SeekableFakeTranscoder):
    """After create, encoder can be marked dead and segments deleted for resolve tests."""

    def __init__(self, duration: float) -> None:
        super().__init__(duration)
        self._running = True

    def ensure_hls_session(self, **kwargs):
        result = super().ensure_hls_session(**kwargs)
        self._running = True
        return result

    def is_hls_session_running(self, session_id: str) -> bool:
        _ = session_id
        return self._running

    def kill_encoder(self) -> None:
        self._running = False

    def stop_hls_session(self, session_id: str) -> None:
        _ = session_id
        self._running = False


class _UnreadableFakeTranscoder(_SeekableFakeTranscoder):
    """Probe behaviour of an incomplete torrent file: no duration and
    no tracks at all (ffprobe cannot read the container header)."""

    def __init__(self) -> None:
        super().__init__(duration=0.0)

    def probe_media_tracks(self, source_path: str):
        _ = source_path
        return {"audio": [], "subtitles": []}


# --- Cycle 1: resume create contract ---


def test_create_session_rejects_resume_when_duration_unknown(tmp_path: Path):
    """Resume with probe duration 0 and no cached duration must reject."""
    svc = PlaybackService(
        media_library=_FakeLibrary(tmp_path),
        transcoder=_ZeroProbeFakeTranscoder(),
        token_secret="test-secret",
        default_ttl_seconds=120,
    )
    with pytest.raises(ValidationError, match=r"(?i)resume|duration"):
        svc.create_session(
            CreatePlaybackSessionCommand(
                anime_id=1,
                file_id="ep-1",
                client_host="127.0.0.1",
                ttl_seconds=120,
                start_time_seconds=708.0,
            )
        )


def test_create_session_uses_list_duration_fallback_and_waits_for_playhead(tmp_path: Path):
    """Cached duration from list_episode_files must drive resume when re-probe is 0."""
    transcoder = _ProbeSequenceFakeTranscoder([1400.0, 0.0])
    svc = PlaybackService(
        media_library=_FakeLibrary(tmp_path),
        transcoder=transcoder,
        token_secret="test-secret",
        default_ttl_seconds=120,
        segment_seconds=4,
    )
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
            start_time_seconds=708.0,
        )
    )
    assert transcoder.calls[0]["start_segment_index"] == 175
    playhead = Path(session.output_dir) / "segment_00177.ts"
    assert playhead.is_file()
    assert session.playback_start_seconds == pytest.approx(708.0)


def test_create_session_postcondition_playhead_segment_exists(tmp_path: Path):
    """After resume create at 708s, playhead segment must exist on disk."""
    svc, _ = _seekable_service(tmp_path, duration=1400.0, segment_seconds=4)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
            start_time_seconds=708.0,
        )
    )
    playhead = Path(session.output_dir) / "segment_00177.ts"
    assert playhead.is_file(), "segment_00177.ts must exist when /play returns for 708s resume"


def test_create_session_rejects_unreadable_incomplete_file(tmp_path: Path):
    svc = PlaybackService(
        media_library=_FakeLibrary(tmp_path),
        transcoder=_UnreadableFakeTranscoder(),
        token_secret="test-secret",
        default_ttl_seconds=120,
    )
    with pytest.raises(ValidationError) as excinfo:
        svc.create_session(
            CreatePlaybackSessionCommand(
                anime_id=1,
                file_id="ep-1",
                client_host="127.0.0.1",
                ttl_seconds=120,
            )
        )
    assert "can't be played yet" in str(excinfo.value)


# --- Legacy compatibility (adapter without seek-on-demand support) ---


def test_media_session_create_and_resolve_manifest(tmp_path: Path):
    svc = _legacy_service(tmp_path)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
        )
    )
    got, manifest = svc.resolve_media_path(
        GetPlaybackSessionQuery(
            session_id=session.session_id,
            token=session.token,
            segment_name=None,
        )
    )
    assert got.session_id == session.session_id
    assert manifest.endswith("index.m3u8")


def test_media_session_segment_rejects_manifest_without_token(tmp_path: Path):
    svc = _legacy_service(tmp_path)
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
                token="",
                segment_name=None,
            )
        )


def test_stop_session_preserves_segment_files(tmp_path: Path):
    svc = _legacy_service(tmp_path)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
        )
    )
    segment = Path(session.output_dir) / "segment_00000.ts"
    segment.write_bytes(b"ts")
    svc.stop_session(StopPlaybackSessionCommand(session_id=session.session_id))
    assert segment.is_file()


def test_media_session_heartbeat_and_stop(tmp_path: Path):
    svc = _legacy_service(tmp_path)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
        )
    )
    beat = svc.heartbeat(HeartbeatPlaybackSessionCommand(session_id=session.session_id))
    assert beat.session_id == session.session_id
    svc.stop_session(StopPlaybackSessionCommand(session_id=session.session_id))
    with pytest.raises(NotFoundError):
        svc.resolve_media_path(
            GetPlaybackSessionQuery(
                session_id=session.session_id,
                token=session.token,
                segment_name=None,
            )
        )


# --- Seek-on-demand HLS pipeline ---


# --- Cycle 2: playhead resolve after resume create ---


def test_resolve_playhead_segment_served_after_resume_create(tmp_path: Path):
    """After 708s resume create, resolving playhead must not restart transcode."""
    transcoder = _DeadEncoderResumeFake(duration=1400.0)
    svc = PlaybackService(
        media_library=_FakeLibrary(tmp_path),
        transcoder=transcoder,
        token_secret="test-secret",
        default_ttl_seconds=120,
        segment_seconds=4,
    )
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
            start_time_seconds=708.0,
        )
    )
    assert transcoder.calls[0]["start_segment_index"] == 175
    initial_calls = len(transcoder.calls)

    _session, path = svc.resolve_media_path(
        GetPlaybackSessionQuery(
            session_id=session.session_id,
            token=session.token,
            segment_name="segment_00177.ts",
        )
    )
    assert path.endswith("segment_00177.ts")
    assert Path(path).is_file()
    assert len(transcoder.calls) == initial_calls


def test_resolve_playhead_waits_when_encoder_dead(tmp_path: Path):
    """Dead encoder with missing playhead segment must restart at anchor, not playhead."""
    transcoder = _DeadEncoderResumeFake(duration=1400.0)
    svc = PlaybackService(
        media_library=_FakeLibrary(tmp_path),
        transcoder=transcoder,
        token_secret="test-secret",
        default_ttl_seconds=120,
        segment_seconds=4,
    )
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
            start_time_seconds=708.0,
        )
    )
    playhead = Path(session.output_dir) / "segment_00177.ts"
    assert playhead.is_file()
    initial_calls = len(transcoder.calls)

    transcoder.kill_encoder()
    playhead.unlink()

    _session, path = svc.resolve_media_path(
        GetPlaybackSessionQuery(
            session_id=session.session_id,
            token=session.token,
            segment_name="segment_00177.ts",
        )
    )
    assert path.endswith("segment_00177.ts")
    assert Path(path).is_file()
    restart_calls = transcoder.calls[initial_calls:]
    assert restart_calls, "encoder restart expected when playhead segment missing"
    assert restart_calls[0]["start_segment_index"] == session.hls_anchor_segment


# --- Cycle 3: stop preserves segment files ---


def test_stop_session_preserves_segment_files(tmp_path: Path):
    """stop_session must stop ffmpeg without deleting segment files on disk."""
    transcoder = _DeadEncoderResumeFake(duration=600.0)
    svc = PlaybackService(
        media_library=_FakeLibrary(tmp_path),
        transcoder=transcoder,
        token_secret="test-secret",
        default_ttl_seconds=120,
        segment_seconds=4,
    )
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
        )
    )
    segment = Path(session.output_dir) / "segment_00000.ts"
    assert segment.is_file()
    assert transcoder.is_hls_session_running(session.session_id)

    svc.stop_session(StopPlaybackSessionCommand(session_id=session.session_id))

    assert segment.is_file(), "segment files must survive stop_session"
    assert not transcoder.is_hls_session_running(session.session_id)


def test_resolve_segment_before_anchor_rejects_without_restart(tmp_path: Path):
    """Prefetch of segment 0 on a mid-file resume must not restart ffmpeg
    at the beginning — that leaves the player stuck buffering."""
    svc, transcoder = _seekable_service(tmp_path, duration=600.0, segment_seconds=4)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
            start_time_seconds=80.0,
        )
    )
    assert transcoder.calls[0]["start_segment_index"] == 18
    assert session.hls_anchor_segment == 18

    with pytest.raises(NotFoundError, match="anchor"):
        svc.resolve_media_path(
            GetPlaybackSessionQuery(
                session_id=session.session_id,
                token=session.token,
                segment_name="segment_00000.ts",
            )
        )
    assert len(transcoder.calls) == 1


def test_create_session_honours_start_time_hint(tmp_path: Path):
    """When the client tells us its saved resume position, we must
    spawn ffmpeg at the matching segment offset rather than wasting
    cycles encoding from segment 0 and then seek-on-demand-restarting
    a second later."""
    svc, transcoder = _seekable_service(tmp_path, duration=600.0, segment_seconds=4)
    svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
            # 80s resume → playhead segment 20, anchor 18 (PREFETCH_MARGIN=2).
            start_time_seconds=80.0,
        )
    )
    assert transcoder.calls
    assert transcoder.calls[0]["start_segment_index"] == 18


def test_resume_segment_index_from_playback_start():
    assert resume_segment_index(708.0, total_segments=900, segment_seconds=4) == 177
    assert anchor_segment(177) == 175


def test_create_session_resume_manifest_no_ext_x_start(tmp_path: Path):
    """Resume keeps the full timeline; seek is client-side via loadStartTime."""
    svc, _ = _seekable_service(tmp_path, duration=600.0, segment_seconds=4)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
            start_time_seconds=80.0,
        )
    )
    manifest_text = Path(session.manifest_path).read_text(encoding="utf-8")
    assert "#EXT-X-MEDIA-SEQUENCE:0" in manifest_text
    assert "#EXT-X-START" not in manifest_text
    assert "segment_00000.ts" in manifest_text
    assert "segment_00018.ts" in manifest_text
    assert "segment_00149.ts" in manifest_text
    assert session.hls_anchor_segment == 18
    assert session.playback_start_seconds == pytest.approx(80.0)


def test_create_session_waits_for_resume_segment(tmp_path: Path):
    """``/play`` must not return until the resume playhead segment exists."""
    svc, transcoder = _incremental_service(
        tmp_path,
        duration=3600.0,
        delay_seconds=0.12,
    )
    t0 = time.monotonic()
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
            start_time_seconds=708.0,
        )
    )
    elapsed = time.monotonic() - t0
    assert session.hls_anchor_segment == 175
    playhead = Path(session.output_dir) / "segment_00177.ts"
    assert playhead.is_file()
    assert elapsed >= 0.2
    assert transcoder.calls


def test_create_session_writes_event_playlist_until_encode_complete(tmp_path: Path):
    """The manifest lists the full timeline for the seek bar but stays
    in EVENT mode (no ``#EXT-X-ENDLIST``) until every segment exists."""
    svc, _ = _seekable_service(tmp_path, duration=130.0, segment_seconds=4)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
        )
    )

    assert session.duration_seconds == pytest.approx(130.0)
    assert session.segment_seconds == 4
    # ceil(130 / 4) == 33 segments
    assert session.total_segments == 33

    manifest_text = Path(session.manifest_path).read_text(encoding="utf-8")
    assert "#EXTM3U" in manifest_text
    assert "#EXT-X-PLAYLIST-TYPE:EVENT" in manifest_text
    assert "#EXT-X-ENDLIST" not in manifest_text
    # First and last segments are both listed by filename.
    assert "segment_00000.ts" in manifest_text
    assert "segment_00032.ts" in manifest_text
    # The final segment carries the leftover duration (130 - 32*4 = 2s)
    # rather than padding to a full 4-second segment.
    assert "#EXTINF:2.000," in manifest_text


def test_resolve_manifest_finishes_vod_when_all_segments_exist(tmp_path: Path):
    svc, _ = _seekable_service(tmp_path, duration=12.0, segment_seconds=4)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
        )
    )
    out = Path(session.output_dir)
    for index in range(session.total_segments):
        (out / f"segment_{index:05d}.ts").write_bytes(b"seg")

    from application.queries import GetPlaybackSessionQuery

    _session, _path = svc.resolve_media_path(
        GetPlaybackSessionQuery(
            session_id=session.session_id,
            token=session.token,
            segment_name=None,
        )
    )
    manifest_text = Path(session.manifest_path).read_text(encoding="utf-8")
    assert "#EXT-X-PLAYLIST-TYPE:VOD" in manifest_text
    assert "#EXT-X-ENDLIST" in manifest_text


def test_resolve_segment_restarts_transcoder_when_user_seeks_ahead(tmp_path: Path):
    """When the client requests a segment that ffmpeg hasn't reached
    yet, the service must relaunch the transcoder with the matching
    ``start_segment_index`` rather than waiting forever."""
    svc, transcoder = _seekable_service(tmp_path, duration=600.0, segment_seconds=4)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
        )
    )

    # The first call is the initial startup from segment 0.
    assert transcoder.calls[0]["start_segment_index"] == 0

    # Ask for a segment that wasn't pre-materialised (the fake only
    # writes segments 0 and 1 for each ensure_hls_session call).
    _session, path = svc.resolve_media_path(
        GetPlaybackSessionQuery(
            session_id=session.session_id,
            token=session.token,
            segment_name="segment_00050.ts",
        )
    )
    assert path.endswith("segment_00050.ts")
    assert Path(path).is_file()
    # The service must have asked the transcoder to restart from 50.
    restart_starts = [
        call["start_segment_index"] for call in transcoder.calls[1:]
    ]
    assert 50 in restart_starts


def test_resolve_segment_uses_existing_file_without_restart(tmp_path: Path):
    """If the segment file is already on disk the service should serve
    it without bothering the transcoder again."""
    svc, transcoder = _seekable_service(tmp_path, duration=600.0, segment_seconds=4)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
        )
    )
    initial_call_count = len(transcoder.calls)

    _session, path = svc.resolve_media_path(
        GetPlaybackSessionQuery(
            session_id=session.session_id,
            token=session.token,
            segment_name="segment_00000.ts",
        )
    )
    assert path.endswith("segment_00000.ts")
    # No additional ensure_hls_session call.
    assert len(transcoder.calls) == initial_call_count


def test_resolve_segment_rejects_request_past_end_of_stream(tmp_path: Path):
    svc, _ = _seekable_service(tmp_path, duration=100.0, segment_seconds=4)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
        )
    )
    # ceil(100 / 4) = 25 → segments 0..24 valid; 25 is past the end.
    with pytest.raises(NotFoundError):
        svc.resolve_media_path(
            GetPlaybackSessionQuery(
                session_id=session.session_id,
                token=session.token,
                segment_name="segment_00025.ts",
            )
        )


def test_resolve_segment_rejects_internal_ffmpeg_playlist(tmp_path: Path):
    """The ``_ffmpeg.m3u8`` sentinel the adapter writes internally
    must never leak out to clients — otherwise scrubbing would
    silently fall back to ffmpeg's partial event playlist."""
    svc, _ = _seekable_service(tmp_path, duration=100.0, segment_seconds=4)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
        )
    )
    with pytest.raises(NotFoundError):
        svc.resolve_media_path(
            GetPlaybackSessionQuery(
                session_id=session.session_id,
                token=session.token,
                segment_name="_ffmpeg.m3u8",
            )
        )


def test_concurrent_segment_requests_collapse_into_one_restart(tmp_path: Path):
    """Two clients (or two HLS pre-fetchers) racing for the same
    not-yet-encoded segment should result in a single ffmpeg restart,
    not one per request."""
    svc, transcoder = _seekable_service(tmp_path, duration=600.0, segment_seconds=4)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
        )
    )
    initial_calls = len(transcoder.calls)

    results: list[str] = []
    errors: list[BaseException] = []

    def _request() -> None:
        try:
            _s, path = svc.resolve_media_path(
                GetPlaybackSessionQuery(
                    session_id=session.session_id,
                    token=session.token,
                    segment_name="segment_00100.ts",
                )
            )
            results.append(path)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_request) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert all(p.endswith("segment_00100.ts") for p in results)
    restart_count = sum(
        1
        for call in transcoder.calls[initial_calls:]
        if call["start_segment_index"] == 100
    )
    assert restart_count == 1


def test_parallel_prefetch_does_not_thrash_sequential_encode(tmp_path: Path):
    """Shaka prefetches segment N+1 and N+2 in parallel on fresh start.

    A short forward wait followed by restart at N+2 used to kill the
    in-progress encode toward N+1, leaving the player stuck buffering."""
    svc, transcoder = _incremental_service(
        tmp_path,
        duration=120.0,
        segment_seconds=4,
        delay_seconds=2.0,
    )
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
        )
    )
    assert (Path(session.output_dir) / "segment_00000.ts").is_file()
    initial_calls = len(transcoder.calls)

    results: list[str] = []
    errors: list[BaseException] = []

    def _request(segment_name: str) -> None:
        try:
            _s, path = svc.resolve_media_path(
                GetPlaybackSessionQuery(
                    session_id=session.session_id,
                    token=session.token,
                    segment_name=segment_name,
                )
            )
            results.append(path)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=_request, args=("segment_00001.ts",)),
        threading.Thread(target=_request, args=("segment_00002.ts",)),
    ]
    started = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=25.0)
        assert not t.is_alive(), "segment resolve hung past timeout"
    elapsed = time.monotonic() - started

    assert not errors, errors
    assert len(results) == 2
    assert all("segment_0000" in p for p in results)
    assert (Path(session.output_dir) / "segment_00001.ts").is_file()
    assert elapsed < 25.0
    assert len(transcoder.calls) == initial_calls, (
        "parallel prefetch must not restart ffmpeg while encoder is catching up"
    )


def test_create_session_resume_headroom_covers_shaka_prefetch(tmp_path: Path):
    """Resume near 1419s must anchor early enough for Shaka prefetch."""
    svc, transcoder = _seekable_service(tmp_path, duration=3600.0, segment_seconds=4)
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
            start_time_seconds=1419.0,
        )
    )
    # 1419s → playhead 354, anchor 352
    assert transcoder.calls[0]["start_segment_index"] == 352
    assert session.hls_anchor_segment == 352


def test_resume_at_1420s_anchor_and_playhead_segment_available(tmp_path: Path):
    """Resume at 1420s on a 1600s episode.

    Regression test for the real-browser 404 bug:
    - anchor segment = 355 - PREFETCH_MARGIN(2) = 353
    - playhead segment = 1420 // 4 = 355
    The service must wait for segment_00355.ts and return the session only
    when that segment exists, so Shaka's player.load(manifest, 1420) can
    immediately fetch the segment it needs.
    """
    svc, transcoder = _incremental_service(
        tmp_path,
        duration=1600.0,
        segment_seconds=4,
        delay_seconds=0.05,
    )
    t0 = time.monotonic()
    session = svc.create_session(
        CreatePlaybackSessionCommand(
            anime_id=1,
            file_id="ep-1",
            client_host="127.0.0.1",
            ttl_seconds=120,
            start_time_seconds=1420.0,
        )
    )
    elapsed = time.monotonic() - t0

    assert session.hls_anchor_segment == 353
    assert session.playback_start_seconds == pytest.approx(1420.0)
    # The server must have waited for the playhead segment before returning
    playhead_seg = Path(session.output_dir) / "segment_00355.ts"
    assert playhead_seg.is_file(), "segment_00355.ts (1420s playhead) must exist when /play returns"
    # Took at least a tiny bit of time (ffmpeg needs to produce segments)
    assert elapsed >= 0.1


def test_resume_segment_index_values():
    """resume_segment_index and anchor_segment for smoke-test positions."""
    assert resume_segment_index(708.0, total_segments=900, segment_seconds=4) == 177
    assert anchor_segment(177) == 175
    assert resume_segment_index(1420.0, total_segments=900, segment_seconds=4) == 355
    assert anchor_segment(355) == 353
