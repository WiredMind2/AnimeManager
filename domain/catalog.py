"""Domain types for catalogue identity and repair."""

from __future__ import annotations

from enum import Enum
from typing import Iterable


class RepairStrategy(str, Enum):
    """How startup/catalog repair groups duplicate rows."""

    PROVIDER_ID = "provider_id"
    TITLE = "title"
    ALL = "all"


def preferred_catalog_id(*ids: int) -> int:
    """Pick a canonical catalogue id: smallest positive, else smallest overall.

    Provisional schedule-light rows use negative fingerprints. When those
    collide with a real ``indexList`` id, the positive id must win.
    """
    if not ids:
        raise ValueError("preferred_catalog_id requires at least one id")
    positives = [int(i) for i in ids if int(i) > 0]
    if positives:
        return min(positives)
    return min(int(i) for i in ids)


def preferred_catalog_id_from(ids: Iterable[int]) -> int:
    """Like :func:`preferred_catalog_id` but accepts any iterable."""
    return preferred_catalog_id(*tuple(ids))
