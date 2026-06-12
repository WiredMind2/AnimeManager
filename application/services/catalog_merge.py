"""Application service for catalogue row consolidation."""

from __future__ import annotations

from typing import Any, Callable, Optional

from adapters.persistence.catalog_repository import CatalogMergeRepository
from shared.contracts import RepairStrategy


class CatalogMergeService:
    """Fold duplicate internal ids; used during identity resolution and startup repair."""

    def __init__(
        self,
        db: Any,
        *,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._repo = CatalogMergeRepository(db, log_fn=log_fn)

    def merge(self, duplicate_id: int, canonical_id: int) -> int:
        return self._repo.merge(duplicate_id, canonical_id)

    def repair_duplicates(
        self, *, strategy: RepairStrategy = RepairStrategy.PROVIDER_ID
    ) -> int:
        return self._repo.repair_duplicates(strategy=strategy)
