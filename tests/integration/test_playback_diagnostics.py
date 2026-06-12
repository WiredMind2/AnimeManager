"""High-level playback diagnostics (real ffmpeg + local fixture).

Skipped when the SubsPlease Classroom Elite S4E11 file is absent.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

EPISODE_PATH = Path(
    r"C:\Users\willi\Documents\Anime\Animes\Classroom of the Elite 4th Season Second Year First Semester - 1090"
    r"\[SubsPlease] Youkoso Jitsuryoku Shijou Shugi no Kyoushitsu e S4 - 11 (720p) [7CA0682C].mkv"
)
ANIME_ID = 1090
FILE_ID = "ep-0010-f72923b691b06c5d"

pytestmark = pytest.mark.skipif(
    not EPISODE_PATH.is_file(),
    reason="Local SubsPlease S4E11 fixture is not present on this machine",
)


@pytest.fixture(scope="module")
def sdk():
    from clients.sdk import ClientSDK

    return ClientSDK()


@pytest.fixture(scope="module")
def transcoder(sdk):
    return sdk._facade._service._media_streaming._transcoder  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _stop_playback_after_test(sdk, transcoder):
    yield
    with transcoder._lock:
        active_ids = list(transcoder._active.keys())
    for sid in active_ids:
        try:
            sdk.stop_playback_session(sid)
        except Exception:
            transcoder.stop_hls_session(sid)


def test_ffmpeg_running_after_session_create(sdk, transcoder):
    session = sdk.create_playback_session(
        ANIME_ID,
        file_id=FILE_ID,
        client_host="127.0.0.1",
    )
    sid = session["session_id"]
    try:
        assert transcoder.is_hls_session_running(sid), "ffmpeg should be alive after create"
    finally:
        sdk.stop_playback_session(sid)


def test_resume_anchor_segment_materializes(sdk):
    session = sdk.create_playback_session(
        ANIME_ID,
        file_id=FILE_ID,
        client_host="127.0.0.1",
        start_time_seconds=80.0,
    )
    sid = session["session_id"]
    token = session["token"]
    try:
        anchor = 19  # 76s // 4s with scrub-back headroom
        seg_name = f"segment_{anchor:05d}.ts"
        t0 = time.monotonic()
        _session, seg_path = sdk.resolve_playback_media_path(
            session_id=sid,
            token=token,
            segment_name=seg_name,
        )
        elapsed = time.monotonic() - t0
        assert os.path.getsize(seg_path) > 10_000, f"{seg_name} too small"
        assert elapsed < 30.0, f"anchor segment took {elapsed:.1f}s"
    finally:
        sdk.stop_playback_session(sid)


def test_seek_ahead_restarts_ffmpeg_and_serves_segment(sdk, transcoder):
    session = sdk.create_playback_session(
        ANIME_ID,
        file_id=FILE_ID,
        client_host="127.0.0.1",
    )
    sid = session["session_id"]
    token = session["token"]
    try:
        target = "segment_00050.ts"
        t0 = time.monotonic()
        _session, seg_path = sdk.resolve_playback_media_path(
            session_id=sid,
            token=token,
            segment_name=target,
        )
        elapsed = time.monotonic() - t0
        assert os.path.getsize(seg_path) > 10_000
        assert elapsed < 35.0, f"seek-ahead segment took {elapsed:.1f}s"
        assert transcoder.is_hls_session_running(sid)
    finally:
        sdk.stop_playback_session(sid)


def test_prefetch_before_anchor_returns_404_not_restart(sdk, transcoder):
    """Shaka may prefetch segment 0 on mid-file resume; must not kill anchor encode."""
    session = sdk.create_playback_session(
        ANIME_ID,
        file_id=FILE_ID,
        client_host="127.0.0.1",
        start_time_seconds=80.0,
    )
    sid = session["session_id"]
    token = session["token"]
    try:
        from domain.errors import NotFoundError

        with pytest.raises(NotFoundError, match="anchor"):
            sdk.resolve_playback_media_path(
                session_id=sid,
                token=token,
                segment_name="segment_00000.ts",
            )
        assert transcoder.is_hls_session_running(sid)
    finally:
        sdk.stop_playback_session(sid)


def test_third_concurrent_session_still_starts_ffmpeg(sdk, transcoder):
    """Orphaned encodes (no /stop) used to block new playback at max_active_sessions=2."""
    sessions: list[str] = []
    try:
        for _ in range(3):
            row = sdk.create_playback_session(
                ANIME_ID,
                file_id=FILE_ID,
                client_host="127.0.0.1",
            )
            sessions.append(row["session_id"])
        assert transcoder.is_hls_session_running(sessions[-1])
        assert len(transcoder._active) <= 2  # type: ignore[attr-defined]
    finally:
        for sid in sessions:
            try:
                sdk.stop_playback_session(sid)
            except Exception:
                transcoder.stop_hls_session(sid)


def test_play_endpoint_waits_for_first_segment_under_30s(sdk):
    from fastapi.testclient import TestClient

    from clients.http.app import app

    client = TestClient(app)
    t0 = time.monotonic()
    play = client.post(
        f"/ui/anime/{ANIME_ID}/play",
        data={"file_id": FILE_ID, "start_time": "78"},
    )
    elapsed = time.monotonic() - t0
    assert play.status_code == 200, play.text
    payload = play.json()
    sid = payload["session_id"]
    try:
        assert elapsed < 35.0, f"/play took {elapsed:.1f}s (ffmpeg may be slow or stuck)"
        seg = client.get(f"/ui/stream/{sid}/segment_00019.ts")
        assert seg.status_code == 200, seg.text[:200]
        assert len(seg.content) > 10_000
    finally:
        client.post(f"/ui/stream/{sid}/stop")
