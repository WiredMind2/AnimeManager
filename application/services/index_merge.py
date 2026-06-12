"""Backward-compatible shim — canonical implementation in catalog_repository."""

from __future__ import annotations

from typing import Any

from adapters.persistence.catalog_repository import CatalogMergeRepository
from shared.contracts import RepairStrategy


def merge_anime_index_rows(
    db: Any,
    *,
    duplicate_id: int,
    canonical_id: int,
) -> int:
    return CatalogMergeRepository(db).merge(duplicate_id, canonical_id)


def repair_duplicate_index_entries(
    db: Any,
    *,
    strategy: RepairStrategy = RepairStrategy.PROVIDER_ID,
) -> int:
    return CatalogMergeRepository(db).repair_duplicates(strategy=strategy)
