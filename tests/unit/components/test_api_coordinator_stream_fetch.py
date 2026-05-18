"""Streaming search and schedule-fetch tests for :class:`APICoordinator`."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.services.api_coordinator import APICoordinator
from shared.contracts import AnimeRecord, IngestionStatus


class _FakeProvider:
    def __init__(self, name, items=(), schedule_items=(), schedule_raises=False):
        self.__name__ = name
        self._items = list(items)
        self._schedule_items = list(schedule_items)
        self._schedule_raises = schedule_raises

    def searchAnime(self, terms, limit=50):
        for item in self._items[:limit]:
            yield item

    def schedule(self, limit=50):
        if self._schedule_raises and isinstance(limit, int) is False:
            raise TypeError("bad signature")
        return list(self._schedule_items[: int(limit)])


class _IterableResult:
    def __init__(self, items):
        self._items = list(items)

    def __iter__(self):
        return iter(self._items)


class _FakeAPI:
    def __init__(self, providers, legacy_items=()):
        self._providers = providers
        self._legacy_items = list(legacy_items)

    def get_providers(self):
        return list(self._providers)

    def searchAnime(self, terms, limit=50):
        return _IterableResult(self._legacy_items[:limit])


class _RecordingDB:
    def __init__(self):
        self.upserts: list[list] = []

    def upsert_anime_batch(self, records):
        self.upserts.append(list(records))
        return len(records)


def _record(rid: int, title: str = "t") -> AnimeRecord:
    return AnimeRecord(id=rid, title=title)


def _coord(api, db=None, **flags):
    c = APICoordinator(max_workers=2, provider_timeout_s=2.0)
    c.log = lambda *_a, **_kw: None
    c.set_api(api)
    if db is not None:
        c.set_database_manager(db)
    if flags:
        c.configure(flags)
    return c


def test_stream_search_yields_pipeline_batches():
    api = _FakeAPI(
        [
            _FakeProvider("A", [_record(1)]),
            _FakeProvider("B", [_record(2)]),
        ]
    )
    db = _RecordingDB()
    coord = _coord(api, db)
    try:
        ids = [a.id for a in coord.stream_search_anime("naruto", limit=10)]
    finally:
        coord.close()
    assert sorted(ids) == [1, 2]
    assert len(db.upserts) == 1


def test_stream_search_legacy_fallback_when_pipeline_disabled():
    legacy = SimpleNamespace(id=5, title="Legacy")
    api = _FakeAPI([], legacy_items=[legacy])
    coord = _coord(api, _RecordingDB(), new_ingestion_pipeline=False)
    try:
        out = list(coord.stream_search_anime("naruto", limit=5))
    finally:
        coord.close()
    assert len(out) == 1
    assert out[0].id == 5


def test_stream_search_short_terms_yields_nothing():
    api = _FakeAPI([_FakeProvider("A", [_record(1)])])
    coord = _coord(api)
    try:
        assert list(coord.stream_search_anime("ab")) == []
    finally:
        coord.close()


def test_stream_search_without_api_is_empty():
    coord = APICoordinator()
    coord.log = lambda *_a, **_kw: None
    try:
        assert list(coord.stream_search_anime("naruto")) == []
    finally:
        coord.close()


def test_fetch_latest_runs_schedule_providers():
    api = _FakeAPI(
        [
            _FakeProvider("Sched", schedule_items=[_record(10), _record(11)]),
            _FakeProvider("NoSched"),
        ]
    )
    db = _RecordingDB()
    coord = _coord(api, db)
    try:
        result = coord.fetch_latest(limit=5)
    finally:
        coord.close()
    assert result is not None
    assert result.status in (IngestionStatus.COMPLETE, IngestionStatus.PARTIAL)
    assert len(result.records) == 2
    assert len(db.upserts) == 1


def test_fetch_latest_schedule_typeerror_fallback():
    class _LegacyScheduleProvider:
        __name__ = "LegacySched"

        def schedule(self, lim):
            _ = lim
            return [_record(3)]

    api = _FakeAPI([_LegacyScheduleProvider()])
    coord = _coord(api, _RecordingDB())
    try:
        result = coord.fetch_latest(limit=1)
    finally:
        coord.close()
    assert result is not None
    assert len(result.records) == 1


class _SearchOnlyProvider:
    __name__ = "SearchOnly"

    def searchAnime(self, terms, limit=50):
        yield from ()


def test_fetch_latest_returns_none_without_schedule_providers():
    api = _FakeAPI([_SearchOnlyProvider()])
    coord = _coord(api, _RecordingDB())
    try:
        assert coord.fetch_latest() is None
    finally:
        coord.close()
