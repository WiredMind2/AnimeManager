"""Edge-case unit tests for ``adapters.api.JikanMoe.JikanMoeWrapper``.

We never reach the network: the wrapper is stripped of its parent constructor
and ``get``/``delay``/``getId``/``getDatabase``/``save_pictures`` are mocked.
"""

from __future__ import annotations

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
    inst.cooldown = 0.0
    inst.last = 0.0
    inst.base_url = "https://api.jikan.moe/v4"
    inst.mapped_external = {}
    inst.session = MagicMock()
    inst.database = MagicMock()
    inst.database.getId.return_value = 1
    inst.queue = MagicMock()
    inst.defer_writes = False
    inst.api_cache = MagicMock()
    inst.api_cache.get.return_value = None
    inst.delay = MagicMock()
    inst.get = MagicMock()
    inst.getId = MagicMock()
    inst.getDatabase = MagicMock()
    inst.save_pictures = MagicMock()
    inst.save_relations = MagicMock()
    inst.save_broadcast = MagicMock()
    inst.save_genres = MagicMock()
    inst.save_animeography = MagicMock()
    inst._convertAnime = MagicMock(side_effect=lambda d: {"id": d.get("mal_id"), "title": d.get("title", "")})
    inst._convertCharacter = MagicMock(side_effect=lambda c, role=None, anime_id=None: {"id": c.get("mal_id") if c else None, "role": role})
    return inst


# ---------------------------------------------------------------------------
# anime()
# ---------------------------------------------------------------------------


class TestAnime:
    def test_anime_returns_empty_when_no_mal_id(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.getId.return_value = None
        assert w.anime(1) == {}
        w.get.assert_not_called()

    def test_anime_returns_empty_when_get_returns_non_dict(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.getId.return_value = 5
        w.get.return_value = None
        assert w.anime(1) == {}

    def test_anime_returns_empty_when_no_data(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.getId.return_value = 5
        w.get.return_value = {}
        assert w.anime(1) == {}

    def test_anime_happy_path(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.getId.return_value = 5
        w.get.return_value = {"data": {"mal_id": 5, "title": "Naruto"}}
        out = w.anime(1)
        assert out == {"id": 5, "title": "Naruto"}


# ---------------------------------------------------------------------------
# animeCharacters()
# ---------------------------------------------------------------------------


class TestAnimeCharacters:
    def test_no_mal_id_returns_empty(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.getId.return_value = None
        assert list(w.animeCharacters(1)) == []

    def test_non_dict_returns_empty(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.getId.return_value = 5
        w.get.return_value = None
        assert list(w.animeCharacters(1)) == []

    def test_no_data_key_returns_empty(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.getId.return_value = 5
        w.get.return_value = {}
        assert list(w.animeCharacters(1)) == []

    def test_yields_characters(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.getId.return_value = 5
        w.get.return_value = {
            "data": [
                {"character": {"mal_id": 1}, "role": "Main"},
                {"character": {"mal_id": 2}, "role": "Supporting"},
            ]
        }
        out = list(w.animeCharacters(99))
        assert len(out) == 2


# ---------------------------------------------------------------------------
# animePictures()
# ---------------------------------------------------------------------------


class TestAnimePictures:
    def test_returns_empty_when_non_dict(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.get.return_value = None
        assert w.animePictures(1) == []

    def test_returns_empty_when_no_pictures_key(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.get.return_value = {}
        assert w.animePictures(1) == []

    def test_returns_pictures_list(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.get.return_value = {"pictures": [{"url": "a"}, {"url": "b"}]}
        out = w.animePictures(1)
        assert len(out) == 2


# ---------------------------------------------------------------------------
# schedule()
# ---------------------------------------------------------------------------


class TestSchedule:
    def test_429_short_circuits(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.get.return_value = {"status": 429}
        out = list(w.schedule())
        assert out == []

    def test_empty_schedules_falls_back_to_season(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.get.side_effect = [
            {"data": []},
            {"data": [{"mal_id": 3, "title": "Season Show"}]},
        ]
        out = list(w.schedule(limit=5))
        assert len(out) == 1
        assert w.get.call_args_list[1].args[0].startswith("/seasons/")

    def test_yields_from_schedules(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.get.side_effect = [
            {"data": [{"mal_id": 1, "title": "A"}, {"mal_id": 2, "title": "B"}]},
            {"data": []},
        ]
        out = list(w.schedule())
        assert len(out) == 2

    def test_does_not_call_top_anime(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.get.side_effect = [
            {"data": []},
            {"data": [{"mal_id": 3, "title": "C"}]},
        ]
        list(w.schedule(limit=5))
        called_paths = [call.args[0] for call in w.get.call_args_list]
        assert "/top/anime" not in called_paths
        assert any(path.startswith("/seasons/") for path in called_paths)


# ---------------------------------------------------------------------------
# searchAnime()
# ---------------------------------------------------------------------------


class TestSearchAnime:
    def test_non_dict_returns_nothing(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.get.return_value = None
        out = list(w.searchAnime("naruto"))
        assert out == []

    def test_yields_each_result(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.get.return_value = {
            "data": [
                {"mal_id": 1, "title": "A"},
                {"mal_id": 2, "title": "B"},
            ]
        }
        # Make _convertAnime return non-empty.
        # _searchAnimeLetter call returns empty so iteration ends.
        with patch.object(w, "searchAnimeLetter", return_value=iter([])):
            out = list(w.searchAnime("naruto", limit=2))
        assert len(out) == 2

    def test_respects_limit(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.get.return_value = {
            "data": [
                {"mal_id": 1, "title": "A"},
                {"mal_id": 2, "title": "B"},
                {"mal_id": 3, "title": "C"},
            ]
        }
        with patch.object(w, "searchAnimeLetter", return_value=iter([])):
            out = list(w.searchAnime("naruto", limit=1))
        # Should produce exactly 1.
        assert len(out) == 1

    def test_falls_through_to_letter_search(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.get.return_value = {"data": []}
        with patch.object(
            w, "searchAnimeLetter", return_value=iter([{"id": 1}, {"id": 2}])
        ) as letter:
            out = list(w.searchAnime("naruto", limit=5))
            letter.assert_called_once()
            assert len(out) == 2


# ---------------------------------------------------------------------------
# character()
# ---------------------------------------------------------------------------


class TestCharacter:
    def test_non_dict_returns_empty(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.get.return_value = None
        assert w.character(1) == {}

    def test_happy_path(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.get.return_value = {"data": {"mal_id": 5}}
        out = w.character(1)
        assert out == {"id": 5, "role": None}

    def test_calls_getid_with_characters_table(self, JikanMoeWrapper):
        w = _make(JikanMoeWrapper)
        w.get.return_value = {}
        w.character(99)
        assert w.getId.call_args.kwargs.get("table", w.getId.call_args.args[1] if len(w.getId.call_args.args) > 1 else None) == "characters"
