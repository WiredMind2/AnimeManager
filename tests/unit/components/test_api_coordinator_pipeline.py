"""
Integration-style unit tests for the new APICoordinator wiring.

These tests exercise the coordinator's adapter + pipeline + sink flow
with in-memory fakes; they neither touch the network nor the DB.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

from ....application.services.api_coordinator import APICoordinator
from ....adapters.persistence.models import Anime


class _FakeProvider:
    """Minimal stand-in for the legacy `AnimeAPI` wrappers."""

    def __init__(
        self,
        name,
        items=(),
        raises=False,
        schedule_items=(),
        season_items=(),
    ):
        self.__name__ = name
        self._items = items
        self._raises = raises
        self._schedule_items = schedule_items
        self._season_items = season_items
        self.last_schedule_limit = None
        self.last_season_args = None

    def searchAnime(self, terms, limit=50):
        if self._raises:
            raise RuntimeError(f"{self.__name__} explosion")
        for item in self._items[:limit]:
            yield item

    def schedule(self, limit=50):
        self.last_schedule_limit = limit
        if self._raises:
            raise RuntimeError(f"{self.__name__} schedule explosion")
        for item in self._schedule_items[:limit]:
            yield item

    def season(self, year, season, limit=50):
        self.last_season_args = (year, season, limit)
        if self._raises:
            raise RuntimeError(f"{self.__name__} season explosion")
        for item in self._season_items[:limit]:
            yield item


class _FakeAPI:
    def __init__(self, providers, settings=None):
        self._providers = providers
        self.settings = settings or {"anime": {"scheduleRecencyDays": 90}}

    def get_providers(self):
        return list(self._providers)


class _RecordingDBManager:
    def __init__(self):
        self.upserts = []
        self.enrich_calls = []

    def get_database(self):
        return None

    def upsert_anime_batch(self, records):
        self.upserts.append(list(records))
        return len(records)

    def enrich_catalog_identities_for_ids(self, catalog_ids):
        self.enrich_calls.append(list(catalog_ids))
        return SimpleNamespace(looked_up=len(catalog_ids), enriched=0, merged=0)


class _MalIdentity:
    """Resolve ``mal_id`` (or first external id) to the same catalogue id."""

    def resolve_external_ids_batch(self, entries):
        out = []
        for entry in entries:
            catalog_id = entry.get("mal_id")
            if catalog_id is None and entry:
                catalog_id = next(iter(entry.values()))
            out.append(
                SimpleNamespace(
                    catalog_id=int(catalog_id),
                    external_ids=dict(entry),
                )
            )
        return out


def _build_coordinator(api, db, *, identity=None):
    coord = APICoordinator(max_workers=2, provider_timeout_s=2.0)
    coord.set_api(api)
    coord.set_database_manager(db)
    coord.log = lambda *args, **kwargs: None
    if identity is not None:
        coord._catalog_identity = identity
    else:
        coord._catalog_identity = _MalIdentity()
    return coord


def _anime_like(rid, title="t", date_from=None, title_synonyms=None):
    return SimpleNamespace(
        id=rid,
        title=title,
        synopsis=None,
        episodes=None,
        duration=None,
        status=None,
        rating=None,
        date_from=date_from,
        date_to=None,
        picture=None,
        trailer=None,
        broadcast=None,
        title_synonyms=title_synonyms or (title, f"{title} Alt"),
        _schedule_external_ids={"mal_id": int(rid)},
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
    assert db.enrich_calls == [[1, 2, 3]]


def test_full_search_flow_persists_title_synonyms():
    api = _FakeAPI([_FakeProvider("A", [_anime_like(1, title="Primary")])])
    db = _RecordingDBManager()
    coord = _build_coordinator(api, db)
    try:
        coord._perform_api_search("term", 10)
    finally:
        coord.close()

    assert len(db.upserts) == 1
    upserted = db.upserts[0][0]
    _data, meta = upserted.save_format()
    assert meta["title_synonyms"] == ["Primary", "Primary Alt"]


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


def test_fetch_latest_splits_total_limit_across_providers():
    now = int(time.time())
    providers = [
        _FakeProvider(
            "A",
            schedule_items=[
                _anime_like(i, date_from=now - i * 86_400) for i in range(1, 9)
            ],
        ),
        _FakeProvider(
            "B",
            schedule_items=[
                _anime_like(i, date_from=now - i * 86_400) for i in range(9, 17)
            ],
        ),
    ]
    api = _FakeAPI(providers)
    db = _RecordingDBManager()
    coord = _build_coordinator(api, db)
    try:
        result = coord.fetch_latest(limit=8, per_provider=False)
    finally:
        coord.close()

    assert result is not None
    assert providers[0].last_schedule_limit == 12
    assert providers[1].last_schedule_limit == 12
    assert len(result.records) == 8
    assert result.persisted_count == 8


def test_fetch_latest_resolves_schedule_external_ids_in_batch():
    def _schedule_like(anilist_id, mal_id=None, title="t"):
        ext = {"anilist_id": anilist_id}
        if mal_id is not None:
            ext["mal_id"] = mal_id
        return SimpleNamespace(
            _schedule_external_ids=ext,
            title=title,
            synopsis=None,
            episodes=None,
            duration=None,
            status="AIRING",
            rating=None,
            date_from=int(time.time()) - 5 * 86_400,
            date_to=None,
            picture=None,
            trailer=None,
            broadcast=None,
            title_synonyms=(),
        )

    class _Identity:
        def resolve_external_ids_batch(self, entries):
            out = []
            for idx, entry in enumerate(entries, start=100):
                out.append(
                    SimpleNamespace(
                        catalog_id=idx,
                        external_ids=dict(entry),
                    )
                )
            return out

    providers = [
        _FakeProvider(
            "AnilistCo",
            schedule_items=[_schedule_like(11, mal_id=22), _schedule_like(33)],
        ),
    ]
    api = _FakeAPI(providers)
    db = _RecordingDBManager()
    coord = _build_coordinator(api, db)
    coord._catalog_identity = _Identity()
    try:
        result = coord.fetch_latest(limit=4, per_provider=False)
    finally:
        coord.close()

    assert result is not None
    assert sorted(r.id for r in result.records) == [100, 101]
    assert db.upserts and sorted(a.id for a in db.upserts[0]) == [100, 101]


def test_schedule_light_anime_retains_external_ids_for_adapter():
    """Real Anime objects must keep _schedule_external_ids through __setattr__."""
    from shared.contracts import ProviderAnimePayload

    anime = Anime()
    external_ids = {"mal_id": 123}
    anime._schedule_external_ids = external_ids
    assert getattr(anime, "_schedule_external_ids", None) == external_ids

    coord = _build_coordinator(_FakeAPI([]), _RecordingDBManager())
    try:
        payload = coord.project_provider_raw(anime, provider_name="JikanMoeWrapper")
    finally:
        coord.close()

    assert payload is not None
    assert isinstance(payload, ProviderAnimePayload)
    assert payload.external_ids == external_ids
    assert payload.title == ""


def test_project_provider_raw_resolves_catalog_id_via_identity():
    """Batch identity assignment should map schedule externals to catalogue ids."""
    from adapters.persistence.catalog_repository import CatalogIndexRepository
    from application.services.catalog_identity import CatalogIdentityService
    from tests.unit.application.test_catalog_enrichment import _EnrichmentDB

    db = _EnrichmentDB()
    identity = CatalogIdentityService.from_database(db)

    class _DBManager:
        def __init__(self):
            self._mapping_port = None
            self.upserts = []
            self.enrich_calls = []

        def get_database(self):
            return db

        def upsert_anime_batch(self, records):
            self.upserts.append(list(records))
            return len(records)

        def enrich_catalog_identities_for_ids(self, catalog_ids):
            self.enrich_calls.append(list(catalog_ids))
            return SimpleNamespace(looked_up=len(catalog_ids), enriched=0, merged=0)

    anime = Anime()
    anime.title = "Higehiro"
    anime._schedule_external_ids = {"mal_id": 40938}

    coord = _build_coordinator(_FakeAPI([]), _DBManager(), identity=identity)
    try:
        payload = coord.project_provider_raw(anime, provider_name="JikanMoeWrapper")
        records = coord._assign_payloads_to_records([payload])
    finally:
        coord.close()

    assert payload is not None
    assert len(records) == 1
    assert records[0].id > 0
    assert records[0].external_ids.get("mal_id") == 40938
    assert CatalogIndexRepository(db).get_external_ids(records[0].id)["mal_id"] == 40938


def test_finalize_catalog_records_drops_unresolved_provisional():
    from shared.contracts import ProviderAnimePayload, ProviderName

    coord = _build_coordinator(_FakeAPI([]), _RecordingDBManager())
    coord._catalog_identity = None
    try:
        # No identity service → payloads cannot resolve → dropped.
        out = coord._finalize_catalog_records(
            [
                ProviderAnimePayload(
                    title="Ghost",
                    external_ids={"mal_id": 1},
                    source_provider=ProviderName.JIKAN,
                ),
                ProviderAnimePayload(
                    title="Real",
                    external_ids={"mal_id": 2},
                    source_provider=ProviderName.JIKAN,
                ),
            ]
        )
    finally:
        coord.close()

    assert out == []


def test_fetch_latest_merges_cross_provider_schedule_rows():
    """Same show from Kitsu and MAL should resolve to one catalogue id."""
    from adapters.persistence.catalog_repository import (
        CatalogIndexRepository,
        CatalogMergeRepository,
        _batched_writes,
    )
    from application.services.catalog_identity import CatalogIdentityService
    from application.services.catalog_merge import CatalogMergeService
    from tests.unit.application.test_catalog_enrichment import _EnrichmentDB, _FakeMappingPort

    class _MappingDBManager:
        def __init__(self, db):
            self._db = db
            self._mapping_port = _FakeMappingPort()
            self.upserts = []
            self.enrich_calls = []

        def get_database(self):
            return self._db

        def upsert_anime_batch(self, records):
            self.upserts.append(list(records))
            return len(records)

        def enrich_catalog_identities_for_ids(self, catalog_ids):
            self.enrich_calls.append(list(catalog_ids))
            return SimpleNamespace(looked_up=0, enriched=0, merged=0)

    def _schedule_like(external_ids, title="t"):
        return SimpleNamespace(
            _schedule_external_ids=external_ids,
            title=title,
            synopsis=None,
            episodes=None,
            duration=None,
            status="AIRING",
            rating=None,
            date_from=int(time.time()) - 5 * 86_400,
            date_to=None,
            picture=None,
            trailer=None,
            broadcast=None,
            title_synonyms=(),
        )

    db = _EnrichmentDB()
    db.index[1] = {
        "id": 1,
        "mal_id": 46488,
        "kitsu_id": None,
        "anilist_id": 128757,
        "anidb_id": None,
    }
    db.index[2] = {
        "id": 2,
        "mal_id": None,
        "kitsu_id": 44021,
        "anilist_id": None,
        "anidb_id": None,
    }

    providers = [
        _FakeProvider(
            "KitsuIo",
            schedule_items=[_schedule_like({"kitsu_id": 44021}, title="Duplicate Kitsu")],
        ),
        _FakeProvider(
            "JikanMoe",
            schedule_items=[_schedule_like({"mal_id": 46488}, title="Duplicate MAL")],
        ),
    ]
    api = _FakeAPI(providers)
    db_manager = _MappingDBManager(db)
    coord = APICoordinator(max_workers=2, provider_timeout_s=2.0)
    coord.set_api(api)
    coord.set_database_manager(db_manager)
    index_repo = CatalogIndexRepository(db)
    merge_service = CatalogMergeService(CatalogMergeRepository(db))
    coord.set_catalog_identity(
        CatalogIdentityService.from_database(
            db,
            index_repo=index_repo,
            merge_service=merge_service,
            batched_writes=_batched_writes,
        )
    )
    coord.log = lambda *args, **kwargs: None
    try:
        result = coord.fetch_latest(limit=10, per_provider=False)
    finally:
        coord.close()

    assert result is not None
    assert len(result.records) == 1
    assert result.records[0].id == 1
    assert db_manager.upserts and len(db_manager.upserts[0]) == 1
    assert 2 not in db.index


def test_fetch_latest_filters_rows_outside_recency_window():
    now = int(time.time())
    recent = now - 10 * 86_400
    old = now - 400 * 86_400
    api = _FakeAPI(
        [
            _FakeProvider(
                "A",
                schedule_items=[
                    _anime_like(1, date_from=recent),
                    _anime_like(2, date_from=old),
                ],
            ),
        ]
    )
    db = _RecordingDBManager()
    coord = _build_coordinator(api, db)
    try:
        result = coord.fetch_latest(limit=10, per_provider=False)
    finally:
        coord.close()

    assert result is not None
    assert [record.id for record in result.records] == [1]
    assert db.upserts and [anime.id for anime in db.upserts[0]] == [1]


def test_browse_season_dedupes_across_providers():
    api = _FakeAPI(
        [
            _FakeProvider("A", season_items=[_anime_like(1), _anime_like(2)]),
            _FakeProvider("B", season_items=[_anime_like(2), _anime_like(3)]),
        ]
    )
    db = _RecordingDBManager()
    coord = _build_coordinator(api, db)
    try:
        results = coord.browse_season(2026, "spring", limit=10)
    finally:
        coord.close()

    assert results is not None
    assert sorted(a.id for a in results) == [1, 2, 3]


def test_stream_browse_season_yields_progressively():
    api = _FakeAPI(
        [
            _FakeProvider("A", season_items=[_anime_like(1)]),
            _FakeProvider("B", season_items=[_anime_like(2)]),
        ]
    )
    db = _RecordingDBManager()
    coord = _build_coordinator(api, db)
    try:
        ids = [item.id for item in coord.stream_browse_season(2026, "spring", limit=10)]
    finally:
        coord.close()

    assert sorted(ids) == [1, 2]
