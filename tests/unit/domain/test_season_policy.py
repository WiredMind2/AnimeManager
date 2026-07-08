"""Tests for broadcast-season domain policies."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domain.errors import ValidationError
from domain.policies.season import (
    format_season_label,
    normalize_airing_season,
    season_date_range,
    validate_season_year,
)


def test_normalize_airing_season_accepts_known_values():
    assert normalize_airing_season("Spring") == "spring"
    assert normalize_airing_season(" FALL ") == "fall"


def test_normalize_airing_season_rejects_unknown():
    with pytest.raises(ValidationError):
        normalize_airing_season("autumn")


def test_validate_season_year_bounds():
    assert validate_season_year(2026) == 2026
    with pytest.raises(ValidationError):
        validate_season_year(1979)
    with pytest.raises(ValidationError):
        validate_season_year(datetime.now(timezone.utc).year + 6)


def test_season_date_range_spring():
    start_ts, end_ts = season_date_range(2026, "spring")
    start_dt = datetime.fromtimestamp(start_ts, timezone.utc)
    end_dt = datetime.fromtimestamp(end_ts, timezone.utc)
    assert start_dt.year == 2026 and start_dt.month == 4
    assert end_dt.year == 2026 and end_dt.month == 7


def test_season_date_range_fall_spans_year_boundary():
    start_ts, end_ts = season_date_range(2026, "fall")
    start_dt = datetime.fromtimestamp(start_ts, timezone.utc)
    end_dt = datetime.fromtimestamp(end_ts, timezone.utc)
    assert start_dt.month == 10
    assert end_dt.year == 2027 and end_dt.month == 1


def test_format_season_label():
    assert format_season_label("spring", 2026) == "Spring 2026"
