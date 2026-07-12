"""Tests for cross-provider index consolidation."""

from __future__ import annotations

from application.services.index_merge import merge_anime_index_rows
from adapters.persistence.catalog_repository import CatalogMergeRepository
from shared.contracts import RepairStrategy


class _IndexDB:
    def __init__(self):
        self.index = {
            1: {"id": 1, "mal_id": 62604, "kitsu_id": None, "anilist_id": None, "anidb_id": None},
            2: {"id": 2, "mal_id": None, "kitsu_id": None, "anilist_id": 138380, "anidb_id": None},
        }
        self.anime = {1: {"id": 1, "title": "Shared Title"}, 2: {"id": 2, "title": "Shared Title"}}
        self.torrents_index: list[tuple[int, str]] = [(2, "dup-hash")]
        self.saved = 0

    def get_lock(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def sql(self, sql, params=(), save=False):
        sql_norm = " ".join(sql.split())
        if save:
            self.saved += 1
        if sql_norm.startswith("SELECT id, mal_id"):
            return [tuple(self.index[i].values()) for i in params if i in self.index]
        if sql_norm.startswith("SELECT id FROM indexList WHERE mal_id"):
            mal_id = params[0]
            for row in self.index.values():
                if row.get("mal_id") == mal_id:
                    return [(row["id"],)]
            return []
        if sql_norm.startswith("SELECT id FROM anime WHERE id"):
            row_id = params[0]
            return [(row_id,)] if row_id in self.anime else []
        if sql_norm.startswith("SELECT id, mal_id FROM indexList"):
            return [
                (row["id"], row["mal_id"])
                for row in self.index.values()
                if row.get("mal_id") is not None
            ]
        if "GROUP_CONCAT" in sql_norm:
            groups: dict[str, list[int]] = {}
            for row in self.anime.values():
                key = row["title"].lower().strip()
                groups.setdefault(key, []).append(row["id"])
            out = []
            for key, ids in groups.items():
                if len(ids) > 1:
                    out.append((key, ",".join(str(i) for i in sorted(ids))))
            return out
        if sql_norm.startswith("DELETE FROM anime"):
            self.anime.pop(params[0], None)
            return []
        if sql_norm.startswith("DELETE FROM indexList"):
            self.index.pop(params[0], None)
            return []
        if sql_norm.startswith("SELECT value FROM torrentsIndex WHERE id"):
            duplicate_id = int(params[0])
            return [(value,) for row_id, value in self.torrents_index if row_id == duplicate_id]
        if sql_norm.startswith("SELECT EXISTS(SELECT 1 FROM torrentsIndex"):
            canonical_id, hash_value = params
            exists = any(
                row_id == int(canonical_id) and value == hash_value
                for row_id, value in self.torrents_index
            )
            return [(int(exists),)]
        if "DELETE FROM torrentsIndex WHERE id" in sql_norm and "AND value" in sql_norm:
            duplicate_id, hash_value = params
            self.torrents_index = [
                row
                for row in self.torrents_index
                if not (row[0] == int(duplicate_id) and row[1] == hash_value)
            ]
            return []
        if sql_norm.startswith("UPDATE torrentsIndex SET id"):
            canonical_id, duplicate_id, hash_value = params
            self.torrents_index = [
                (int(canonical_id), hash_value)
                if row[0] == int(duplicate_id) and row[1] == hash_value
                else row
                for row in self.torrents_index
            ]
            return []
        if sql_norm.startswith("UPDATE indexList"):
            col_val, row_id = params
            for col in ("mal_id", "kitsu_id", "anilist_id", "anidb_id"):
                if f"SET {col}=" in sql_norm:
                    self.index[row_id][col] = col_val
            return []
        if sql_norm.startswith("UPDATE "):
            return []
        return []

    def save(self):
        self.saved += 1


def test_merge_deletes_orphan_anime_row():
    db = _IndexDB()
    merge_anime_index_rows(
        merge_repo=CatalogMergeRepository(db),
        duplicate_id=2,
        canonical_id=1,
    )
    assert 2 not in db.anime
    assert 2 not in db.index
    assert db.saved > 0


def test_merge_repoints_torrents_index_to_canonical():
    db = _IndexDB()
    merge_anime_index_rows(
        merge_repo=CatalogMergeRepository(db),
        duplicate_id=2,
        canonical_id=1,
    )
    assert db.torrents_index == [(1, "dup-hash")]


def test_repair_merges_rows_with_identical_title():
    db = _IndexDB()
    merged = CatalogMergeRepository(db).repair_duplicates(
        strategy=RepairStrategy.TITLE
    )
    assert merged >= 1
    assert 2 not in db.anime
