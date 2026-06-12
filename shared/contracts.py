"""
Typed data-transfer contracts used across the API->DB pipeline.

These DTOs draw a strict boundary between provider-shaped data and the
ingestion/persistence layer. Adapters MUST produce normalized records.
Anything not represented here is considered untrusted and ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class IngestionStatus(str, Enum):
    """Completion semantics for an ingestion run."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class ProviderName(str, Enum):
    """Known provider identifiers; new ones must be registered here."""

    JIKAN = "jikan"
    ANILIST = "anilist"
    KITSU = "kitsu"
    MAL = "myanimelist"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AnimeRecord:
    """Normalized anime record produced by adapters.

    Frozen so adapters cannot mutate records after creation. Internal id
    is mandatory; provider-specific identifiers belong in `external_ids`.
    """

    id: int
    title: str
    title_synonyms: Tuple[str, ...] = ()
    synopsis: Optional[str] = None
    episodes: Optional[int] = None
    duration: Optional[int] = None
    status: Optional[str] = None
    rating: Optional[str] = None
    date_from: Optional[int] = None
    date_to: Optional[int] = None
    picture: Optional[str] = None
    trailer: Optional[str] = None
    broadcast: Optional[str] = None
    genres: Tuple[str, ...] = ()
    external_ids: Dict[str, Any] = field(default_factory=dict)
    source_provider: ProviderName = ProviderName.UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RelationRecord:
    """Anime-to-anime relation."""

    id: int
    rel_id: int
    type: str
    name: str


@dataclass(frozen=True)
class MediaAssetRecord:
    """Picture / cover asset for an anime."""

    id: int
    url: str
    size: str  # one of: small, medium, large, original


@dataclass
class IngestionResult:
    """Outcome of a search/ingest call. Mutable summary, never trusted as data."""

    status: IngestionStatus
    records: List[AnimeRecord] = field(default_factory=list)
    failed_providers: int = 0
    total_providers: int = 0
    elapsed_ms: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def successful_providers(self) -> int:
        return max(0, self.total_providers - self.failed_providers)


VALID_ASSET_SIZES = frozenset({"small", "medium", "large", "original"})
VALID_RELATION_TYPES = frozenset({"anime", "manga", "novel", "character"})

INDEX_PROVIDER_KEYS = frozenset({"mal_id", "kitsu_id", "anilist_id", "anidb_id"})


class RepairStrategy(str, Enum):
    """How startup/catalog repair groups duplicate rows."""

    PROVIDER_ID = "provider_id"
    TITLE = "title"
    ALL = "all"


@dataclass(frozen=True)
class ProviderAnimePayload:
    """Provider-neutral anime metadata before catalog identity resolution."""

    title: str
    external_ids: Dict[str, int] = field(default_factory=dict)
    title_synonyms: Tuple[str, ...] = ()
    synopsis: Optional[str] = None
    episodes: Optional[int] = None
    duration: Optional[int] = None
    status: Optional[str] = None
    rating: Optional[str] = None
    date_from: Optional[int] = None
    date_to: Optional[int] = None
    picture: Optional[str] = None
    trailer: Optional[str] = None
    broadcast: Optional[str] = None
    genres: Tuple[str, ...] = ()
    source_provider: ProviderName = ProviderName.UNKNOWN


@dataclass(frozen=True)
class ResolvedCatalogEntry:
    """Canonical internal catalogue id for a provider payload."""

    catalog_id: int
    external_ids: Dict[str, int] = field(default_factory=dict)
    merged_from: Tuple[int, ...] = ()
