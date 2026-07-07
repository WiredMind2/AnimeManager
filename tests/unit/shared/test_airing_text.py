"""Tests for contextual airing line generation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.utils.airing_text import build_airing_lines


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


def test_build_airing_lines_finished_range():
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = datetime(2020, 3, 1, tzinfo=timezone.utc)
    lines = build_airing_lines(
        date_from=_ts(start),
        date_to=_ts(end),
        status="FINISHED",
    )
    assert len(lines) == 1
    assert "From 01 Jan 2020 to 01 Mar 2020" in lines[0]


def test_build_airing_lines_unknown_without_dates():
    assert build_airing_lines(status="AIRING", date_from=None) == []


def test_build_airing_lines_upcoming():
    future = datetime.now(timezone.utc) + timedelta(days=10)
    lines = build_airing_lines(
        date_from=_ts(future),
        status="UPCOMING",
    )
    assert len(lines) == 1
    assert "days left" in lines[0]


def test_build_airing_lines_airing_since():
    past = datetime.now(timezone.utc) - timedelta(days=30)
    lines = build_airing_lines(
        date_from=_ts(past),
        status="AIRING",
        broadcast=None,
    )
    assert any("Since" in line for line in lines)
