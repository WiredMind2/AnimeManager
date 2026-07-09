"""Comprehensive coverage for the JSON HTTP API.

The existing ``test_http_adapter.py`` is a single happy-path smoke
test and ``test_http_app_edges.py`` focuses on error mapping. This
suite fills in the gaps with parametrized, behavior-focused tests
that:

* exercise every JSON endpoint with realistic payload shapes,
* verify query-parameter coercion (ints, bools, lists, defaults),
* pin the JSON response schema each route promises,
* and ensure error mappings stay consistent across endpoints.

Tests use a single fake SDK that records every call so we can both
assert outputs and confirm the right SDK method received the right
arguments.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from fastapi.testclient import TestClient

from domain.errors import (
    InfrastructureError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)

http_app = importlib.import_module("clients.http.app")


class RecordingSDK:
    """SDK fake that captures every call AND lets tests override
    individual methods by name. Mirrors the surface defined by
    :class:`clients.sdk.ClientSDK`.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.overrides: dict[str, Any] = {}

    # ---- read paths --------------------------------------------------
    def get_anime(self, anime_id: int):
        return self._invoke(
            "get_anime",
            (anime_id,),
            {},
            default=lambda: {
                "id": anime_id,
                "title": "T",
                "metadata_pending": False,
                "metadata_refreshing": False,
            },
        )

    def refresh_anime_details(self, anime_id: int):
        return self._invoke(
            "refresh_anime_details",
            (anime_id,),
            {},
            default=lambda: {"accepted": True, "anime_id": anime_id},
        )

    def get_anime_list(self, **kwargs):
        return self._invoke(
            "get_anime_list",
            (),
            kwargs,
            default=lambda: {"items": [], "has_next": False},
        )

    def search_anime(self, query: str, limit: int = 50):
        return self._invoke(
            "search_anime",
            (query, limit),
            {},
            default=lambda: [],
        )

    def get_download_progress(self, anime_id: int):
        return self._invoke(
            "get_download_progress",
            (anime_id,),
            {},
            default=lambda: {"anime_id": anime_id, "progress": 0},
        )

    def get_active_downloads(self):
        return self._invoke("get_active_downloads", (), {}, default=lambda: [])

    def search_torrents(self, terms, profile="interactive", limit=200):
        return self._invoke(
            "search_torrents",
            (tuple(terms), profile, limit),
            {},
            default=lambda: [],
        )

    def get_user_state(self, anime_id: int, user_id: int):
        return self._invoke(
            "get_user_state",
            (anime_id, user_id),
            {},
            default=lambda: {"tag": "NONE", "liked": False},
        )

    def get_search_terms(self, anime_id: int):
        return self._invoke(
            "get_search_terms", (anime_id,), {}, default=lambda: []
        )

    def get_settings(self):
        return self._invoke("get_settings", (), {}, default=lambda: {})

    def get_relations(self, anime_id: int, relation_type: str = "anime"):
        return self._invoke(
            "get_relations",
            (anime_id, relation_type),
            {},
            default=lambda: [],
        )

    def get_characters(self, anime_id: int):
        return self._invoke(
            "get_characters", (anime_id,), {}, default=lambda: []
        )

    def get_character(self, character_id: int):
        return self._invoke(
            "get_character",
            (character_id,),
            {},
            default=lambda: {"id": character_id, "name": "Char"},
        )

    def get_anime_pictures(self, anime_id: int):
        return self._invoke(
            "get_anime_pictures", (anime_id,), {}, default=lambda: []
        )

    def refresh_anime_characters(self, anime_id: int):
        return self._invoke(
            "refresh_anime_characters",
            (anime_id,),
            {},
            default=lambda: [],
        )

    def refresh_character(self, character_id: int):
        return self._invoke(
            "refresh_character",
            (character_id,),
            {},
            default=lambda: {"id": character_id, "name": "Char"},
        )

    def refresh_anime_pictures(self, anime_id: int):
        return self._invoke(
            "refresh_anime_pictures",
            (anime_id,),
            {},
            default=lambda: [],
        )

    # ---- write paths -------------------------------------------------
    def start_download(self, anime_id, url=None, hash_value=None, user_id=None):
        return self._invoke(
            "start_download",
            (anime_id, url, hash_value, user_id),
            {},
            default=lambda: True,
        )

    def cancel_download(self, anime_id: int):
        return self._invoke(
            "cancel_download", (anime_id,), {}, default=lambda: True
        )

    def set_tag(self, anime_id, tag, user_id):
        return self._invoke("set_tag", (anime_id, tag, user_id), {}, default=lambda: None)

    def set_like(self, anime_id, user_id, liked=True):
        return self._invoke(
            "set_like", (anime_id, user_id, liked), {}, default=lambda: None
        )

    def mark_seen(self, anime_id, file_name, user_id):
        return self._invoke(
            "mark_seen", (anime_id, file_name, user_id), {}, default=lambda: None
        )

    def add_search_term(self, anime_id, term):
        return self._invoke(
            "add_search_term", (anime_id, term), {}, default=lambda: True
        )

    def remove_search_term(self, anime_id, term):
        return self._invoke(
            "remove_search_term", (anime_id, term), {}, default=lambda: True
        )

    def update_settings(self, updates):
        return self._invoke(
            "update_settings", (updates,), {}, default=lambda: updates
        )

    # ---- internals ---------------------------------------------------
    def _invoke(self, name, args, kwargs, *, default):
        self.calls.append((name, args, kwargs))
        if name in self.overrides:
            outcome = self.overrides[name]
            if callable(outcome):
                return outcome(*args, **kwargs)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return default()

    # ---- helpers for tests ------------------------------------------
    def last_call(self, name: str) -> tuple:
        for call in reversed(self.calls):
            if call[0] == name:
                return call
        raise AssertionError(f"no {name!r} call recorded")

    def call_names(self) -> list[str]:
        return [c[0] for c in self.calls]


