from __future__ import annotations

import threading
from pathlib import Path

import pytest

from application.commands import (
    CreatePlaybackSessionCommand,
    HeartbeatPlaybackSessionCommand,
    StopPlaybackSessionCommand,
)
from application.queries import GetPlaybackSessionQuery
from application.services.media_streaming_service import MediaStreamingService
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


class _LegacyFakeTranscoder:
    """Mimics a third-party adapter that hasn't been updated for
    seek-on-demand: its ``ensure_hls_session`` does *not* accept the
    new ``start_segment_index`` / ``segment_seconds`` kwargs. The
    service must transparently fall back to the legacy call shape so
    older adapters keep working."""

    def ensure_hls_session(
        self,
        *,
        session_id: str,
        source_path: str,
        output_dir: str,
        audio_track: int | None = None,
        subtitle_track: int | None = None,
    ):
        _ = (session_id, source_path, audio_track, subtitle_track)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        manifest = out / "index.m3u8"
        segment = out / "segment_00001.ts"
        manifest.write_text("#EXTM3U\n#EXTINF:3,\nsegment_00001.ts\n", encoding="utf-8")
        segment.write_bytes(b"seg")
        return {"manifest_path": str(manifest)}

    def stop_hls_session(self, session_id: str) -> None:
        _ = session_id

    def probe_media_tracks(self, source_path: str):
        _ = source_path
        return {"audio": [{"id": 0, "label": "UND"}], "subtitles": []}


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
        # Materialise segment N and N+1 so the service finds the
        # requested segment on disk after the (potential) restart.
        for offset in (0, 1):
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


def _legacy_service(tmp_path: Path) -> MediaStreamingService:
    return MediaStreamingService(
        media_library=_FakeLibrary(tmp_path),
        transcoder=_LegacyFakeTranscoder(),
        token_secret="test-secret",
        default_ttl_seconds=120,
    )


def _seekable_service(
    tmp_path: Path,
    duration: float,
    *,
    segment_seconds: int = 4,
) -> tuple[MediaStreamingService, _SeekableFakeTranscoder]:
    transcoder = _SeekableFakeTranscoder(duration=duration)
    svc = MediaStreamingService(
        media_library=_FakeLibrary(tmp_path),
        transcoder=transcoder,
        token_secret="test-secret",
        default_ttl_seconds=120,
        segment_seconds=segment_seconds,
    )
    return svc, transcoder


class _UnreadableFakeTranscoder(_SeekableFakeTranscoder):
    """Probe behaviour of an incomplete torrent file: no duration and
    no tracks at all (ffprobe cannot read the container header)."""

    def __init__(self) -> None:
        super().__init__(duration=0.0)

    def probe_media_tracks(self, source_path: str):
        _ = source_path
        return {"audio": [], "subtitles": []}


def test_create_session_rejects_unreadable_incomplete_file(tmp_path: Path):
    svc = MediaStreamingService(
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
    assert transcoder.calls[0]["start_segment_index"] == 19
    assert session.hls_anchor_segment == 19

    with pytest.raises(NotFoundError, match="anchor"):
        svc.resolve_media_path(
            GetPlaybackSessionQuery(
                session_id=session.session_id,
                token=session.token,
                segment_name="segment_00000.ts",
            )
        )
    # No seek-on-demand restart was triggered for the bogus prefetch.
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
            # The user was 80 seconds in when they left; with 4s
            # segments and the service's 4s scrub-back headroom this
            # should anchor encoding at segment 19 (76 // 4).
            start_time_seconds=80.0,
        )
    )
    assert transcoder.calls
    assert transcoder.calls[0]["start_segment_index"] == 19


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
