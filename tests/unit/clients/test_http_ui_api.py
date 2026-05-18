"""Tests for the Next.js-oriented ``/ui/api/*`` contract."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

http_app_module = importlib.import_module("clients.http.app")


class _SDK:
    def search_anime(self, query: str, limit: int = 50):
        return [{"id": 10, "title": query, "limit": limit}]

    def get_anime_list(self, **kwargs):
        return {"items": [{"id": 1, "title": "A"}], "has_next": False}

    def get_anime(self, anime_id: int):
        return {"id": anime_id, "title": "Test Anime"}

    def get_user_state(self, anime_id: int, user_id: int):
        return {"anime_id": anime_id, "user_id": user_id, "liked": False}

    def get_search_terms(self, anime_id: int):
        return ["term1", "term2"]

    def list_episode_files(self, anime_id: int, user_id: int | None = None):
        return [{"id": "f1", "name": "episode.mkv"}]

    def get_relations(self, anime_id: int, relation_type: str = "anime"):
        return [{"id": anime_id + 1, "relation_type": relation_type}]

    def list_anime_characters(self, anime_id: int):
        return [{"id": 123, "name": "Hero"}]

    def get_last_torrent_search_query(self, anime_id: int):
        return "old query"

    def search_torrents(self, terms, profile="interactive", limit=200):
        return [{"name": "torrent", "terms": terms, "profile": profile, "limit": limit}]

    def set_last_torrent_search_query(self, anime_id: int, query: str):
        self.last_query = (anime_id, query)

    def get_torrents_overview(self):
        return {"active": [{"name": "one"}], "seeding": [], "completed": [], "error": [], "other": []}

    def set_like(self, anime_id, user_id, liked=True):
        return None

    def set_tag(self, anime_id, tag, user_id):
        return None

    def start_download(self, anime_id, url=None, hash_value=None, user_id=None):
        return True

    def cancel_download(self, anime_id: int):
        return True


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(http_app_module, "get_sdk", lambda: _SDK())
    return TestClient(http_app_module.app)


def test_ui_api_meta(client):
    resp = client.get("/ui/api/meta")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ui_api_version"]
    assert payload["streams"]["library_ws"] == "/ui/library/ws"


def test_ui_api_library_list_mode(client):
    resp = client.get("/ui/api/library", params={"filter": "DEFAULT"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["mode"] == "list"
    assert isinstance(payload["items"], list)


def test_ui_api_library_search_mode(client):
    resp = client.get("/ui/api/library", params={"q": "naruto"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["mode"] == "search"
    assert payload["query"] == "naruto"


def test_ui_api_anime_bundle(client):
    resp = client.get("/ui/api/anime/7/bundle")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["anime"]["id"] == 7
    assert "episodes" in payload
    assert "characters" in payload


def test_ui_api_torrent_search(client):
    resp = client.get("/ui/api/torrents/search", params={"anime_id": 9, "term": "abc"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["query"] == "abc"
    assert payload["items"][0]["name"] == "torrent"


def test_ui_api_mutations(client):
    like_resp = client.post("/ui/api/anime/1/like", json={"user_id": 1, "liked": True})
    tag_resp = client.post("/ui/api/anime/1/tag", json={"user_id": 1, "tag": "WATCHING"})
    dl_resp = client.post("/ui/api/anime/1/download", json={"user_id": 1, "url": "magnet:?x"})
    cancel_resp = client.post("/ui/api/anime/1/cancel")
    assert like_resp.status_code == 200
    assert tag_resp.status_code == 200
    assert dl_resp.json() == {"started": True}
    assert cancel_resp.json() == {"cancelled": True}
