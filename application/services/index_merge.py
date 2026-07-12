"""Backward-compatible shim — canonical implementation in catalog_repository."""

from __future__ import annotations

from domain.catalog import RepairStrategy
from ports.interfaces import CatalogMergePort


def merge_anime_index_rows(
    *,
    merge_repo: CatalogMergePort,
    duplicate_id: int,
    canonical_id: int,
) -> int:
    return merge_repo.merge(duplicate_id, canonical_id)


def repair_duplicate_index_entries(
    *,
    merge_repo: CatalogMergePort,
    strategy: RepairStrategy = RepairStrategy.PROVIDER_ID,
) -> int:
    return merge_repo.repair_duplicates(strategy=strategy)
