"""
Integration-style unit tests for the new APICoordinator wiring.

These tests exercise the coordinator's adapter + pipeline + sink flow
with in-memory fakes; they neither touch the network nor the DB.
"""

from __future__ import annotations

from types import SimpleNamespace

from ....application.services.api_coordinator import APICoordinator


class _FakeProvider:
    """Minimal stand-in for the legacy `AnimeAPI` wrappers."""

    def __init__(self, name, items=(), raises=False):
        self.__name__ = name
        self._items = items
        self._raises = raises

    def searchAnime(self, terms, limit=50):
        if self._raises:
            raise RuntimeError(f"{self.__name__} explosion")
        for item in self._items[:limit]:
            yield item


class _FakeAPI:
    def __init__(self, providers):
        self._providers = providers

    def get_providers(self):
        return list(self._providers)


class _RecordingDBManager:
    def __init__(self):
        self.upserts = []

    def upsert_anime_batch(self, records):
        self.upserts.append(list(records))
        return len(records)


def _build_coordinator(api, db):
    coord = APICoordinator(max_workers=2, provider_timeout_s=2.0)
    coord.set_api(api)
    coord.set_database_manager(db)
    coord.log = lambda *args, **kwargs: None
    return coord


def _anime_like(rid, title="t"):
    return SimpleNamespace(
        id=rid,
        title=title,
        synopsis=None,
        episodes=None,
        duration=None,
        status=None,
        rating=None,
        date_from=None,
        date_to=None,
        picture=None,
        trailer=None,
        broadcast=None,
    )


def test_full_search_flow_persists_dedup():
    api = _FakeAPI(
        [
            _FakeProvider("A", [_anime_like(1), _anime_like(2)]),
            _FakeProvider("B", [_anime_like(2), _anime_like(3)]),
        ]
    )
    db = _RecordingDBManager()
    coord = _build_coordinator(api, db)
    try:
        results = coord._perform_api_search("term", 10)
    finally:
        coord.close()

    assert results is not None
    ids = sorted(a.id for a in results)
    assert ids == [1, 2, 3]
    # DB sink received exactly the deduped batch.
    assert len(db.upserts) == 1
    assert sorted(a.id for a in db.upserts[0]) == [1, 2, 3]


def test_partial_failure_still_persists_good_results():
    api = _FakeAPI(
        [
            _FakeProvider("A", [_anime_like(1)]),
            _FakeProvider("B", raises=True),
        ]
    )
    db = _RecordingDBManager()
    coord = _build_coordinator(api, db)
    try:
        results = coord._perform_api_search("term", 10)
    finally:
        coord.close()

    assert results is not None
    assert [a.id for a in results] == [1]
    assert sum(len(b) for b in db.upserts) == 1


def test_persistence_disabled_via_flag():
    api = _FakeAPI([_FakeProvider("A", [_anime_like(1)])])
    db = _RecordingDBManager()
    coord = _build_coordinator(api, db)
    coord.configure({"db_gateway_writes_only": False})
    try:
        results = coord._perform_api_search("term", 10)
    finally:
        coord.close()

    assert results is not None
    assert [a.id for a in results] == [1]
    # Persistence sink must not have been called.
    assert db.upserts == []


def test_falls_back_to_legacy_search_when_flag_disabled():
    legacy = SimpleNamespace(
        searchAnime=lambda terms, limit=50: ["legacy-result"],
    )
    coord = APICoordinator()
    coord.log = lambda *args, **kwargs: None
    coord.set_api(legacy)
    coord.configure({"new_ingestion_pipeline": False})

    try:
        out = coord._perform_api_search("term", 10)
    finally:
        coord.close()
    assert out == ["legacy-result"]


def test_close_is_idempotent():
    coord = APICoordinator()
    coord.log = lambda *args, **kwargs: None
    coord.close()
    coord.close()  # second call must not raise
