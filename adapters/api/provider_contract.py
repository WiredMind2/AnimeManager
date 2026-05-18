"""Shared metadata provider adapter contract.

Every wrapper under ``adapters.api`` should implement the methods declared
here. Optional methods may be omitted; the coordinator skips providers that
lack ``searchAnime``.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Protocol, runtime_checkable


@runtime_checkable
class MetadataProviderAdapter(Protocol):
    """Minimum surface for a metadata provider wrapper."""

    apiKey: str

    def searchAnime(self, search: str, limit: int = 50) -> Iterable[Any]:
        ...

    def anime(self, id: int) -> Any:
        ...


@runtime_checkable
class SchedulableMetadataProvider(MetadataProviderAdapter, Protocol):
    def schedule(self, limit: int = 50) -> Iterable[Any]:
        ...


REQUIRED_METHODS = ("searchAnime", "anime")
OPTIONAL_METHODS = (
    "schedule",
    "season",
    "character",
    "animeCharacters",
    "animePictures",
)


def provider_name(provider: Any) -> str:
    return getattr(provider, "__name__", None) or type(provider).__name__


def validate_provider(provider: Any) -> list[str]:
    """Return a list of missing required method names (empty if valid)."""
    missing = []
    for name in REQUIRED_METHODS:
        if not callable(getattr(provider, name, None)):
            missing.append(name)
    if not getattr(provider, "apiKey", None):
        missing.append("apiKey")
    return missing


__all__ = [
    "MetadataProviderAdapter",
    "SchedulableMetadataProvider",
    "REQUIRED_METHODS",
    "OPTIONAL_METHODS",
    "provider_name",
    "validate_provider",
]
