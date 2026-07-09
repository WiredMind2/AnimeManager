"""Backfill cross-provider external ids and merge orphan catalogue rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from adapters.persistence.catalog_repository import CatalogIndexRepository
from application.services.catalog_identity import (
    CatalogIdentityService,
    _normalize_external_ids,
)
from ports.interfaces import CatalogMappingPort
from shared.contracts import INDEX_PROVIDER_KEYS
from shared.telemetry import get_telemetry

DEFAULT_ENRICH_CATALOG_LIMIT = 200

_SINGLE_PROVIDER_WHERE = (
    "(mal_id IS NOT NULL) + (kitsu_id IS NOT NULL) + "
    "(anilist_id IS NOT NULL) + (anidb_id IS NOT NULL)"
) + " = 1"


def select_single_provider_ids_for_enrichment(db: Any, *, limit: int) -> list[int]:
    """Pick single-provider rows to enrich, prioritizing likely merge candidates."""
    quota = max(0, int(limit))
    if quota == 0:
        return []

    selected: list[int] = []
    seen: set[int] = set()

    try:
        duplicate_title_rows = db.sql(
            "SELECT i.id FROM indexList i "
            "JOIN anime a ON a.id = i.id "
            f"WHERE {_SINGLE_PROVIDER_WHERE} "
            "AND a.title IS NOT NULL AND TRIM(a.title) <> '' "
            "AND EXISTS ("
            "  SELECT 1 FROM anime a2 "
            "  JOIN indexList i2 ON i2.id = a2.id "
            "  WHERE a2.id <> a.id "
            "  AND LOWER(TRIM(a2.title)) = LOWER(TRIM(a.title))"
            ") "
            "ORDER BY i.id DESC LIMIT ?",
            (quota,),
        )
    except Exception:
        duplicate_title_rows = ()

    for row in duplicate_title_rows or []:
        catalog_id = int(row[0])
        if catalog_id in seen:
            continue
        seen.add(catalog_id)
        selected.append(catalog_id)
        if len(selected) >= quota:
            return selected

    remaining = quota - len(selected)
    if remaining <= 0:
        return selected

    if seen:
        placeholders = ",".join("?" * len(seen))
        not_in = f"AND i.id NOT IN ({placeholders})"
        params: tuple[Any, ...] = (*sorted(seen), remaining)
    else:
        not_in = ""
        params = (remaining,)

    try:
        fallback_rows = db.sql(
            "SELECT i.id FROM indexList i "
            f"WHERE {_SINGLE_PROVIDER_WHERE} {not_in} "
            "ORDER BY i.id DESC LIMIT ?",
            params,
        )
    except Exception:
        fallback_rows = ()

    for row in fallback_rows or []:
        catalog_id = int(row[0])
        if catalog_id in seen:
            continue
        seen.add(catalog_id)
        selected.append(catalog_id)

    return selected


def lookup_cross_ids(
    mapping_port: CatalogMappingPort,
    provider_key: str,
    external_id: int,
) -> Dict[str, int]:
    """Resolve one provider id to the full known cross-id set."""
    if provider_key == "kitsu_id":
        return mapping_port.lookup_kitsu_mappings(int(external_id))
    if provider_key == "anilist_id":
        return mapping_port.lookup_anilist_cross_ids(int(external_id))
    if provider_key == "mal_id":
        return mapping_port.lookup_mal_cross_ids(int(external_id))
    return {}


def expand_external_ids_with_mapping(
    external_ids: Mapping[str, Any],
    mapping_port: Optional[CatalogMappingPort],
    *,
    cache: Optional[Dict[Tuple[str, int], Dict[str, int]]] = None,
) -> Dict[str, int]:
    """Merge mapping API cross-refs into a provider id payload."""
    normalized = _normalize_external_ids(external_ids)
    if not normalized or mapping_port is None:
        return normalized

    merged = dict(normalized)
    for key, ext in normalized.items():
        cache_key = (key, int(ext))
        if cache is not None and cache_key in cache:
            discovered = cache[cache_key]
        else:
            discovered = lookup_cross_ids(mapping_port, key, int(ext))
            if cache is not None:
                cache[cache_key] = discovered
        for provider_key, value in discovered.items():
            if provider_key in INDEX_PROVIDER_KEYS and value is not None:
                merged[provider_key] = int(value)
    return _normalize_external_ids(merged)


@dataclass(frozen=True)
class EnrichmentResult:
    looked_up: int = 0
    enriched: int = 0
    merged: int = 0


class CatalogEnrichmentService:
    """Resolve single-provider ``indexList`` rows via external mapping APIs."""

    def __init__(
        self,
        db: Any,
        mapping_port: CatalogMappingPort,
        *,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._db = db
        self._mapping = mapping_port
        self._index = CatalogIndexRepository(db)
        self._identity = CatalogIdentityService.from_database(
            db,
            log_fn=log_fn,
        )
        self._telemetry = get_telemetry()
        self._log = log_fn

    def enrich_ids(self, catalog_ids: Sequence[int]) -> EnrichmentResult:
        result = EnrichmentResult()
        for catalog_id in catalog_ids:
            try:
                row_result = self._enrich_one(int(catalog_id))
            except Exception as exc:
                if self._log:
                    self._log(f"enrichment failed for {catalog_id}: {exc}")
                continue
            result = EnrichmentResult(
                looked_up=result.looked_up + row_result.looked_up,
                enriched=result.enriched + row_result.enriched,
                merged=result.merged + row_result.merged,
            )
        return result

    def enrich_single_provider_rows(self, *, limit: int = DEFAULT_ENRICH_CATALOG_LIMIT) -> EnrichmentResult:
        try:
            ids = select_single_provider_ids_for_enrichment(self._db, limit=int(limit))
        except Exception as exc:
            if self._log:
                self._log(f"enrichment scan failed: {exc}")
            return EnrichmentResult()

        return self.enrich_ids(ids)

    def _enrich_one(self, catalog_id: int) -> EnrichmentResult:
        existing = self._index.get_external_ids(catalog_id)
        if len(existing) != 1:
            return EnrichmentResult()

        provider_key = next(iter(existing))
        discovered = self._lookup_cross_ids(provider_key, existing[provider_key])
        if not discovered:
            return EnrichmentResult()

        merged_ids = {**existing, **discovered}
        if merged_ids == existing:
            return EnrichmentResult(looked_up=1)

        before_id = int(catalog_id)
        try:
            resolved = self._identity.resolve_external_ids(merged_ids)
        except Exception as exc:
            if self._log:
                self._log(f"enrichment resolve failed for {catalog_id}: {exc}")
            return EnrichmentResult(looked_up=1)
        after_id = int(resolved.catalog_id)
        merged = 1 if resolved.merged_from else 0
        if merged:
            self._telemetry.increment("catalog.enrichment.merges")
        self._telemetry.increment("catalog.enrichment.lookups")
        return EnrichmentResult(looked_up=1, enriched=1, merged=merged)

    def _lookup_cross_ids(self, provider_key: str, external_id: int) -> Dict[str, int]:
        return lookup_cross_ids(self._mapping, provider_key, external_id)
