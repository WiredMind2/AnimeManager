"""Edge case tests for ``clients/http/app.py`` error mapping.

Confirms that domain errors raised by the SDK collapse to the expected
HTTP status codes and that pass-through endpoints accept the right
parameter shapes.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from domain.errors import (
    InfrastructureError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)

http_app_module = importlib.import_module("clients.http.app")


class _SDKBase:
    """Minimal fake SDK; tests override only the methods they need."""

    def get_anime(self, anime_id: int):
        return {"id": anime_id, "title": "Test"}

    def get_anime_list(self, **kwargs):
        return {"items": [], "has_next": False}

    def search_anime(self, query: str, limit: int = 50):
        return []

    def start_download(self, anime_id: int, url=None, hash_value=None, user_id=None):
        return True

    def get_download_progress(self, anime_id: int):
        return {"anime_id": anime_id, "progress": 0}

    def cancel_download(self, anime_id: int):
        return True

    def get_active_downloads(self):
        return []

    def search_torrents(self, terms, profile="interactive", limit=200):
        return []

    def set_tag(self, anime_id, tag, user_id):
        pass

    def set_like(self, anime_id, user_id, liked=True):
        pass

    def mark_seen(self, anime_id, file_name, user_id):
        pass

    def get_user_state(self, anime_id, user_id):
        return {}

    def get_search_terms(self, anime_id):
        return []

    def add_search_term(self, anime_id, term):
        return True

    def remove_search_term(self, anime_id, term):
        return True

    def get_settings(self):
        return {}

    def update_settings(self, updates):
        return updates


# ---------------------------------------------------------------------------
# _map_error
# ---------------------------------------------------------------------------


class TestMapError:
    def test_validation_error_maps_to_400(self):
        exc = http_app_module._map_error(ValidationError("bad"))
        assert exc.status_code == 400
        assert exc.detail == "bad"

    def test_not_found_maps_to_404(self):
        exc = http_app_module._map_error(NotFoundError("missing"))
        assert exc.status_code == 404
        assert exc.detail == "missing"

    def test_other_exceptions_map_to_500(self):
        exc = http_app_module._map_error(RuntimeError("boom"))
        assert exc.status_code == 500
        assert exc.detail == "boom"

    def test_infrastructure_error_maps_to_500(self):
        exc = http_app_module._map_error(InfrastructureError("db down"))
        assert exc.status_code == 500

    def test_unauthorized_falls_through_to_500(self):
        # The current mapping does not have a dedicated branch for
        # UnauthorizedError; document the behavior.
        exc = http_app_module._map_error(UnauthorizedError("nope"))
        assert exc.status_code == 500


# ---------------------------------------------------------------------------
# End-to-end error responses
# ---------------------------------------------------------------------------


@pytest.fixture
def client_factory(monkeypatch):
    def _build(sdk):
        monkeypatch.setattr(http_app_module, "get_sdk", lambda: sdk)
        return TestClient(http_app_module.app)

    return _build


class TestErrorEndpoints:
    def test_anime_not_found_returns_404(self, client_factory):
        class SDK(_SDKBase):
            def get_anime(self, anime_id):
                raise NotFoundError(f"missing {anime_id}")

        client = client_factory(SDK())
        resp = client.get("/anime/9999")
        assert resp.status_code == 404
        assert "missing" in resp.json()["detail"]

    def test_validation_error_on_search_returns_400(self, client_factory):
        class SDK(_SDKBase):
            def search_anime(self, query, limit=50):
                raise ValidationError("too short")

        client = client_factory(SDK())
        resp = client.get("/search", params={"query": "a"})
        assert resp.status_code == 400

    def test_unexpected_error_returns_500(self, client_factory):
        class SDK(_SDKBase):
            def get_anime(self, anime_id):
                raise RuntimeError("boom")

        client = client_factory(SDK())
        resp = client.get("/anime/1")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Happy-path edges (query parameter coercion, defaults)
# ---------------------------------------------------------------------------


class TestEndpointParameterEdges:
    def test_root(self, client_factory):
        client = client_factory(_SDKBase())
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_anime_id_non_numeric_returns_422(self, client_factory):
        client = client_factory(_SDKBase())
        resp = client.get("/anime/not-an-int")
        assert resp.status_code == 422

    def test_animelist_defaults(self, client_factory):
        captured = {}

        class SDK(_SDKBase):
            def get_anime_list(self, **kwargs):
                captured.update(kwargs)
                return {"items": [], "has_next": False}

        client = client_factory(SDK())
        client.get("/animelist")
        assert captured["filter_name"] == "DEFAULT"
        assert captured["user_id"] is None
        assert captured["list_start"] == 0
        assert captured["list_stop"] == 50
        assert captured["hide_rated"] is None

    def test_download_post_with_just_url(self, client_factory):
        client = client_factory(_SDKBase())
        resp = client.post("/download/1", params={"url": "magnet:?xt=urn:btih:abc"})
        assert resp.status_code == 200
        assert resp.json() == {"started": True}

    def test_search_terms_default_limit_for_search(self, client_factory):
        captured = {}

        class SDK(_SDKBase):
            def search_anime(self, query, limit=50):
                captured["query"] = query
                captured["limit"] = limit
                return []

        client = client_factory(SDK())
        client.get("/search", params={"query": "naruto"})
        assert captured["query"] == "naruto"
        assert captured["limit"] == 50

    def test_torrents_search_requires_term(self, client_factory):
        client = client_factory(_SDKBase())
        resp = client.get("/torrents/search")
        # FastAPI returns 422 when required query param missing
        assert resp.status_code == 422

    def test_torrents_search_passes_term(self, client_factory):
        captured = {}

        class SDK(_SDKBase):
            def search_torrents(self, terms, profile="interactive", limit=200):
                captured["terms"] = list(terms)
                return []

        client = client_factory(SDK())
        resp = client.get("/torrents/search", params=[("term", "naruto")])
        assert resp.status_code == 200
        assert "naruto" in captured["terms"]

    def test_tag_post(self, client_factory):
        captured = {}

        class SDK(_SDKBase):
            def set_tag(self, anime_id, tag, user_id):
                captured["args"] = (anime_id, tag, user_id)

        client = client_factory(SDK())
        resp = client.post("/tag/5", params={"tag": "LIKED", "user_id": 7})
        assert resp.status_code == 200
        assert captured["args"] == (5, "LIKED", 7)

    def test_like_default_true(self, client_factory):
        captured = {}

        class SDK(_SDKBase):
            def set_like(self, anime_id, user_id, liked=True):
                captured["args"] = (anime_id, user_id, liked)

        client = client_factory(SDK())
        client.post("/like/5", params={"user_id": 7})
        assert captured["args"] == (5, 7, True)

    def test_like_explicit_false(self, client_factory):
        captured = {}

        class SDK(_SDKBase):
            def set_like(self, anime_id, user_id, liked=True):
                captured["args"] = (anime_id, user_id, liked)

        client = client_factory(SDK())
        client.post("/like/5", params={"user_id": 7, "liked": False})
        assert captured["args"] == (5, 7, False)

    def test_settings_patch_with_empty_dict(self, client_factory):
        captured = {}

        class SDK(_SDKBase):
            def update_settings(self, updates):
                captured["updates"] = updates
                return updates

        client = client_factory(SDK())
        resp = client.patch("/settings", json={})
        assert resp.status_code == 200
        assert captured["updates"] == {}