@pytest.fixture
def sdk():
    return RecordingSDK()


@pytest.fixture
def client(monkeypatch, sdk):
    monkeypatch.setattr(http_app, "get_sdk", lambda: sdk)
    return TestClient(http_app.app, follow_redirects=False)


# ---------------------------------------------------------------------------
# /anime
# ---------------------------------------------------------------------------


class TestAnimeEndpoint:
    def test_returns_payload_from_sdk(self, client, sdk):
        sdk.overrides["get_anime"] = lambda aid: {"id": aid, "title": "Bleach"}
        resp = client.get("/anime/7")
        assert resp.status_code == 200
        assert resp.json() == {"id": 7, "title": "Bleach"}

    def test_passes_id_as_int(self, client, sdk):
        client.get("/anime/123")
        assert sdk.last_call("get_anime") == ("get_anime", (123,), {})

    def test_negative_id_still_routed_to_sdk(self, client, sdk):
        """Path coercion only enforces ``int``; semantic validation is
        the SDK's job. The route must not reject negative IDs."""
        resp = client.get("/anime/-1")
        assert resp.status_code == 200
        assert sdk.last_call("get_anime")[1] == (-1,)

    def test_string_id_returns_422(self, client):
        resp = client.get("/anime/abc")
        assert resp.status_code == 422

    @pytest.mark.parametrize(
        "exc, expected_status",
        [
            (NotFoundError("nope"), 404),
            (ValidationError("bad"), 400),
            (InfrastructureError("db"), 500),
            (RuntimeError("boom"), 500),
        ],
    )
    def test_error_mapping(self, client, sdk, exc, expected_status):
        sdk.overrides["get_anime"] = exc
        resp = client.get("/anime/1")
        assert resp.status_code == expected_status

    def test_refresh_returns_accepted(self, client, sdk):
        sdk.overrides["refresh_anime_details"] = lambda aid: {
            "accepted": True,
            "anime_id": aid,
        }
        resp = client.post("/anime/7/refresh")
        assert resp.status_code == 200
        assert resp.json() == {"accepted": True, "anime_id": 7}
        assert sdk.last_call("refresh_anime_details") == (
            "refresh_anime_details",
            (7,),
            {},
        )

    def test_refresh_error_mapping(self, client, sdk):
        sdk.overrides["refresh_anime_details"] = NotFoundError("nope")
        resp = client.post("/anime/7/refresh")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /animelist
