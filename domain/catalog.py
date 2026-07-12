"""Domain types for catalogue identity and repair."""

from __future__ import annotations

from enum import Enum


class RepairStrategy(str, Enum):
    """How startup/catalog repair groups duplicate rows."""

    PROVIDER_ID = "provider_id"
    TITLE = "title"
    ALL = "all"
