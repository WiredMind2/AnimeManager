"""Resolve a single canonical internal id from cross-provider external ids."""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from adapters.persistence.catalog_repository import CatalogIndexRepository
from application.services.catalog_merge import CatalogMergeService
from shared.contracts import (
    INDEX_PROVIDER_KEYS,
    ProviderAnimePayload,
    ResolvedCatalogEntry,
)
from shared.telemetry import get_telemetry


def _normalize_external_ids(external_ids: Mapping[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for key, value in external_ids.items():
        if key not in INDEX_PROVIDER_KEYS or value is None:
            continue
        try:
            out[key] = int(value)
        except (TypeError, ValueError):
            continue
    return out


class CatalogIdentityService:
    """Single entry point for indexList identity assignment and linking."""

    def __init__(
        self,
        db: Any,
        *,
        merge_service: Optional[CatalogMergeService] = None,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._db = db
        self._index = CatalogIndexRepository(db)
        self._merge = merge_service or CatalogMergeService(db, log_fn=log_fn)
        self._telemetry = get_telemetry()

    @classmethod
    def from_database(cls, db: Any, **kwargs) -> "CatalogIdentityService":
        return cls(db, **kwargs)

    def resolve(self, payload: ProviderAnimePayload) -> ResolvedCatalogEntry:
        return self.resolve_external_ids(
            payload.external_ids,
            source_provider=payload.source_provider.value,
        )

    def resolve_external_ids(
        self,
        external_ids: Mapping[str, Any],
        *,
        source_provider: str = "unknown",
    ) -> ResolvedCatalogEntry:
        normalized = _normalize_external_ids(external_ids)
        if not normalized:
            raise ValueError("Cannot resolve catalogue identity without external ids")

        found: set[int] = set()
        for key, ext in normalized.items():
            internal_id = self._index.find_by_external(key, ext)
            if internal_id is not None:
                found.add(internal_id)

        merged_from: list[int] = []
        if len(found) > 1:
            canonical = min(found)
            for duplicate in sorted(found):
                if duplicate == canonical:
                    continue
                self._merge.merge(duplicate, canonical)
                merged_from.append(duplicate)
            self._telemetry.increment("catalog.identity.conflict")
            self._index.backfill_external_ids(canonical, normalized)
            return ResolvedCatalogEntry(
                catalog_id=canonical,
                external_ids=dict(normalized),
                merged_from=tuple(merged_from),
            )

        if len(found) == 1:
            canonical = next(iter(found))
            self._index.backfill_external_ids(canonical, normalized)
            return ResolvedCatalogEntry(
                catalog_id=canonical,
                external_ids=dict(normalized),
            )

        catalog_id = self._index.allocate(normalized)
        return ResolvedCatalogEntry(
            catalog_id=catalog_id,
            external_ids=dict(normalized),
        )

    def link(
        self,
        internal_id: int,
        external_ids: Mapping[str, Any],
    ) -> int:
        """Attach provider ids to an existing row; merge away conflicts."""
        normalized = _normalize_external_ids(external_ids)
        if not normalized:
            return int(internal_id)

        canonical = int(internal_id)
        for key, ext in normalized.items():
            existing = self._index.find_by_external(key, ext)
            if existing is None:
                continue
            if existing != canonical:
                canonical = self._merge.merge(
                    duplicate_id=canonical,
                    canonical_id=existing,
                )
                self._telemetry.increment("catalog.merge")

        self._index.backfill_external_ids(canonical, normalized)
        return canonical