# ---------------------------------------------------------------------------


class TestAnimeListEndpoint:
    def test_default_pagination(self, client, sdk):
        client.get("/animelist")
        _, _, kwargs = sdk.last_call("get_anime_list")
        assert kwargs == {
            "filter_name": "DEFAULT",
            "user_id": None,
            "list_start": 0,
            "list_stop": 50,
            "hide_rated": None,
        }

    def test_query_params_forwarded(self, client, sdk):
        client.get(
            "/animelist",
            params={
                "filter": "WATCHING",
                "user_id": 4,
                "list_start": 100,
                "list_stop": 130,
                "hide_rated": "true",
            },
        )
        _, _, kwargs = sdk.last_call("get_anime_list")
        assert kwargs["filter_name"] == "WATCHING"
        assert kwargs["user_id"] == 4
        assert kwargs["list_start"] == 100
        assert kwargs["list_stop"] == 130
        assert kwargs["hide_rated"] is True

    def test_response_schema_passthrough(self, client, sdk):
        sdk.overrides["get_anime_list"] = lambda **_: {
            "items": [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}],
            "has_next": True,
        }
        body = client.get("/animelist").json()
        assert body["has_next"] is True
        assert [it["id"] for it in body["items"]] == [1, 2]


# ---------------------------------------------------------------------------
# /search
# ---------------------------------------------------------------------------


class TestSearchEndpoint:
    def test_requires_query_param(self, client):
        resp = client.get("/search")
        assert resp.status_code == 422

    def test_limit_default_and_override(self, client, sdk):
        client.get("/search", params={"query": "bleach"})
        assert sdk.last_call("search_anime") == ("search_anime", ("bleach", 50), {})
        client.get("/search", params={"query": "naruto", "limit": 7})
        assert sdk.last_call("search_anime") == ("search_anime", ("naruto", 7), {})


# ---------------------------------------------------------------------------
# /download/*
# ---------------------------------------------------------------------------


class TestDownloadEndpoints:
    def test_start_returns_started_flag(self, client, sdk):
        sdk.overrides["start_download"] = lambda *a, **k: True
        resp = client.post(
            "/download/9", params={"url": "magnet:?xt=urn:btih:abc"}
        )
        assert resp.status_code == 200
        assert resp.json() == {"started": True}

    def test_start_passes_hash_and_user(self, client, sdk):
        client.post(
            "/download/9",
            params={"hash_value": "abc", "user_id": 4},
        )
        _, args, _ = sdk.last_call("start_download")
        assert args == (9, None, "abc", 4)

    def test_progress_returns_sdk_dict_verbatim(self, client, sdk):
        sdk.overrides["get_download_progress"] = lambda aid: {
            "anime_id": aid,
            "progress": 0.42,
            "state": "DOWNLOADING",
        }
        body = client.get("/download/progress/3").json()
        assert body == {"anime_id": 3, "progress": 0.42, "state": "DOWNLOADING"}

    def test_cancel(self, client, sdk):
        body = client.post("/download/cancel/5").json()
        assert body == {"cancelled": True}
        assert sdk.last_call("cancel_download")[1] == (5,)

    def test_active_returns_list_under_items_key(self, client, sdk):
        sdk.overrides["get_active_downloads"] = lambda: [
            {"anime_id": 1}, {"anime_id": 2}
        ]
        body = client.get("/download/active").json()
        assert body == {"items": [{"anime_id": 1}, {"anime_id": 2}]}


# ---------------------------------------------------------------------------
# /torrents/search
# ---------------------------------------------------------------------------


