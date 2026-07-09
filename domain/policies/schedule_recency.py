"""Pure policies for filtering startup schedule rows by airing start date."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, TypeVar

from shared.contracts import AnimeRecord

_T = TypeVar("_T", bound=AnimeRecord)

_SECONDS_PER_DAY = 86_400


def schedule_recency_cutoff_ts(
    *,
    window_days: int = 90,
    now: datetime | None = None,
) -> int:
    """Return the earliest Unix timestamp that still qualifies as recent."""
    current = now or datetime.now(timezone.utc)
    return int(current.timestamp()) - int(window_days) * _SECONDS_PER_DAY


def is_recent_schedule_start(
    date_from: int | None,
    *,
    window_days: int = 90,
    now: datetime | None = None,
) -> bool:
    """True when ``date_from`` fell within the last ``window_days`` (inclusive)."""
    if date_from is None:
        return False
    current = now or datetime.now(timezone.utc)
    now_ts = int(current.timestamp())
    cutoff = schedule_recency_cutoff_ts(window_days=window_days, now=current)
    try:
        start = int(date_from)
    except (TypeError, ValueError):
        return False
    return cutoff <= start <= now_ts


def filter_recent_schedule_records(
    records: Sequence[_T],
    *,
    window_days: int = 90,
    limit: int,
    now: datetime | None = None,
) -> list[_T]:
    """Keep recent rows, newest ``date_from`` first, capped at ``limit``."""
    recent = [
        record
        for record in records
        if is_recent_schedule_start(
            record.date_from, window_days=window_days, now=now
        )
    ]
    recent.sort(key=lambda record: int(record.date_from or 0), reverse=True)
    return recent[: max(0, int(limit))]
