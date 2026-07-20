"""Tests for AnimeApplicationService top browse use-cases."""

from __future__ import annotations

from application.services.anime_service import AnimeApplicationService
from domain.dto import TopBrowseRequest
from domain.entities import AnimeEntity
from domain.errors import ValidationError


class FakeRepository:
    def list_by_top_category(self, category, limit=50):
        _ = limit
        if category == "airing":
            return [AnimeEntity(id=1, title="Local Airing", status="AIRING")]
        return []

    def list_by_genre(self, genre, limit=50):
        _ = (genre, limit)
        return []

    def list_by_airing_season(self, year, season, limit=50):
        _ = (year, season, limit)
        return []

    def search(self, query, limit=50):
        _ = (query, limit)
        return []


class FakeProvider:
    def browse_top(self, category, limit=50):
        _ = limit
        return [AnimeEntity(id=2, title=f"Remote {category}")]

    def stream_browse_top(self, category, limit=50):
        for item in self.browse_top(category, limit):
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


def test_browse_top_merges_local_and_provider():
    results = _service().browse_top(TopBrowseRequest(category="airing", limit=50))
    assert sorted(item.id for item in results.items) == [1, 2]
    assert results.has_next is False


def test_browse_top_all_is_provider_first_when_no_local_seed():
    results = _service().browse_top(TopBrowseRequest(category="all", limit=50))
    assert [item.id for item in results.items] == [2]


def test_browse_top_pages_with_offset():
    class ManyRepo(FakeRepository):
        def list_by_top_category(self, category, limit=50):
            _ = category
            return [
                AnimeEntity(id=i, title=f"Local {i}", status="AIRING")
                for i in range(1, limit + 1)
            ]

    page = _service(repo=ManyRepo()).browse_top(
        TopBrowseRequest(category="airing", limit=2, offset=2)
    )
    assert [item.id for item in page.items] == [3, 4]
    assert page.has_next is True


def test_stream_browse_top_yields_local_then_remote():
    results = list(
        _service().stream_browse_top(TopBrowseRequest(category="airing", limit=50))
    )
    assert [item.id for item in results] == [1, 2]


def test_browse_top_rejects_invalid_category():
    try:
        _service().browse_top(TopBrowseRequest(category="movie", limit=50))
    except ValidationError:
        return
    raise AssertionError("expected ValidationError")
