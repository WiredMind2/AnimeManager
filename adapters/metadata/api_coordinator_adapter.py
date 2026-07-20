"""Metadata provider adapter backed by APICoordinator."""

from __future__ import annotations

from typing import Any

from application.services.api_coordinator import APICoordinator
from application.services.database_manager import DatabaseManager
from domain.entities import AnimeEntity, from_legacy_anime


class ApiCoordinatorAdapter:
    """Implements :class:`ports.interfaces.MetadataProviderPort`."""

    def __init__(
        self,
        api: Any,
        db_manager: DatabaseManager,
        write_service: Any = None,
    ) -> None:
        self._api_coordinator = APICoordinator()
        self._api_coordinator.set_api(api)
        self._api_coordinator.set_database_manager(db_manager)
        if write_service is not None:
            self._api_coordinator.set_write_service(write_service)

    @property
    def api_coordinator(self) -> APICoordinator:
        return self._api_coordinator

    def search(self, query: str, limit: int = 50) -> list[AnimeEntity]:
        results = self._api_coordinator.search_anime(query, limit=limit)
        if not results:
            return []
        return [from_legacy_anime(item) for item in results]

    def stream_search(self, query: str, limit: int = 50):
        streamer = getattr(self._api_coordinator, "stream_search_anime", None)
        if callable(streamer):
            for item in streamer(query, limit=limit):
                yield from_legacy_anime(item)
            return
        for item in self.search(query, limit=limit):
            yield item

    def browse_season(
        self, year: int, season: str, limit: int = 50
    ) -> list[AnimeEntity]:
        results = self._api_coordinator.browse_season(year, season, limit=limit)
        if not results:
            return []
        return [from_legacy_anime(item) for item in results]

    def stream_browse_season(self, year: int, season: str, limit: int = 50):
        streamer = getattr(self._api_coordinator, "stream_browse_season", None)
        if callable(streamer):
            for item in streamer(year, season, limit=limit):
                yield from_legacy_anime(item)
            return
        for item in self.browse_season(year, season, limit=limit):
            yield item

    def browse_genre(self, genre, limit: int = 50) -> list[AnimeEntity]:
        results = self._api_coordinator.browse_genre(genre, limit=limit)
        if not results:
            return []
        return [from_legacy_anime(item) for item in results]

    def stream_browse_genre(self, genre, limit: int = 50):
        streamer = getattr(self._api_coordinator, "stream_browse_genre", None)
        if callable(streamer):
            for item in streamer(genre, limit=limit):
                yield from_legacy_anime(item)
            return
        for item in self.browse_genre(genre, limit=limit):
            yield item

    def browse_top(self, category: str, limit: int = 50) -> list[AnimeEntity]:
        results = self._api_coordinator.browse_top(category, limit=limit)
        if not results:
            return []
        return [from_legacy_anime(item) for item in results]

    def stream_browse_top(self, category: str, limit: int = 50):
        streamer = getattr(self._api_coordinator, "stream_browse_top", None)
        if callable(streamer):
            for item in streamer(category, limit=limit):
                yield from_legacy_anime(item)
            return
        for item in self.browse_top(category, limit=limit):
            yield item
