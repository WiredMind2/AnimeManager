"""Tests for JST broadcast schedule conversion."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.utils.broadcast_schedule import (
    BroadcastSlot,
    broadcast_slot_to_string,
    convert_jst_slot_to_local,
    format_broadcast_display,
    latest_episode_label,
    next_episode_datetime,
    parse_broadcast,
    utc_timestamp_to_jst_slot,
)

BERLIN_SUMMER = timezone(timedelta(hours=2))
NEW_YORK_SUMMER = timezone(timedelta(hours=-4))


def test_parse_broadcast_valid():
    assert parse_broadcast("0-9-0") == BroadcastSlot(weekday=0, hour=9, minute=0)


def test_parse_broadcast_invalid():
    assert parse_broadcast(None) is None
    assert parse_broadcast("bad") is None
    assert parse_broadcast("8-9-0") is None


def test_convert_jst_to_berlin_summer():
    slot = BroadcastSlot(weekday=0, hour=9, minute=0)
    local = convert_jst_slot_to_local(slot, BERLIN_SUMMER)
    assert local == BroadcastSlot(weekday=0, hour=2, minute=0)


def test_convert_jst_crosses_weekday():
    slot = BroadcastSlot(weekday=0, hour=1, minute=0)
    local = convert_jst_slot_to_local(slot, NEW_YORK_SUMMER)
    assert local.weekday == 6
    assert local.hour == 12
    assert local.minute == 0


def test_format_broadcast_display_includes_jst():
    slot = BroadcastSlot(weekday=0, hour=9, minute=0)
    text = format_broadcast_display(slot, BERLIN_SUMMER)
    assert text == "Mon 02:00 (Mon 09:00 JST)"


def test_next_episode_datetime_uses_jst_schedule():
    slot = BroadcastSlot(weekday=0, hour=9, minute=0)
    now = datetime(2026, 7, 6, 0, 0, tzinfo=timezone.utc)
    nxt = next_episode_datetime(slot, now=now, tz=BERLIN_SUMMER)
    assert nxt.tzinfo is not None
    assert nxt.weekday() == 0
    assert nxt.hour == 2


def test_latest_episode_label_same_day():
    slot = BroadcastSlot(weekday=0, hour=9, minute=0)
    now = datetime(2026, 7, 13, 10, 0, tzinfo=timezone(timedelta(hours=9)))
    assert latest_episode_label(slot, now=now, tz=timezone(timedelta(hours=9))) == "Today"


def test_utc_timestamp_to_jst_slot():
    ts = int(datetime(2026, 7, 6, 0, 0, tzinfo=timezone.utc).timestamp())
    slot = utc_timestamp_to_jst_slot(ts)
    assert broadcast_slot_to_string(slot) == "0-9-0"