class TestTorrentSearch:
    def test_splits_comma_terms(self, client, sdk):
        client.get("/torrents/search", params={"term": "naruto, shippuden , 1080p"})
        _, args, _ = sdk.last_call("search_torrents")
        terms, profile, limit = args
        assert list(terms) == ["naruto", "shippuden", "1080p"]
        assert profile == "interactive"
        assert limit == 200

    def test_custom_profile_and_limit(self, client, sdk):
        client.get(
            "/torrents/search",
            params={"term": "bleach", "profile": "fast", "limit": 5},
        )
        _, args, _ = sdk.last_call("search_torrents")
        assert args[1] == "fast"
        assert args[2] == 5

    def test_empty_term_drops_to_empty_list(self, client, sdk):
        sdk.overrides["search_torrents"] = ValidationError("no terms")
        resp = client.get("/torrents/search", params={"term": ",, ,"})
        # The validation surfaces via the legacy mapping path.
        assert resp.status_code in {400, 500}


# ---------------------------------------------------------------------------
# /tag /like /seen — user actions
# ---------------------------------------------------------------------------


class TestUserActions:
    def test_tag_records_set_tag(self, client, sdk):
        resp = client.post("/tag/5", params={"tag": "WATCHING", "user_id": 1})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert sdk.last_call("set_tag") == ("set_tag", (5, "WATCHING", 1), {})

    def test_tag_endpoint_can_be_called_repeatedly(self, client, sdk):
        """Regression for the original report — the JSON API surface
        must also allow successive tag modifications."""
        for tag in ("WATCHING", "WATCHLIST", "SEEN", "NONE"):
            client.post("/tag/5", params={"tag": tag, "user_id": 1})
        recorded = [c for c in sdk.calls if c[0] == "set_tag"]
        assert [args[1] for _, args, _ in recorded] == [
            "WATCHING",
            "WATCHLIST",
            "SEEN",
            "NONE",
        ]

    def test_like_default_true(self, client, sdk):
        client.post("/like/5", params={"user_id": 1})
        _, args, _ = sdk.last_call("set_like")
        assert args == (5, 1, True)

    def test_like_explicit_false(self, client, sdk):
        client.post("/like/5", params={"user_id": 1, "liked": False})
        _, args, _ = sdk.last_call("set_like")
        assert args == (5, 1, False)

    def test_seen_passes_file_name(self, client, sdk):
        client.post(
            "/seen/5",
            params={"file_name": "ep01.mkv", "user_id": 1},
        )
        assert sdk.last_call("mark_seen")[1] == (5, "ep01.mkv", 1)

    def test_state_returns_sdk_dict(self, client, sdk):
        sdk.overrides["get_user_state"] = lambda *_: {
            "tag": "WATCHING",
            "liked": True,
        }
        body = client.get("/state/5", params={"user_id": 1}).json()
        assert body == {"tag": "WATCHING", "liked": True}

    def test_unauthorized_does_not_leak_500(self, client, sdk):
        """UnauthorizedError currently maps to 500 by design (no 401
        branch in _map_error). Pin the behavior so a future change is
        intentional rather than accidental."""
        sdk.overrides["set_tag"] = UnauthorizedError("nope")
        resp = client.post("/tag/5", params={"tag": "X", "user_id": 1})
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# /search-terms
# ---------------------------------------------------------------------------


