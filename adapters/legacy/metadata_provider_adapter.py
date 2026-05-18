"""Metadata provider port adapter (hexagonal boundary)."""

from __future__ import annotations

from typing import Any

from application.services.api_coordinator import APICoordinator
from domain.entities import AnimeEntity, from_legacy_anime


class LegacyMetadataProviderAdapter:
    """Adapter around :class:`APICoordinator` for provider-backed search."""

    def __init__(
        self,
        runtime: Any,
        repository: Any,
    ) -> None:
        self._runtime = runtime
        self._api_coordinator = APICoordinator()
        self._api_coordinator.set_api(runtime.api)
        self._api_coordinator.set_database_manager(repository._db_manager)

    @property
    def coordinator(self) -> APICoordinator:
        return self._api_coordinator

    def search(self, query: str, limit: int = 50) -> list[AnimeEntity]:
        results = self._api_coordinator.search_anime(query, limit=limit)
        if not results:
            return []
        return [from_legacy_anime(item) for item in results]

    def stream_search(self, query: str, limit: int = 50):
        """Yield :class:`AnimeEntity` instances per provider batch."""
        streamer = getattr(self._api_coordinator, "stream_search_anime", None)
        if callable(streamer):
            for item in streamer(query, limit=limit):
                yield from_legacy_anime(item)
            return
        for item in self.search(query, limit=limit):
            yield item


__all__ = ["LegacyMetadataProviderAdapter"]
