"""Tests for catalogue identity enrichment."""

from __future__ import annotations

from adapters.persistence.catalog_repository import (
    CatalogIndexRepository,
    CatalogMergeRepository,
    _batched_writes,
)
from application.services.catalog_enrichment import (
    CatalogEnrichmentService,
    select_single_provider_ids_for_enrichment,
)
from application.services.catalog_identity import CatalogIdentityService
from application.services.catalog_merge import CatalogMergeService


def _enrichment_service(db, mapping_port) -> CatalogEnrichmentService:
    index_repo = CatalogIndexRepository(db)
    merge_service = CatalogMergeService(CatalogMergeRepository(db))
    identity_service = CatalogIdentityService.from_database(
        db,
        index_repo=index_repo,
        merge_service=merge_service,
        batched_writes=_batched_writes,
    )
    return CatalogEnrichmentService(
        db,
        mapping_port,
        index_repo=index_repo,
        identity_service=identity_service,
    )


class _EnrichmentDB:
    def __init__(self):
        self._next = 100
        self.index: dict[int, dict] = {
            1: {
                "id": 1,
                "mal_id": 46488,
                "kitsu_id": None,
                "anilist_id": 128757,
                "anidb_id": None,
            },
            2: {
                "id": 2,
                "mal_id": None,
                "kitsu_id": 44021,
                "anilist_id": None,
                "anidb_id": None,
            },
        }
        self.anime = {
            1: {"id": 1, "title": "Canonical"},
            2: {"id": 2, "title": "Duplicate"},
            3: {"id": 3, "title": "Duplicate"},
        }
        self.index[3] = {
            "id": 3,
            "mal_id": None,
            "kitsu_id": 99999,
            "anilist_id": None,
            "anidb_id": None,
        }

    def get_lock(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getId(self, api_key, api_id, table="anime"):
        for row in self.index.values():
            if row.get(api_key) == int(api_id):
                return row["id"]
        new_id = self._next
        self._next += 1
        self.index[new_id] = {
            "id": new_id,
            "mal_id": None,
            "kitsu_id": None,
            "anilist_id": None,
            "anidb_id": None,
            api_key: int(api_id),
        }
        return new_id

    def sql(self, sql, params=(), save=False):
        sql_norm = " ".join(sql.split())
        if "FROM indexList i" in sql_norm and "EXISTS" in sql_norm:
            rows = []
            for row in self.index.values():
                count = sum(
                    1
                    for key in ("mal_id", "kitsu_id", "anilist_id", "anidb_id")
                    if row.get(key) is not None
                )
                if count != 1:
                    continue
                anime = self.anime.get(row["id"])
                if not anime or not anime.get("title"):
                    continue
                title = anime["title"].lower().strip()
                has_duplicate_title = any(
                    other_id != row["id"]
                    and self.anime.get(other_id, {}).get("title", "").lower().strip() == title
                    for other_id in self.anime
                )
                if has_duplicate_title:
                    rows.append((row["id"],))
            rows.sort(key=lambda item: item[0], reverse=True)
            limit = int(params[0]) if params else len(rows)
            return rows[:limit]
        if "FROM indexList i" in sql_norm and "NOT IN" in sql_norm:
            excluded = {int(value) for value in params[:-1]}
            limit = int(params[-1])
            rows = []
            for row in self.index.values():
                if row["id"] in excluded:
                    continue
                count = sum(
                    1
                    for key in ("mal_id", "kitsu_id", "anilist_id", "anidb_id")
                    if row.get(key) is not None
                )
                if count == 1:
                    rows.append((row["id"],))
            rows.sort(key=lambda item: item[0], reverse=True)
            return rows[:limit]
        if "FROM indexList WHERE (" in sql_norm and "= 1" in sql_norm:
            rows = []
            for row in self.index.values():
                count = sum(
                    1
                    for key in ("mal_id", "kitsu_id", "anilist_id", "anidb_id")
                    if row.get(key) is not None
                )
                if count == 1:
                    rows.append((row["id"],))
            rows.sort(key=lambda item: item[0], reverse=True)
            limit = int(params[0]) if params else len(rows)
            return rows[:limit]
        if sql_norm.startswith("SELECT id FROM indexList WHERE"):
            col = sql_norm.split("WHERE")[1].split("=")[0].strip()
            val = int(params[0])
            for row in self.index.values():
                if row.get(col) == val:
                    return [(row["id"],)]
            return []
        if sql_norm.startswith("SELECT mal_id, kitsu_id"):
            internal_id = int(params[0])
            row = self.index.get(internal_id)
            if not row:
                return []
            return [
                (
                    row["mal_id"],
                    row["kitsu_id"],
                    row["anilist_id"],
                    row["anidb_id"],
                )
            ]
        if sql_norm.startswith("UPDATE indexList SET"):
            col = sql_norm.split("SET")[1].split("=")[0].strip()
            val, internal_id = params
            self.index[int(internal_id)][col] = val
            return []
        if sql_norm.startswith("DELETE FROM"):
            if "indexList" in sql_norm:
                self.index.pop(int(params[0]), None)
            elif "anime" in sql_norm:
                self.anime.pop(int(params[0]), None)
            return []
        if sql_norm.startswith("UPDATE "):
            return []
        return []

    def save(self):
        pass


class _FakeMappingPort:
    def lookup_kitsu_mappings(self, kitsu_id: int) -> dict[str, int]:
        if kitsu_id == 44021:
            return {
                "kitsu_id": 44021,
                "mal_id": 46488,
                "anilist_id": 128757,
            }
        return {}

    def lookup_anilist_cross_ids(self, anilist_id: int) -> dict[str, int]:
        if anilist_id == 128757:
            return {"anilist_id": 128757, "mal_id": 46488}
        return {}

    def lookup_mal_cross_ids(self, mal_id: int) -> dict[str, int]:
        return {}


def test_enrich_kitsu_only_row_merges_into_existing_canonical():
    db = _EnrichmentDB()
    service = _enrichment_service(db, _FakeMappingPort())
    result = service.enrich_ids([2])
    assert result.looked_up == 1
    assert result.enriched == 1
    assert result.merged == 1
    assert 2 not in db.index
    assert db.index[1]["kitsu_id"] == 44021
    assert db.index[1]["mal_id"] == 46488
    assert db.index[1]["anilist_id"] == 128757


def test_enrich_single_provider_scan_finds_kitsu_row():
    db = _EnrichmentDB()
    service = _enrichment_service(db, _FakeMappingPort())
    result = service.enrich_single_provider_rows(limit=10)
    assert result.looked_up == 1
    assert result.merged == 1
    assert 2 not in db.index


def test_expand_external_ids_with_mapping_merges_cross_refs():
    from application.services.catalog_enrichment import expand_external_ids_with_mapping

    expanded = expand_external_ids_with_mapping(
        {"kitsu_id": 44021},
        _FakeMappingPort(),
    )
    assert expanded == {
        "kitsu_id": 44021,
        "mal_id": 46488,
        "anilist_id": 128757,
    }


def test_enrich_skips_rows_with_multiple_provider_ids():
    db = _EnrichmentDB()
    service = _enrichment_service(db, _FakeMappingPort())
    result = service.enrich_ids([1])
    assert result.looked_up == 0
    assert result.enriched == 0
    assert result.merged == 0
    assert 1 in db.index


def test_select_single_provider_ids_prioritizes_duplicate_titles():
    db = _EnrichmentDB()
    selected = select_single_provider_ids_for_enrichment(db, limit=2)
    assert selected[0] == 3
    assert 3 in selected
    assert 2 in selected
