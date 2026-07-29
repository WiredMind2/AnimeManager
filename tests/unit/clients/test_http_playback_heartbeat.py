"""HTTP integration tests for POST /ui/stream/{session_id}/heartbeat."""

from __future__ import annotations

import importlib
import time
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

http_app = importlib.import_module("clients.http.app")


class _HeartbeatFakeSDK:
    """Minimal SDK fake for play + heartbeat routes."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self._playback_sessions: dict[str, dict] = {}
        self._play_root = Path(tempfile.mkdtemp(prefix="am-heartbeat-"))
        (self._play_root / "index.m3u8").write_text(
            "#EXTM3U\n#EXTINF:3,\nsegment_00001.ts\n",
            encoding="utf-8",
        )

    def _record(self, name: str, *args, **kwargs) -> None:
        self.calls.append((name, args, kwargs))

    def list_episode_files(self, anime_id: int, user_id: int | None = None):
        self._record("list_episode_files", anime_id, user_id)
        return [{"file_id": "ep-001", "title": "Episode 1", "path": "/anime/ep.mkv"}]

    def create_playback_session(self, anime_id: int, file_id: str, **kwargs):
        self._record("create_playback_session", anime_id, file_id, kwargs)
        sid = "sess-hb-1"
        token = "hb.token"
        self._playback_sessions[sid] = {
            "session_id": sid,
            "anime_id": anime_id,
            "file_id": file_id,
            "token": token,
            "expires_at": time.time() + 600,
        }
        return dict(self._playback_sessions[sid])

    def heartbeat_playback_session(self, session_id: str, *, position_seconds: float | None = None):
        self._record("heartbeat_playback_session", session_id, position_seconds=position_seconds)
        session = self._playback_sessions.get(session_id)
        if not session:
            from domain.errors import NotFoundError

            raise NotFoundError("missing session")
        session["expires_at"] = time.time() + 600
        session["token"] = "hb.token.refreshed"
        return dict(session)

    def resolve_playback_media_path(self, *, session_id: str, token: str, segment_name=None):
        self._record("resolve_playback_media_path", session_id, token, segment_name)
        session = self._playback_sessions.get(session_id)
        if not session:
            from domain.errors import NotFoundError

            raise NotFoundError("missing session")
        if not token or token != session["token"]:
            from domain.errors import UnauthorizedError

            raise UnauthorizedError("bad token")
        return dict(session), str(self._play_root / "index.m3u8")


@pytest.fixture
def client(monkeypatch):
    fake = _HeartbeatFakeSDK()
    monkeypatch.setattr(http_app, "get_sdk", lambda: fake)
    with TestClient(http_app.app, follow_redirects=False) as test_client:
        test_client.fake = fake  # type: ignore[attr-defined]
        yield test_client


def _create_session(client: TestClient) -> dict:
    resp = client.post("/ui/anime/1/play", data={"file_id": "ep-001"})
    assert resp.status_code == 200
    return resp.json()


def test_heartbeat_forwards_position_seconds(client):
    created = _create_session(client)
    session_id = created["session_id"]
    token = created["token"]

    resp = client.post(
        f"/ui/stream/{session_id}/heartbeat",
        params={"token": token},
        json={"position_seconds": 412.5},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == session_id
    assert "token" in body
    assert "expires_at" in body
    assert resp.headers["cache-control"] == "no-store"

    fake: _HeartbeatFakeSDK = client.fake  # type: ignore[attr-defined]
    assert fake.calls[-1] == (
        "heartbeat_playback_session",
        (session_id,),
        {"position_seconds": 412.5},
    )


def test_heartbeat_without_body_omits_position(client):
    created = _create_session(client)
    session_id = created["session_id"]
    token = created["token"]

    resp = client.post(
        f"/ui/stream/{session_id}/heartbeat",
        params={"token": token},
    )

    assert resp.status_code == 200
    fake: _HeartbeatFakeSDK = client.fake  # type: ignore[attr-defined]
    assert fake.calls[-1] == (
        "heartbeat_playback_session",
        (session_id,),
        {"position_seconds": None},
    )


def test_heartbeat_rejects_non_numeric_position(client):
    created = _create_session(client)
    session_id = created["session_id"]
    token = created["token"]

    resp = client.post(
        f"/ui/stream/{session_id}/heartbeat",
        params={"token": token},
        json={"position_seconds": "not-a-number"},
    )

    assert resp.status_code == 400
    assert "position_seconds" in resp.json()["detail"]
