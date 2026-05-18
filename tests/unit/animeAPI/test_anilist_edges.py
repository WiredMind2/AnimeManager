"""Edge-case unit tests for ``adapters.api.AnilistCo`` (no network)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from adapters.api.AnilistCo import AnilistCoWrapper, QueryObject


# ---------------------------------------------------------------------------
# QueryObject
# ---------------------------------------------------------------------------


class TestQueryObject:
    def test_build_simple_field(self):
        q = QueryObject("Media", fields=["id", "title"])
        assert "Media" in str(q)
        assert "id" in str(q)
        assert "title" in str(q)

    def test_build_with_string_arg_value(self):
        q = QueryObject(
            "Media",
            args=[("search", "String", "naruto")],
            fields=["id"],
        )
        built = q.build()
        assert 'search: String = "naruto"' in built

    def test_build_with_int_arg_value(self):
        q = QueryObject("Page", args=[("page", "Int", 1)], fields=["total"])
        assert "page: Int = 1" in q.build()

    def test_set_arg_replaces_existing(self):
        q = QueryObject("Media", args=[("id", "Int", 1)])
        q.set_arg(("id", "Int", 2))
        assert ("id", "Int", 2) in q.args
        assert len([a for a in q.args if a[0] == "id"]) == 1

    def test_set_arg_appends_new(self):
        q = QueryObject("Media", args=[("id", "Int")])
        q.set_arg(("page", "Int", 1))
        assert len(q.args) == 2

    def test_add_and_del_field(self):
        q = QueryObject("Media", fields=["id"])
        q.add_field("title")
        assert "title" in q.fields
        q.del_field("id")
        assert "id" not in q.fields
        q.del_field("missing")  # no-op


# ---------------------------------------------------------------------------
# AnilistCoWrapper helpers
# ---------------------------------------------------------------------------


def _make_wrapper():
    w = object.__new__(AnilistCoWrapper)
    w.apiKey = "anilist_id"
    w.url = "https://graphql.anilist.co"
    w.session = MagicMock()
    w.log = MagicMock()
    w.getId = MagicMock(return_value=99)
    w.database = MagicMock()
    w._convertAnime = MagicMock(return_value={"id": 1, "title": "Test"})
    w.media_fields = ["id", "title"]
    w.media_query = QueryObject(
        "Media",
        args=(("id", "$id"), ("type", "ANIME")),
        fields=["id"],
    )
    w.pagination_query = QueryObject(
        "Page",
        args=(("page", "$page"), ("perPage", "$perPage")),
        fields=["pageInfo"],
    )
    return w


class TestAnilistAnime:
    def test_returns_none_when_no_anilist_id(self):
        w = _make_wrapper()
        w.getId.return_value = None
        assert w.anime(1) is None
        w.session.request.assert_not_called()

    def test_network_error_returns_none(self):
        w = _make_wrapper()
        w.session.request.side_effect = OSError("offline")
        assert w.anime(1) is None
        w.log.assert_called()

    def test_invalid_json_returns_none(self):
        w = _make_wrapper()
        w.session.request.return_value = SimpleNamespace(
            json=MagicMock(side_effect=ValueError("bad json"))
        )
        assert w.anime(1) is None

    def test_empty_data_returns_none(self):
        w = _make_wrapper()
        w.session.request.return_value = SimpleNamespace(json=lambda: {"data": None})
        assert w.anime(1) is None

    def test_happy_path(self):
        w = _make_wrapper()
        w.session.request.return_value = SimpleNamespace(
            json=lambda: {"data": {"Media": {"id": 99, "title": {"romaji": "A"}}}}
        )
        out = w.anime(1)
        assert out == {"id": 1, "title": "Test"}
        w._convertAnime.assert_called_once()

    def test_falls_back_to_requests_when_no_session(self):
        w = _make_wrapper()
        del w.session
        with patch("adapters.api.AnilistCo.requests.post") as post:
            post.return_value = SimpleNamespace(
                json=lambda: {"data": {"Media": {"id": 1}}}
            )
            w.anime(1)
            post.assert_called_once()


class TestAnilistSearchAnime:
    def test_yields_converted_rows_up_to_limit(self):
        w = _make_wrapper()
        media = {"id": 1, "title": {"romaji": "A"}}
        w.iterate = MagicMock(return_value=iter([media, media, media]))
        w._convertAnime.side_effect = lambda m: {"id": m["id"], "title": "X"}

        rows = list(w.searchAnime("naruto", limit=2))
        assert len(rows) == 2

    def test_skips_empty_conversions(self):
        w = _make_wrapper()
        w.iterate = MagicMock(return_value=iter([{"id": 1}, {"id": 2}]))
        w._convertAnime = MagicMock(side_effect=[None, {"id": 2, "title": "B"}])

        rows = list(w.searchAnime("x", limit=5))
        assert len(rows) == 1
        assert rows[0]["title"] == "B"


class TestAnilistIterate:
    def test_errors_in_response_stops_iteration(self):
        w = _make_wrapper()
        w.session.request.return_value = SimpleNamespace(
            json=lambda: {"errors": [{"message": "rate limited"}]}
        )
        assert list(w.iterate("query {}", {"page": 1})) == []
        w.log.assert_called()

    def test_network_error_returns_immediately(self):
        w = _make_wrapper()
        w.session.request.side_effect = ConnectionError("down")
        assert list(w.iterate("query {}", {"page": 1})) == []

    def test_invalid_json_returns_immediately(self):
        w = _make_wrapper()
        w.session.request.return_value = SimpleNamespace(
            json=MagicMock(side_effect=ValueError("nope"))
        )
        assert list(w.iterate("query {}", {"page": 1})) == []

    def test_no_page_data_returns(self):
        w = _make_wrapper()
        w.session.request.return_value = SimpleNamespace(json=lambda: {"data": {}})
        assert list(w.iterate("query {}", {"page": 1})) == []

    def test_yields_media_from_page(self):
        w = _make_wrapper()
        w.session.request.return_value = SimpleNamespace(
            json=lambda: {
                "data": {
                    "Page": {
                        "media": [{"id": 5}],
                        "pageInfo": {"hasNextPage": False},
                    }
                }
            }
        )
        assert list(w.iterate("query {}", {"page": 1})) == [{"id": 5}]
