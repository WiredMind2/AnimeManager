"""Integration check for the SubsPlease Classroom Elite S4E11 fixture."""

from __future__ import annotations

import os
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


@pytest.fixture(autouse=True)
def _stop_playback_after_test(sdk):
    yield
    transcoder = sdk._facade._service._media_streaming._transcoder  # type: ignore[attr-defined]
    with transcoder._lock:
        active_ids = list(transcoder._active.keys())
    for sid in active_ids:
        try:
            sdk.stop_playback_session(sid)
        except Exception:
            transcoder.stop_hls_session(sid)


def test_subsplease_ep11_playback_produces_first_segment(sdk):
    session = sdk.create_playback_session(
        ANIME_ID,
        file_id=FILE_ID,
        client_host="127.0.0.1",
    )
    out = Path(session["output_dir"])
    assert (out / "index.m3u8").is_file()

    _session, seg_path = sdk.resolve_playback_media_path(
        session_id=session["session_id"],
        token=session["token"],
        segment_name="segment_00000.ts",
    )
    assert os.path.getsize(seg_path) > 10_000
    assert _session["session_id"] == session["session_id"]
    sdk.stop_playback_session(session["session_id"])


def test_subsplease_ep11_http_play_and_segment(sdk):
    from fastapi.testclient import TestClient

    from clients.http.app import app

    client = TestClient(app)
    play = client.post(f"/ui/anime/{ANIME_ID}/play", data={"file_id": FILE_ID})
    assert play.status_code == 200, play.text
    payload = play.json()
    manifest = client.get(payload["manifest_url"])
    assert manifest.status_code == 200
    manifest_text = manifest.text
    assert "#EXT-X-PLAYLIST-TYPE:VOD" in manifest_text
    assert "#EXT-X-ENDLIST" in manifest_text
    seg = client.get(f"/ui/stream/{payload['session_id']}/segment_00000.ts")
    assert seg.status_code == 200
    assert len(seg.content) > 10_000
    client.post(f"/ui/stream/{payload['session_id']}/stop")
