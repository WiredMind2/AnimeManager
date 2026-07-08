"""Pure policies for broadcast-season (airing quarter) browse."""

from __future__ import annotations

from datetime import date, datetime, timezone

from domain.errors import ValidationError

AIRING_SEASONS: frozenset[str] = frozenset({"winter", "spring", "summer", "fall"})

_SEASON_START_MONTH: dict[str, int] = {
    "winter": 1,
    "spring": 4,
    "summer": 7,
    "fall": 10,
}

_MIN_YEAR = 1980


def normalize_airing_season(season: str) -> str:
    """Return a lowercase airing-season token or raise ``ValidationError``."""
    normalized = (season or "").strip().lower()
    if normalized not in AIRING_SEASONS:
        allowed = ", ".join(sorted(AIRING_SEASONS))
        raise ValidationError(f"Season must be one of: {allowed}.")
    return normalized


def validate_season_year(year: int) -> int:
    """Validate and return the airing year as an integer."""
    try:
        value = int(year)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Year must be a valid integer.") from exc
    max_year = date.today().year + 5
    if value < _MIN_YEAR or value > max_year:
        raise ValidationError(
            f"Year must be between {_MIN_YEAR} and {max_year}."
        )
    return value


def season_date_range(year: int, season: str) -> tuple[int, int]:
    """Return inclusive ``date_from`` range ``(start_ts, end_ts)`` for a season.

    ``end_ts`` is the first instant of the next calendar season (exclusive
    upper bound), matching anime airing-quarter conventions.
    """
    season_key = normalize_airing_season(season)
    year_value = validate_season_year(year)
    start_month = _SEASON_START_MONTH[season_key]
    start_dt = datetime(year_value, start_month, 1, tzinfo=timezone.utc)
    if season_key == "winter":
        end_dt = datetime(year_value, 4, 1, tzinfo=timezone.utc)
    elif season_key == "spring":
        end_dt = datetime(year_value, 7, 1, tzinfo=timezone.utc)
    elif season_key == "summer":
        end_dt = datetime(year_value, 10, 1, tzinfo=timezone.utc)
    else:
        end_dt = datetime(year_value + 1, 1, 1, tzinfo=timezone.utc)
    return int(start_dt.timestamp()), int(end_dt.timestamp())


def format_season_label(season: str, year: int) -> str:
    """Human label such as ``Spring 2026``."""
    season_key = normalize_airing_season(season)
    year_value = validate_season_year(year)
    return f"{season_key.capitalize()} {year_value}"
