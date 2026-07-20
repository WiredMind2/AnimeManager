"""Edge case tests for ``clients.sdk.ClientSDK``.

The SDK delegates to a composed facade. We inject a fake facade so the
tests do not exercise the legacy backend stack.
"""

from __future__ import annotations

import pytest

from clients.sdk import ClientSDK
from application.services.anime_hydration import AnimeDetailsResult
from domain.entities import AnimeEntity


class FakeFacade:
    def __init__(self):
        self.calls = []

    def search_anime(self, query, limit=50, offset=0):
        self.calls.append(("search_anime", query, limit, offset))

        class Response:
            items = [AnimeEntity(id=1, title="Cowboy")]
            has_next = False

        return Response()

    def get_anime_list(self, **kwargs):
        self.calls.append(("get_anime_list", kwargs))

        class Response:
            items = [AnimeEntity(id=1, title="Test")]
            has_next = True

        return Response()

    def get_anime_details(self, anime_id):
        return AnimeDetailsResult(
            entity=AnimeEntity(id=anime_id, title="Detail"),
            metadata_pending=False,
        )

    def start_download(self, anime_id, url=None, hash_value=None, user_id=None):
        return True

    def get_download_progress(self, anime_id):
        return {"anime_id": anime_id, "progress": 30}

    def cancel_download(self, anime_id):
        return True

    def get_active_downloads(self):
        return [{"anime_id": 1}]

    def search_torrents(self, terms, profile="interactive", limit=200):
        return [{"terms": terms, "profile": profile, "limit": limit}]

    def set_tag(self, anime_id, tag, user_id):
        self.calls.append(("set_tag", anime_id, tag, user_id))

    def set_like(self, anime_id, user_id, liked=True):
        self.calls.append(("set_like", anime_id, user_id, liked))

    def mark_seen(self, anime_id, file_name, user_id):
        self.calls.append(("mark_seen", anime_id, file_name, user_id))

    def get_user_state(self, anime_id, user_id):
        return {"tag": "WATCHING"}

    def get_search_terms(self, anime_id):
        return ["x"]

    def add_search_term(self, anime_id, term):
        return True

    def remove_search_term(self, anime_id, term):
        return True

    def get_settings(self):
        return {"anime": {"hideRated": True}}

    def update_settings(self, updates):
        return updates

    def get_relations(self, anime_id, relation_type="anime"):
        return [{"id": 1, "rel_id": 2}]


@pytest.fixture
def sdk():
    s = ClientSDK.__new__(ClientSDK)
    s._facade = FakeFacade()
    return s


class TestSDKEdges:
    def test_search_anime_returns_dicts(self, sdk):
        out = sdk.search_anime("cowboy", limit=20)
        assert isinstance(out, dict)
        assert "items" in out and "has_next" in out
        assert isinstance(out["items"][0], dict)
        assert out["items"][0]["id"] == 1
        assert out["items"][0]["title"] == "Cowboy"

    def test_search_anime_forwards_limit(self, sdk):
        sdk.search_anime("cowboy", limit=5)
        last = sdk._facade.calls[-1]
        assert last == ("search_anime", "cowboy", 5, 0)

    def test_get_anime_list_returns_dict_with_items_and_has_next(self, sdk):
        out = sdk.get_anime_list()
        assert "items" in out and "has_next" in out
        assert isinstance(out["items"][0], dict)
        assert out["has_next"] is True

    def test_get_anime_list_forwards_kwargs(self, sdk):
        sdk.get_anime_list(
            filter_name="LIKED",
            user_id=7,
            list_start=10,
            list_stop=20,
            hide_rated=False,
        )
        last = sdk._facade.calls[-1]
        assert last[0] == "get_anime_list"
        assert last[1]["filter_name"] == "LIKED"
        assert last[1]["user_id"] == 7
        assert last[1]["hide_rated"] is False

    def test_get_anime_returns_dict(self, sdk):
        out = sdk.get_anime(42)
        assert out["id"] == 42
        assert out["metadata_pending"] is False

    def test_start_download_pass_through(self, sdk):
        assert sdk.start_download(1, url="magnet:?xt=urn:btih:abc") is True

    def test_get_download_progress_returns_dict(self, sdk):
        assert sdk.get_download_progress(1) == {"anime_id": 1, "progress": 30}

    def test_search_torrents_pass_through(self, sdk):
        out = sdk.search_torrents(["a", "b"])
        assert out[0]["terms"] == ["a", "b"]
        assert out[0]["profile"] == "interactive"
        assert out[0]["limit"] == 200

    def test_set_tag_no_return(self, sdk):
        assert sdk.set_tag(1, "LIKED", 7) is None
        assert ("set_tag", 1, "LIKED", 7) in sdk._facade.calls

    def test_set_like_default_true(self, sdk):
        sdk.set_like(1, 7)
        assert ("set_like", 1, 7, True) in sdk._facade.calls

    def test_set_like_explicit_false(self, sdk):
        sdk.set_like(1, 7, liked=False)
        assert ("set_like", 1, 7, False) in sdk._facade.calls

    def test_mark_seen_forwards(self, sdk):
        sdk.mark_seen(1, "ep.mkv", 7)
        assert ("mark_seen", 1, "ep.mkv", 7) in sdk._facade.calls

    def test_update_settings_returns_dict(self, sdk):
        out = sdk.update_settings({"a": 1})
        assert out == {"a": 1}

    def test_get_relations_default_anime_type(self, sdk):
        out = sdk.get_relations(1)
        assert out == [{"id": 1, "rel_id": 2}]

    def test_get_search_terms_returns_list(self, sdk):
        assert sdk.get_search_terms(1) == ["x"]

    def test_facade_exception_propagates(self, sdk):
        sdk._facade.get_anime_details = lambda anime_id: (_ for _ in ()).throw(
            RuntimeError("boom")
        )
        with pytest.raises(RuntimeError):
            sdk.get_anime(1)

    def test_export_AnimeManagerError(self):
        # The module re-exports the error class for clients that want to
        # discriminate from generic exceptions.
        from clients.sdk import AnimeManagerError
        assert issubclass(AnimeManagerError, Exception)
