"""Edge-case unit tests for :mod:`adapters.api.KitsuIo` (no network)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests


@pytest.fixture
def KitsuIoWrapper():
    from adapters.api.KitsuIo import KitsuIoWrapper as _W

    return _W


def _make(KitsuIoWrapper):
    inst = object.__new__(KitsuIoWrapper)
    inst.apiKey = "kitsu_id"
    inst.subtypes = ("TV", "movie")
    inst.s = MagicMock()
    inst.database = MagicMock()
    inst.database.get_lock.return_value.__enter__ = MagicMock(return_value=None)
    inst.database.get_lock.return_value.__exit__ = MagicMock(return_value=False)
    inst.database.getId.return_value = 42
    inst.getId = MagicMock(return_value=99)
    inst.log = MagicMock()
    inst._convertAnime = MagicMock(return_value={"id": 42, "title": "Test"})
    inst._convertCharacter = MagicMock(return_value={"id": 7})
    return inst


class TestAnime:
    def test_anime_returns_empty_when_no_kitsu_id(self, KitsuIoWrapper):
        w = _make(KitsuIoWrapper)
        w.getId.return_value = None
        assert w.anime(1) == {}
        w.s.get.assert_not_called()

    def test_anime_happy_path(self, KitsuIoWrapper):
        w = _make(KitsuIoWrapper)
        resource = MagicMock()
        w.s.get.return_value.resource = resource
        out = w.anime(1)
        assert out == {"id": 42, "title": "Test"}
        w._convertAnime.assert_called_once_with(resource, force=True)


class TestErrorWrapper:
    def test_connection_error_returns_none(self, KitsuIoWrapper):
        w = _make(KitsuIoWrapper)
        w.getId.return_value = 99
        w.s.get.side_effect = requests.exceptions.ConnectionError("offline")
        assert w.anime(1) is None
        w.log.assert_called()

    def test_read_timeout_returns_none(self, KitsuIoWrapper):
        w = _make(KitsuIoWrapper)
        w.getId.return_value = 99
        w.s.get.side_effect = requests.exceptions.ReadTimeout("slow")
        assert w.anime(1) is None


class TestSearchAnime:
    def test_search_yields_converted_rows(self, KitsuIoWrapper):
        w = _make(KitsuIoWrapper)
        a1, a2 = MagicMock(), MagicMock()
        w.s.iterate.return_value = iter([a1, a2])
        rows = list(w.searchAnime("naruto", limit=5))
        assert len(rows) == 2
        assert rows[0]["title"] == "Test"
