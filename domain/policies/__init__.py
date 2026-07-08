"""Pure domain policies extracted from legacy helper modules.

This module is the canonical home of these pure functions. The legacy
``backend.domain.policies`` module is a thin compatibility shim that
re-exports from here.
"""

from __future__ import annotations

from datetime import datetime, timezone


def derive_status(
    status: str | None,
    date_from: int | None,
    date_to: int | None,
    episodes: int | None,
) -> str:
    """Compute canonical status without touching infrastructure or UI state."""
    if status:
        return "UNKNOWN" if status == "UPDATE" else status

    if date_from is None:
        return "UNKNOWN"

    now = datetime.now(timezone.utc)
    starts_at = datetime.fromtimestamp(date_from, timezone.utc)
    if starts_at > now:
        return "UPCOMING"

    if date_to is None:
        if episodes == 1:
            return "FINISHED"
        return "AIRING"

    ends_at = datetime.fromtimestamp(date_to, timezone.utc)
    return "FINISHED" if ends_at <= now else "AIRING"


def normalize_search_query(query: str) -> str:
    """Normalize search terms to deterministic DB/API-safe input."""
    if not query:
        return ""
    cleaned = "".join(c if (c.isalnum() or c == " ") else " " for c in query)
    return " ".join(cleaned.split()).strip()


from domain.policies.genre import (  # noqa: E402
    GENRES,
    format_genre_label,
    normalize_genre,
)
from domain.policies.season import (  # noqa: E402
    AIRING_SEASONS,
    format_season_label,
    normalize_airing_season,
    season_date_range,
    validate_season_year,
)

__all__ = [
    "AIRING_SEASONS",
    "GENRES",
    "derive_status",
    "format_genre_label",
    "format_season_label",
    "normalize_airing_season",
    "normalize_genre",
    "normalize_search_query",
    "season_date_range",
    "validate_season_year",
]
