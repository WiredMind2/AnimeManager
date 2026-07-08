"""Tests for AnimeApplicationService genre browse use-cases."""

from __future__ import annotations

from application.services.anime_service import AnimeApplicationService
from domain.dto import GenreBrowseRequest, SearchRequest
from domain.entities import AnimeEntity
from domain.errors import ValidationError


class FakeRepository:
    def list_by_genre(self, genre, limit=50):
        _ = (genre, limit)
        return [AnimeEntity(id=1, title="Local Comedy", genres=["Comedy"])]

    def list_by_airing_season(self, year, season, limit=50):
        _ = (year, season, limit)
        return []

    def search(self, query, limit=50):
        _ = (query, limit)
        return [AnimeEntity(id=3, title=f"Title match {query}")]


class FakeProvider:
    def browse_genre(self, genre, limit=50):
        _ = (genre, limit)
        return [AnimeEntity(id=2, title="Remote Comedy", genres=["Comedy"])]

    def stream_browse_genre(self, genre, limit=50):
        for item in self.browse_genre(genre, limit):
            yield item

    def search(self, query, limit=50):
        _ = (query, limit)
        return []


def _service(repo=None, provider=None):
    return AnimeApplicationService(
        anime_repository=repo or FakeRepository(),
        metadata_provider=provider or FakeProvider(),
        download_port=object(),
        user_actions_port=object(),
    )


def test_browse_genre_merges_local_and_provider():
    results = _service().browse_genre(
        GenreBrowseRequest(genre="Comedy", limit=50)
    )
    assert sorted(item.id for item in results) == [1, 2]


def test_stream_browse_genre_yields_local_then_remote():
    results = list(
        _service().stream_browse_genre(
            GenreBrowseRequest(genre="Comedy", limit=50)
        )
    )
    assert [item.id for item in results] == [1, 2]


def test_browse_genre_rejects_invalid_genre():
    try:
        _service().browse_genre(
            GenreBrowseRequest(genre="Not A Genre", limit=50)
        )
    except ValidationError:
        return
    raise AssertionError("expected ValidationError")


def test_search_anime_merges_local_genre_matches():
    results = _service().search_anime(SearchRequest(query="Comedy", limit=50))
    assert sorted(item.id for item in results) == [1, 3]


def test_stream_search_anime_yields_genre_matches_before_title_search():
    results = list(
        _service().stream_search_anime(SearchRequest(query="Comedy", limit=50))
    )
    assert [item.id for item in results] == [1, 3]
