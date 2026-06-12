"""Catalog identity resolution across provider external ids."""

from __future__ import annotations

from application.services.catalog_identity import CatalogIdentityService


class _IdentityDB:
    def __init__(self):
        self._next = 100
        self.index: dict[int, dict] = {}
        self.anime: dict[int, dict] = {}
        self.saved = 0

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
        self.anime[new_id] = {"id": new_id, "title": "Show"}
        return new_id

    def sql(self, sql, params=(), save=False):
        sql_norm = " ".join(sql.split())
        if save:
            self.saved += 1
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
                    row["id"],
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
            if "anime" in sql_norm:
                self.anime.pop(int(params[0]), None)
            elif "indexList" in sql_norm:
                self.index.pop(int(params[0]), None)
            return []
        if sql_norm.startswith("UPDATE "):
            return []
        return []

    def save(self):
        pass


def test_resolve_merges_conflicting_provider_ids():
    db = _IdentityDB()
    mal_row = db.getId("mal_id", 62604)
    anilist_row = db.getId("anilist_id", 138380)
    assert mal_row != anilist_row

    service = CatalogIdentityService(db)
    resolved = service.resolve_external_ids(
        {"mal_id": 62604, "anilist_id": 138380},
    )
    assert resolved.catalog_id == min(mal_row, anilist_row)
    assert anilist_row not in db.anime or mal_row not in db.anime
