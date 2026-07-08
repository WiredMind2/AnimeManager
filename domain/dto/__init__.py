"""Application DTO contracts shared by clients.

This module is the canonical home of the DTO dataclasses. The legacy
``backend.domain.dto`` module is a thin compatibility shim that
re-exports from here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from domain.entities import AnimeEntity


@dataclass(slots=True)
class AnimeListRequest:
    filter: str = "DEFAULT"
    user_id: Optional[int] = None
    list_start: int = 0
    list_stop: int = 50
    hide_rated: Optional[bool] = None


@dataclass(slots=True)
class SearchRequest:
    query: str
    limit: int = 50


@dataclass(slots=True)
class SeasonBrowseRequest:
    year: int
    season: str
    limit: int = 50


@dataclass(slots=True)
class GenreBrowseRequest:
    genre: str
    limit: int = 50


@dataclass(slots=True)
class DownloadRequest:
    anime_id: int
    url: Optional[str] = None
    hash_value: Optional[str] = None
    user_id: Optional[int] = None


@dataclass(slots=True)
class AnimeListResponse:
    items: list[AnimeEntity] = field(default_factory=list)
    has_next: bool = False


__all__ = [
    "AnimeListRequest",
    "SearchRequest",
    "SeasonBrowseRequest",
    "GenreBrowseRequest",
    "DownloadRequest",
    "AnimeListResponse",
]
