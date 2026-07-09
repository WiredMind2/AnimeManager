"""Tests for ``adapters.metadata.anime_hydration_adapter``."""

from __future__ import annotations

from types import SimpleNamespace

from adapters.metadata.anime_hydration_adapter import AnimeHydrationAdapter


class _DB:
    def __init__(self, rows=None):
        self.rows = rows or {(1,): [(1,)]}

    def sql(self, _query, params):
        return self.rows.get(tuple(params), [])


class _API:
    def __init__(self, result=None, *, raises=False):
        self.result = result
        self.raises = raises
        self.calls = []

    def anime(self, catalog_id, _persist=False):
        self.calls.append((catalog_id, _persist))
        if self.raises:
            raise RuntimeError("api boom")
        return self.result


class _WriteService:
    def __init__(self, *, persisted=True):
        self.persisted = persisted
        self.calls = []

    def persist_legacy_anime(self, anime, *, source, catalog_id=None):
        self.calls.append((anime, source, catalog_id))
        return self.persisted


def test_catalog_id_exists_uses_indexlist_lookup():
    adapter = AnimeHydrationAdapter(_API(), _DB(rows={(7,): [(1,)]}))
    assert adapter.catalog_id_exists(7) is True
    assert adapter.catalog_id_exists(8) is False


def test_hydrate_fetches_without_implicit_persist():
    api = _API(result=SimpleNamespace(title="Naruto"))
    write = _WriteService(persisted=True)
    adapter = AnimeHydrationAdapter(api, _DB(), write_service=write)

    assert adapter.hydrate_anime(10) is True
    assert api.calls == [(10, False)]
    assert len(write.calls) == 1
    assert write.calls[0][2] == 10


def test_hydrate_returns_false_when_title_missing():
    api = _API(result=SimpleNamespace(title=""))
    adapter = AnimeHydrationAdapter(api, _DB(), write_service=_WriteService())
    assert adapter.hydrate_anime(10) is False


def test_hydrate_returns_false_when_write_gateway_fails():
    api = _API(result={"title": "Bleach"})
    write = _WriteService(persisted=False)
    adapter = AnimeHydrationAdapter(api, _DB(), write_service=write)
    assert adapter.hydrate_anime(11) is False


def test_hydrate_without_write_service_keeps_legacy_success_signal():
    api = _API(result={"title": "One Piece"})
    adapter = AnimeHydrationAdapter(api, _DB())
    assert adapter.hydrate_anime(12) is True


def test_hydrate_handles_api_error():
    api = _API(raises=True)
    adapter = AnimeHydrationAdapter(api, _DB())
    assert adapter.hydrate_anime(13) is False
