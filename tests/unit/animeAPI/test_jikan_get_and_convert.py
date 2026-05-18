"""Additional Jikan.moe tests for ``get``, ``delay``, and conversion branches."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def JikanMoeWrapper():
    from adapters.api.JikanMoe import JikanMoeWrapper as _W

    return _W


def _make(JikanMoeWrapper):
    inst = object.__new__(JikanMoeWrapper)
    inst.apiKey = "mal_id"
    inst.cooldown = 0.5
    inst.last = time.time()
    inst.base_url = "https://api.jikan.moe/v4"
    inst.mapped_external = {
        "AnimeDB": {"api_key": "anidb_id", "regex": r".+aid=(\d+).*"}
    }
    inst.session = MagicMock()
    inst.database = MagicMock()
    inst.database.getId.return_value = 1
    inst.log = MagicMock()
    inst.save_pictures = MagicMock()
    inst.save_broadcast = MagicMock()
    inst.save_relations = MagicMock()
    inst.save_mapped = MagicMock(return_value=1)
    inst.getStatus = MagicMock(return_value="AIRING")
    return inst


def _anime_payload(**overrides):
    base = {
        "mal_id": 123,
        "title": "Test.",
        "title_english": "Test",
        "title_japanese": "テスト",
        "title_synonyms": [],
        "aired": {
            "prop": {
                "from": {"year": 2020, "month": 1, "day": 1},
                "to": {"year": 2020, "month": 3, "day": 1},
            }
        },
        "images": {
            "jpg": {
                "image_url": "http://img.jpg",
                "small_image_url": "http://small.jpg",
                "large_image_url": "http://large.jpg",
            }
        },
        "synopsis": "desc",
        "episodes": 12,
        "duration": "24 min",
        "rating": "PG-13 - Teens",
        "status": "Finished Airing",
    }
    base.update(overrides)
    return base


class TestJikanGet:
    def test_formats_path_and_query_params(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.session.request.return_value = SimpleNamespace(
            json=lambda: {"data": []}, status_code=200
        )
        w.get("/anime/{id}/full", id=5, q="naruto")
        call = w.session.request.call_args
        assert "/anime/5/full" in call.args[1]
        assert call.kwargs["params"] == {"q": "naruto"}

    def test_request_exception_returns_empty(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.session.request.side_effect = OSError("down")
        assert w.get("/anime") == {}
        w.log.assert_called()

    def test_invalid_json_returns_empty(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.session.request.return_value = SimpleNamespace(
            json=MagicMock(side_effect=ValueError("bad"))
        )
        assert w.get("/anime") == {}

    def test_falls_back_to_requests_without_session(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        del w.session
        with patch("adapters.api.JikanMoe.requests.get") as get:
            get.return_value = SimpleNamespace(json=lambda: {"ok": True})
            assert w.get("/anime") == {"ok": True}


class TestJikanDelay:
    def test_delay_updates_last_timestamp(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.cooldown = 0.0
        w.last = 0.0
        before = w.last
        w.delay()
        assert w.last >= before


class TestJikanSearchAnimeLetter:
    def test_paginates_until_no_next_page(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.delay = MagicMock()
        w._convertAnime = MagicMock(return_value={"id": 1})
        w.get = MagicMock(
            side_effect=[
                {
                    "data": [{"mal_id": 1}],
                    "pagination": {"has_next_page": True},
                },
                {"data": [{"mal_id": 2}], "pagination": {"has_next_page": False}},
            ]
        )
        rows = list(w.searchAnimeLetter("n", limit=10))
        assert len(rows) == 2
        assert w.get.call_count == 2


class TestJikanConvertAnime:
    def test_strips_trailing_dot_from_title(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        out = w._convertAnime(_anime_payload())
        assert out["title"] == "Test"

    def test_returns_empty_when_no_date_from(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        payload = _anime_payload()
        payload.pop("aired")
        assert w._convertAnime(payload) == {}

    def test_saves_broadcast_for_valid_weekday(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        payload = _anime_payload(
            broadcast={"day": "Sundays", "time": "23:30"}
        )
        w._convertAnime(payload)
        w.save_broadcast.assert_called_once()

    def test_invalid_broadcast_day_raises(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        payload = _anime_payload(broadcast={"day": "Sometimes", "time": "12:00"})
        with pytest.raises(ValueError):
            w._convertAnime(payload)

    def test_saves_relations_and_external_mapping(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        payload = _anime_payload(
            relations=[
                {
                    "relation": "Sequel",
                    "entry": [{"type": "anime", "mal_id": 456}],
                }
            ],
            external=[
                {"name": "AnimeDB", "url": "https://anidb.net/?aid=789"},
            ],
        )
        out = w._convertAnime(payload)
        w.save_relations.assert_called_once()
        w.save_mapped.assert_called_once()
        assert out["id"] == 1
