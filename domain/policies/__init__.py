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
    GENRE_ORDER,
    format_genre_label,
    genres_contain_all,
    normalize_genre,
    normalize_genres,
)
from domain.policies.adult_content import is_adult_torrent  # noqa: E402
from domain.policies.anime_metadata import is_anime_metadata_missing  # noqa: E402
from domain.policies.schedule_recency import (  # noqa: E402
    filter_recent_schedule_records,
    is_recent_schedule_start,
    schedule_recency_cutoff_ts,
)
from domain.policies.season import (  # noqa: E402
    AIRING_SEASONS,
    format_season_label,
    normalize_airing_season,
    season_date_range,
    validate_season_year,
)
from domain.policies.top import (  # noqa: E402
    TOP_CATEGORIES,
    TOP_CATEGORY_SPECS,
    format_top_label,
    local_status_for,
    normalize_top_category,
    top_category_spec,
)

__all__ = [
    "AIRING_SEASONS",
    "GENRES",
    "GENRE_ORDER",
    "TOP_CATEGORIES",
    "TOP_CATEGORY_SPECS",
    "derive_status",
    "filter_recent_schedule_records",
    "format_genre_label",
    "format_season_label",
    "format_top_label",
    "genres_contain_all",
    "is_adult_torrent",
    "is_anime_metadata_missing",
    "is_recent_schedule_start",
    "local_status_for",
    "normalize_airing_season",
    "normalize_genre",
    "normalize_genres",
    "normalize_search_query",
    "normalize_top_category",
    "schedule_recency_cutoff_ts",
    "season_date_range",
    "top_category_spec",
    "validate_season_year",
]
