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


def _make_schedule_light(KitsuIoWrapper):
    from adapters.persistence.models import Anime

    inst = object.__new__(KitsuIoWrapper)
    inst.s = MagicMock()
    inst.log = MagicMock()
    inst.schedule_light = True

    def _convert(raw):
        anime = Anime()
        anime._schedule_external_ids = {"kitsu_id": int(getattr(raw, "id", 0))}
        anime["title"] = "t"
        return anime

    inst._convertAnime = MagicMock(side_effect=_convert)
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
    assert [item["id"] for item in out] == [3, 4, 5, 1, 2]


def test_schedule_light_yields_rows_without_catalog_id(KitsuIoWrapper):
    inst = _make_schedule_light(KitsuIoWrapper)
    current_rows = [SimpleNamespace(id=11), SimpleNamespace(id=12)]

    def iterate(resource, modifier):
        if resource == "anime":
            return iter(current_rows)
        return iter(())

    inst.s.iterate.side_effect = iterate

    out = list(inst.schedule(limit=2))
    assert len(out) == 2
    assert getattr(out[0], "_schedule_external_ids", None) == {"kitsu_id": 11}
    assert getattr(out[1], "_schedule_external_ids", None) == {"kitsu_id": 12}


def test_schedule_respects_limit(KitsuIoWrapper):
    inst = _make(KitsuIoWrapper)
    inst.s.iterate.return_value = iter(
        SimpleNamespace(id=i) for i in range(1, 20)
    )

    out = list(inst.schedule(limit=3))
    assert len(out) == 3


def test_anime_pictures_returns_normalized_dicts(KitsuIoWrapper):
    from jsonapi_client.resourceobject import AttributeDict

    inst = object.__new__(KitsuIoWrapper)
    inst.s = MagicMock()
    inst.log = MagicMock()
    inst.getId = MagicMock(return_value=99)
    poster = AttributeDict(
        {
            "small": "http://example/s",
            "medium": "http://example/m",
            "large": "http://example/l",
        },
        resource=MagicMock(),
    )
    inst.s.get.return_value = SimpleNamespace(
        resources=[SimpleNamespace(posterImage=poster)]
    )

    out = KitsuIoWrapper.animePictures(inst, 2483)

    assert out == [
        {"url": "http://example/s", "size": "small"},
        {"url": "http://example/m", "size": "medium"},
        {"url": "http://example/l", "size": "large"},
    ]
    inst.getId.assert_called_once_with(2483)
