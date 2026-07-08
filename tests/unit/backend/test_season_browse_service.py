"""Tests for AnimeApplicationService season browse use-cases."""

from __future__ import annotations

from application.services.anime_service import AnimeApplicationService
from domain.dto import SeasonBrowseRequest
from domain.entities import AnimeEntity
from domain.errors import ValidationError


class FakeRepository:
    def list_by_airing_season(self, year, season, limit=50):
        _ = (year, season, limit)
        return [AnimeEntity(id=1, title="Local Hit", status="FINISHED")]

    def search(self, query, limit=50):
        _ = (query, limit)
        return []


class FakeProvider:
    def browse_season(self, year, season, limit=50):
        _ = (year, season, limit)
        return [AnimeEntity(id=2, title="Remote Hit", status="AIRING")]

    def stream_browse_season(self, year, season, limit=50):
        for item in self.browse_season(year, season, limit):
            yield item


def _service(repo=None, provider=None):
    return AnimeApplicationService(
        anime_repository=repo or FakeRepository(),
        metadata_provider=provider or FakeProvider(),
        download_port=object(),
        user_actions_port=object(),
    )


def test_browse_season_merges_local_and_provider():
    results = _service().browse_season(
        SeasonBrowseRequest(year=2026, season="spring", limit=50)
    )
    assert sorted(item.id for item in results) == [1, 2]


def test_stream_browse_season_yields_local_then_remote():
    results = list(
        _service().stream_browse_season(
            SeasonBrowseRequest(year=2026, season="spring", limit=50)
        )
    )
    assert [item.id for item in results] == [1, 2]


def test_browse_season_rejects_invalid_season():
    try:
        _service().browse_season(
            SeasonBrowseRequest(year=2026, season="autumn", limit=50)
        )
    except ValidationError:
        return
    raise AssertionError("expected ValidationError")
