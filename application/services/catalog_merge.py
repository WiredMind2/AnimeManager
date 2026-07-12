"""Application service for catalogue row consolidation."""

from __future__ import annotations

from domain.catalog import RepairStrategy
from ports.interfaces import CatalogMergePort


class CatalogMergeService:
    """Fold duplicate internal ids; used during identity resolution and startup repair."""

    def __init__(self, merge_repo: CatalogMergePort) -> None:
        self._repo = merge_repo

    def merge(self, duplicate_id: int, canonical_id: int) -> int:
        return self._repo.merge(duplicate_id, canonical_id)

    def repair_duplicates(
        self, *, strategy: RepairStrategy = RepairStrategy.PROVIDER_ID
    ) -> int:
        return self._repo.repair_duplicates(strategy=strategy)
