"""Pure policies for top-by-popularity browse categories.

Add a new category by appending to ``TOP_CATEGORY_SPECS`` (and mapping it
in each provider's ``top()``). Validation, labels, and local status seeds
all derive from that registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class TopCategorySpec:
    """Descriptor for one top-browse category."""

    key: str
    label: str
    local_status: Optional[str] = None


# Ordered registry — UI tabs follow this order.
TOP_CATEGORY_SPECS: tuple[TopCategorySpec, ...] = (
    TopCategorySpec(key="all", label="All"),
    TopCategorySpec(key="airing", label="Airing", local_status="AIRING"),
    TopCategorySpec(key="upcoming", label="Upcoming", local_status="UPCOMING"),
)

TOP_CATEGORIES: frozenset[str] = frozenset(spec.key for spec in TOP_CATEGORY_SPECS)

_TOP_LOOKUP: dict[str, TopCategorySpec] = {
    spec.key: spec for spec in TOP_CATEGORY_SPECS
}


def normalize_top_category(value: str) -> str:
    """Return a canonical top-category key or raise ``ValidationError``."""
    normalized = (value or "").strip().lower()
    if normalized not in _TOP_LOOKUP:
        allowed = ", ".join(spec.key for spec in TOP_CATEGORY_SPECS)
        raise ValidationError(f"Top category must be one of: {allowed}.")
    return normalized


def top_category_spec(value: str) -> TopCategorySpec:
    """Return the registry entry for a validated category key."""
    return _TOP_LOOKUP[normalize_top_category(value)]


def local_status_for(category: str) -> Optional[str]:
    """Local catalog status seed for a category, or ``None`` if provider-only."""
    return top_category_spec(category).local_status


def format_top_label(category: str) -> str:
    """Human label such as ``Airing`` or ``All``."""
    return top_category_spec(category).label
