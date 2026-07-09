"""Unit tests for schedule recency filtering."""

from __future__ import annotations

from datetime import datetime, timezone

from shared.contracts import AnimeRecord, ProviderName

from domain.policies.schedule_recency import (
    filter_recent_schedule_records,
    is_recent_schedule_start,
    schedule_recency_cutoff_ts,
)


def _record(rid: int, date_from: int | None) -> AnimeRecord:
    return AnimeRecord(
        id=rid,
        title=f"anime-{rid}",
        date_from=date_from,
        source_provider=ProviderName.UNKNOWN,
    )


def test_schedule_recency_cutoff_ts_uses_window_days():
    now = datetime(2026, 7, 8, tzinfo=timezone.utc)
    cutoff = schedule_recency_cutoff_ts(window_days=90, now=now)
    assert cutoff == int(now.timestamp()) - 90 * 86_400


def test_is_recent_schedule_start_accepts_in_window():
    now = datetime(2026, 7, 8, tzinfo=timezone.utc)
    recent = int(now.timestamp()) - 10 * 86_400
    assert is_recent_schedule_start(recent, window_days=90, now=now) is True


def test_is_recent_schedule_start_rejects_old_and_future():
    now = datetime(2026, 7, 8, tzinfo=timezone.utc)
    old = int(now.timestamp()) - 120 * 86_400
    future = int(now.timestamp()) + 10 * 86_400
    assert is_recent_schedule_start(old, window_days=90, now=now) is False
    assert is_recent_schedule_start(future, window_days=90, now=now) is False
    assert is_recent_schedule_start(None, window_days=90, now=now) is False


def test_filter_recent_schedule_records_sorts_newest_first_and_caps():
    now = datetime(2026, 7, 8, tzinfo=timezone.utc)
    records = [
        _record(1, int(now.timestamp()) - 5 * 86_400),
        _record(2, int(now.timestamp()) - 40 * 86_400),
        _record(3, int(now.timestamp()) - 200 * 86_400),
        _record(4, int(now.timestamp()) - 1 * 86_400),
    ]
    filtered = filter_recent_schedule_records(
        records, window_days=90, limit=2, now=now
    )
    assert [record.id for record in filtered] == [4, 1]
