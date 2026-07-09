"""Broadcast schedule helpers — stored slots are Japan Standard Time (JST)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
_WEEKDAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True)
class BroadcastSlot:
    """Weekly airing slot stored as JST wall-clock time."""

    weekday: int  # 0=Monday .. 6=Sunday
    hour: int
    minute: int


def parse_broadcast(value: str | None) -> BroadcastSlot | None:
    """Parse a ``weekday-hour-minute`` broadcast string."""
    if not value:
        return None
    parts = str(value).strip().split("-")
    if len(parts) != 3:
        return None
    try:
        weekday, hour, minute = (int(part) for part in parts)
    except ValueError:
        return None
    if not 0 <= weekday <= 6:
        return None
    if not 0 <= hour <= 23:
        return None
    if not 0 <= minute <= 59:
        return None
    return BroadcastSlot(weekday=weekday, hour=hour, minute=minute)


def _resolve_tz(tz: timezone | None) -> timezone:
    if tz is not None:
        return tz
    local = datetime.now().astimezone().tzinfo
    if isinstance(local, timezone):
        return local
    return timezone.utc


def convert_jst_slot_to_local(
    slot: BroadcastSlot,
    tz: timezone | None = None,
    now: datetime | None = None,
) -> BroadcastSlot:
    """Convert a recurring JST slot to local wall-clock weekday/time."""
    tzinfo = _resolve_tz(tz)
    local_next = next_episode_datetime(slot, now=now, tz=tzinfo)
    return BroadcastSlot(
        weekday=local_next.weekday(),
        hour=local_next.hour,
        minute=local_next.minute,
    )


def format_slot_short(slot: BroadcastSlot) -> str:
    return f"{_WEEKDAY_SHORT[slot.weekday]} {slot.hour:02d}:{slot.minute:02d}"


def format_broadcast_jst(slot: BroadcastSlot) -> str:
    return f"{format_slot_short(slot)} JST"


def format_broadcast_display(
    slot: BroadcastSlot,
    tz: timezone | None = None,
    *,
    include_jst: bool = True,
    now: datetime | None = None,
) -> str:
    """Render a broadcast slot in local time, with optional JST annotation."""
    local = convert_jst_slot_to_local(slot, tz, now=now)
    local_text = format_slot_short(local)
    if not include_jst:
        return local_text
    jst_text = format_slot_short(slot)
    if local_text == jst_text:
        return local_text
    return f"{local_text} ({jst_text} JST)"


def next_episode_datetime(
    slot: BroadcastSlot,
    now: datetime | None = None,
    tz: timezone | None = None,
) -> datetime:
    """Return the next airing datetime in the requested timezone."""
    tzinfo = _resolve_tz(tz)
    now_jst = (now or datetime.now(timezone.utc)).astimezone(JST)

    days_ahead = (slot.weekday - now_jst.weekday()) % 7
    candidate = now_jst.replace(
        hour=slot.hour, minute=slot.minute, second=0, microsecond=0
    ) + timedelta(days=days_ahead)
    if candidate <= now_jst:
        candidate += timedelta(days=7)
    return candidate.astimezone(tzinfo)


def latest_episode_label(
    slot: BroadcastSlot,
    now: datetime | None = None,
    tz: timezone | None = None,
) -> str:
    """Return a relative label for the most recent weekly episode."""
    tzinfo = _resolve_tz(tz)
    now_local = (now or datetime.now(timezone.utc)).astimezone(tzinfo)
    last_local = next_episode_datetime(slot, now, tzinfo) - timedelta(days=7)
    days_since = (now_local.date() - last_local.date()).days

    if days_since == 0:
        return "Today"
    if days_since == 1:
        return "Yesterday"
    if days_since > 1:
        return f"{days_since} days ago"
    return "uhh?"


def utc_timestamp_to_jst_slot(timestamp: int) -> BroadcastSlot:
    """Convert a UTC unix timestamp into a recurring JST slot."""
    dt_jst = datetime.fromtimestamp(int(timestamp), timezone.utc).astimezone(JST)
    return BroadcastSlot(
        weekday=dt_jst.weekday(),
        hour=dt_jst.hour,
        minute=dt_jst.minute,
    )


def broadcast_slot_to_string(slot: BroadcastSlot) -> str:
    return f"{slot.weekday}-{slot.hour}-{slot.minute}"
