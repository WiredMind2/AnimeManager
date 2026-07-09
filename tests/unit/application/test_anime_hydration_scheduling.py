"""Tests that list/search paths schedule metadata hydration."""

from __future__ import annotations

from application.services.anime_hydration import AnimeHydrationService
from application.services.anime_service import AnimeApplicationService
from domain.dto import AnimeListRequest, SearchRequest
from domain.entities import AnimeEntity


class FakeHydrationPort:
    def catalog_id_exists(self, catalog_id: int) -> bool:
        return int(catalog_id) in {1932}

    def hydrate_anime(self, catalog_id: int) -> bool:
        return True


class FakeRepository:
    def __init__(self):
        self.items = [
            AnimeEntity(id=1, title="Complete"),
            AnimeEntity(id=1932, title=""),
        ]

    def search(self, query, limit=50):
        return list(self.items)

    def list_anime(self, **kwargs):
        return list(self.items), False

    def list_by_airing_season(self, year, season, limit=50):
        return list(self.items)

    def list_by_genre(self, genre, limit=50):
        return list(self.items)

    def get_anime(self, anime_id):
        for item in self.items:
            if item.id == anime_id:
                return item
        return None

    def anime_row_exists(self, anime_id):
        entity = self.get_anime(anime_id)
        return entity is not None and bool((entity.title or "").strip())


class RecordingHydration(AnimeHydrationService):
    def __init__(self):
        self.scheduled: list[int] = []
        super().__init__(FakeHydrationPort(), FakeRepository())

    def schedule_entities(self, entities, *, priority: int = 1):
        for entity in entities:
            if entity.id > 0 and not (entity.title or "").strip():
                self.scheduled.append(entity.id)


class FakeProvider:
    def search(self, query, limit=50):
        return []


class FakeDownload:
    def start_download(self, *args, **kwargs):
        return True

    def get_download_progress(self, anime_id):
        return {}

    def cancel_download(self, anime_id):
        return True

    def get_active_downloads(self):
        return []

    def search_torrents(self, terms, profile="interactive", limit=200):
        return []


class FakeActions:
    def set_tag(self, *args, **kwargs):
        pass

    def set_like(self, *args, **kwargs):
        pass

    def mark_seen(self, *args, **kwargs):
        pass

    def get_user_state(self, anime_id, user_id):
        return {}


def _service(hydration):
    return AnimeApplicationService(
        FakeRepository(),
        FakeProvider(),
        FakeDownload(),
        FakeActions(),
        hydration_service=hydration,
    )


def test_get_anime_list_schedules_incomplete_rows():
    hydration = RecordingHydration()
    service = _service(hydration)
    service.get_anime_list(AnimeListRequest())
    assert 1932 in hydration.scheduled


def test_search_anime_schedules_incomplete_rows():
    hydration = RecordingHydration()
    service = _service(hydration)
    service.search_anime(SearchRequest(query="skeleton", limit=50))
    assert 1932 in hydration.scheduled
