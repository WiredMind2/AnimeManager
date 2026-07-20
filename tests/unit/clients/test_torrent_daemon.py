"""Tests for the LibTorrent daemon FastAPI app."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def test_health_reports_ready_manager():
    manager = MagicMock()
    manager._running = True
    manager.handles = {"abc": object()}

    with patch("clients.torrent_daemon.app._MANAGER", manager):
        from clients.torrent_daemon.app import app

        client = TestClient(app)
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["torrent_count"] == 1