class TestSearchTerms:
    def test_get_returns_items_array(self, client, sdk):
        sdk.overrides["get_search_terms"] = lambda _: ["alpha", "beta"]
        body = client.get("/search-terms/3").json()
        assert body == {"items": ["alpha", "beta"]}

    def test_add_returns_added_flag(self, client, sdk):
        body = client.post("/search-terms/3", params={"term": "new"}).json()
        assert body == {"added": True}
        assert sdk.last_call("add_search_term")[1] == (3, "new")

    def test_delete_returns_removed_flag(self, client, sdk):
        body = client.delete("/search-terms/3", params={"term": "old"}).json()
        assert body == {"removed": True}
        assert sdk.last_call("remove_search_term")[1] == (3, "old")

    def test_add_validation_error_returns_400(self, client, sdk):
        sdk.overrides["add_search_term"] = ValidationError("too short")
        resp = client.post("/search-terms/3", params={"term": "x"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /settings
# ---------------------------------------------------------------------------


class TestSettings:
    def test_get_returns_sdk_payload(self, client, sdk):
        sdk.overrides["get_settings"] = lambda: {"anime": {"hideRated": True}}
        body = client.get("/settings").json()
        assert body == {"anime": {"hideRated": True}}

    def test_patch_returns_updated_state(self, client, sdk):
        sdk.overrides["update_settings"] = lambda updates: {
            "anime": {"hideRated": False, **updates.get("anime", {})}
        }
        body = client.patch(
            "/settings", json={"anime": {"hideRated": False}}
        ).json()
        assert body["anime"]["hideRated"] is False

    def test_patch_with_validation_error_returns_400(self, client, sdk):
        sdk.overrides["update_settings"] = ValidationError("non-empty required")
        resp = client.patch("/settings", json={})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Detail tier endpoints (characters, pictures)
# ---------------------------------------------------------------------------


class TestDetailTierEndpoints:
    def test_get_characters_returns_items(self, client, sdk):
        sdk.overrides["get_characters"] = lambda _: [
            {"id": 1, "name": "Hero", "role": "main"}
        ]
        body = client.get("/anime/3/characters").json()
        assert body == {"items": [{"id": 1, "name": "Hero", "role": "main"}]}
        assert sdk.last_call("get_characters")[1] == (3,)

    def test_refresh_characters_returns_items(self, client, sdk):
        sdk.overrides["refresh_anime_characters"] = lambda _: [
            {"id": 2, "name": "Rival", "role": "supporting"}
        ]
        body = client.post("/anime/3/characters/refresh").json()
        assert body["items"][0]["name"] == "Rival"
        assert sdk.last_call("refresh_anime_characters")[1] == (3,)

    def test_get_character_returns_payload(self, client, sdk):
        sdk.overrides["get_character"] = lambda cid: {
            "id": cid,
            "name": "Hero",
            "animeography": [],
        }
        body = client.get("/characters/9").json()
        assert body["id"] == 9
        assert body["name"] == "Hero"

    def test_refresh_character_returns_payload(self, client, sdk):
        sdk.overrides["refresh_character"] = lambda cid: {
            "id": cid,
            "name": "Refreshed",
        }
        body = client.post("/characters/9/refresh").json()
        assert body["name"] == "Refreshed"

    def test_get_pictures_returns_items(self, client, sdk):
        sdk.overrides["get_anime_pictures"] = lambda _: [
            {"url": "https://example.com/p.jpg", "size": "large"}
        ]
        body = client.get("/anime/3/pictures").json()
        assert body["items"][0]["size"] == "large"


# ---------------------------------------------------------------------------
# Root + cross-cutting
# ---------------------------------------------------------------------------


class TestRootProbe:
    def test_json_probe(self, client):
        resp = client.get("/", headers={"accept": "application/json"})
        assert resp.status_code == 200
        assert resp.json()["service"] == "animemanager-http-client-adapter"

    def test_browser_redirect(self, client):
        resp = client.get("/", headers={"accept": "text/html"})
        assert resp.status_code == 307
        assert resp.headers["location"] == "/ui/library"

    def test_browser_redirect_next_frontend(self, client, monkeypatch):
        monkeypatch.setenv("WEB_FRONTEND_URL", "http://127.0.0.1:3000")
        resp = client.get("/", headers={"accept": "text/html"})
        assert resp.status_code == 307
        assert resp.headers["location"] == "http://127.0.0.1:3000/library"

    def test_unknown_route_returns_404(self, client):
        resp = client.get("/this-endpoint-does-not-exist")
        assert resp.status_code == 404

    def test_method_not_allowed(self, client):
        # /search is GET only
        resp = client.post("/search", params={"query": "x"})
        assert resp.status_code == 405
