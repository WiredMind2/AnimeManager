"""Unit tests for provider ``top()`` category filter mapping."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def JikanMoeWrapper():
    from adapters.api.JikanMoe import JikanMoeWrapper as _W

    return _W


def _make_jikan(JikanMoeWrapper):
    inst = object.__new__(JikanMoeWrapper)
    inst.apiKey = "mal_id"
    inst.cooldown = 0.0
    inst.last = 0.0
    inst.base_url = "https://api.jikan.moe/v4"
    inst.delay = MagicMock()
    inst.get = MagicMock(
        return_value={
            "data": [{"mal_id": 1, "title": "Popular"}],
            "pagination": {"has_next_page": False},
        }
    )
    inst._convertAnime = MagicMock(
        side_effect=lambda d: {"id": d.get("mal_id"), "title": d.get("title", "")}
    )
    return inst


def test_jikan_top_all_uses_bypopularity_filter(JikanMoeWrapper):
    inst = _make_jikan(JikanMoeWrapper)
    results = list(inst.top("all", limit=5))
    assert results[0]["title"] == "Popular"
    kwargs = inst.get.call_args
    assert kwargs[0][0] == "/top/anime"
    assert kwargs[1]["filter"] == "bypopularity"


def test_jikan_top_airing_and_upcoming_filters(JikanMoeWrapper):
    inst = _make_jikan(JikanMoeWrapper)
    list(inst.top("airing", limit=1))
    assert inst.get.call_args[1]["filter"] == "airing"
    list(inst.top("upcoming", limit=1))
    assert inst.get.call_args[1]["filter"] == "upcoming"


def test_jikan_top_unknown_category_yields_nothing(JikanMoeWrapper):
    inst = _make_jikan(JikanMoeWrapper)
    assert list(inst.top("movie", limit=5)) == []
    inst.get.assert_not_called()


@pytest.fixture
def AnilistCoWrapper():
    from adapters.api.AnilistCo import AnilistCoWrapper as _W

    return _W


def test_anilist_top_all_sorts_by_popularity(AnilistCoWrapper):
    inst = object.__new__(AnilistCoWrapper)
    captured = {}

    def fake_iterate(query, variables):
        captured["query"] = query
        captured["variables"] = variables
        yield {"id": 9, "title": {"romaji": "Hit"}}

    inst.iterate = fake_iterate
    inst.pagination_query = SimpleNamespace(
        add_field=lambda field: field,
    )
    inst.media_fields = []
    inst._convertAnime = MagicMock(return_value={"id": 9, "title": "Hit"})

    # Build QueryObject the same way the method does by calling top().
    # We need QueryObject available on the module path used by the method.
    results = list(AnilistCoWrapper.top(inst, "all", limit=3))
    assert results[0]["title"] == "Hit"
    assert "status" not in captured["variables"]


def test_anilist_top_airing_sets_releasing_status(AnilistCoWrapper):
    inst = object.__new__(AnilistCoWrapper)
    captured = {}

    def fake_iterate(query, variables):
        captured["variables"] = variables
        yield {"id": 1}

    inst.iterate = fake_iterate
    inst.pagination_query = SimpleNamespace(add_field=lambda field: field)
    inst.media_fields = []
    inst._convertAnime = MagicMock(return_value={"id": 1, "title": "Air"})

    list(AnilistCoWrapper.top(inst, "airing", limit=1))
    assert captured["variables"]["status"] == "RELEASING"
