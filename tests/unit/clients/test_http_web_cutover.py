"""Cutover redirect tests for legacy `/ui/*` pages."""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

http_app_module = importlib.import_module("clients.http.app")


class _SDK:
    def get_anime_list(self, **kwargs):
        return {"items": [], "has_next": False}


def test_ui_routes_redirect_to_next_when_cutover_enabled(monkeypatch):
    monkeypatch.setattr(http_app_module, "get_sdk", lambda: _SDK())
    monkeypatch.setenv("ANIMEMANAGER_NEXT_UI_URL", "http://127.0.0.1:3000")
    client = TestClient(http_app_module.app)

    resp = client.get("/ui/library", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "http://127.0.0.1:3000/library"


def test_ui_root_redirects_to_next_root_when_cutover_enabled(monkeypatch):
    monkeypatch.setattr(http_app_module, "get_sdk", lambda: _SDK())
    monkeypatch.setenv("ANIMEMANAGER_NEXT_UI_URL", "http://127.0.0.1:3000")
    client = TestClient(http_app_module.app)

    resp = client.get("/ui", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "http://127.0.0.1:3000/"
