"""Unit tests for Kitsu schedule fallback behaviour."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def KitsuIoWrapper():
    from adapters.api.KitsuIo import KitsuIoWrapper as _W

    return _W


def _make(KitsuIoWrapper):
    inst = object.__new__(KitsuIoWrapper)
    inst.s = MagicMock()
    inst.log = MagicMock()
    inst._convertAnime = MagicMock(
        side_effect=lambda raw: {"id": int(getattr(raw, "id", 0)), "title": "t"}
    )
    return inst


def test_schedule_falls_back_to_season_when_status_filters_fail(KitsuIoWrapper):
    inst = _make(KitsuIoWrapper)

    trending = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    season_rows = [SimpleNamespace(id=3), SimpleNamespace(id=4), SimpleNamespace(id=5)]

    def iterate(resource, modifier):
        if resource == "trending/anime":
            return iter(trending)
        if resource == "anime" and "status" in str(modifier):
            from jsonapi_client import exceptions

            raise exceptions.DocumentError({"status_code": 500})
        if resource == "anime":
            return iter(season_rows)
        return iter(())

    inst.s.iterate.side_effect = iterate

    out = list(inst.schedule(limit=5))
    assert [item["id"] for item in out] == [1, 2, 3, 4, 5]


def test_schedule_respects_limit(KitsuIoWrapper):
    inst = _make(KitsuIoWrapper)
    inst.s.iterate.return_value = iter(
        SimpleNamespace(id=i) for i in range(1, 20)
    )

    out = list(inst.schedule(limit=3))
    assert len(out) == 3
