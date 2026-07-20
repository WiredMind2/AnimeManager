"""Tests for :class:`ApiCoordinatorAdapter`."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from adapters.metadata.api_coordinator_adapter import ApiCoordinatorAdapter


def _make_adapter(coordinator=None):
    db = MagicMock()
    api = MagicMock()
    with patch(
        "adapters.metadata.api_coordinator_adapter.APICoordinator"
    ) as coord_cls:
        coord = coordinator or MagicMock()
        coord_cls.return_value = coord
        adapter = ApiCoordinatorAdapter(api, db)
    return adapter, coord


def test_search_maps_results():
    adapter, coord = _make_adapter()
    coord.search_anime.return_value = [{"id": 1, "title": "Naruto"}]
    results = adapter.search( "naruto", limit=5)
    assert len(results) == 1
    assert results[0].title == "Naruto"
    coord.search_anime.assert_called_once_with("naruto", limit=5)


def test_search_empty_returns_empty_list():
    adapter, coord = _make_adapter()
    coord.search_anime.return_value = []
    assert adapter.search("x") == []


def test_stream_search_uses_native_streamer():
    adapter, coord = _make_adapter()
    coord.stream_search_anime.return_value = [{"id": 2, "title": "Bleach"}]
    items = list(adapter.stream_search("bleach", limit=3))
    assert len(items) == 1
    assert items[0].id == 2


def test_stream_search_falls_back_to_search():
    adapter, coord = _make_adapter()
    del coord.stream_search_anime
    coord.search_anime.return_value = [{"id": 3, "title": "One Piece"}]
    items = list(adapter.stream_search("piece"))
    assert items[0].title == "One Piece"


def test_browse_season_maps_results():
    adapter, coord = _make_adapter()
    coord.browse_season.return_value = [{"id": 4, "title": "Winter"}]
    results = adapter.browse_season(2024, "WINTER")
    assert results[0].title == "Winter"


def test_stream_browse_season_uses_native_streamer():
    adapter, coord = _make_adapter()
    coord.stream_browse_season.return_value = [{"id": 5, "title": "Spring"}]
    items = list(adapter.stream_browse_season(2024, "SPRING"))
    assert items[0].title == "Spring"


def test_stream_browse_season_falls_back_to_browse():
    adapter, coord = _make_adapter()
    del coord.stream_browse_season
    coord.browse_season.return_value = [{"id": 6, "title": "Fall"}]
    items = list(adapter.stream_browse_season(2023, "FALL"))
    assert items[0].title == "Fall"


def test_api_coordinator_property():
    adapter, coord = _make_adapter()
    assert adapter.api_coordinator is coord


def test_browse_genre_maps_results():
    adapter, coord = _make_adapter()
    coord.browse_genre.return_value = [{"id": 7, "title": "Comedy"}]
    results = adapter.browse_genre("Comedy")
    assert results[0].title == "Comedy"


def test_stream_browse_genre_uses_native_streamer():
    adapter, coord = _make_adapter()
    coord.stream_browse_genre.return_value = [{"id": 8, "title": "Drama"}]
    items = list(adapter.stream_browse_genre("Drama"))
    assert items[0].title == "Drama"


def test_stream_browse_genre_falls_back_to_browse():
    adapter, coord = _make_adapter()
    del coord.stream_browse_genre
    coord.browse_genre.return_value = [{"id": 9, "title": "Action"}]
    items = list(adapter.stream_browse_genre("Action"))
    assert items[0].title == "Action"


def test_browse_top_maps_results():
    adapter, coord = _make_adapter()
    coord.browse_top.return_value = [{"id": 10, "title": "Popular"}]
    results = adapter.browse_top("all")
    assert results[0].title == "Popular"


def test_stream_browse_top_uses_native_streamer():
    adapter, coord = _make_adapter()
    coord.stream_browse_top.return_value = [{"id": 11, "title": "Airing"}]
    items = list(adapter.stream_browse_top("airing"))
    assert items[0].title == "Airing"


def test_stream_browse_top_falls_back_to_browse():
    adapter, coord = _make_adapter()
    del coord.stream_browse_top
    coord.browse_top.return_value = [{"id": 12, "title": "Upcoming"}]
    items = list(adapter.stream_browse_top("upcoming"))
    assert items[0].title == "Upcoming"
