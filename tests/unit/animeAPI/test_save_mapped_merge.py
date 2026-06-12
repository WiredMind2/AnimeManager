"""Tests for cross-provider ``save_mapped`` index merging."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from adapters.api.APIUtils import APIUtils


class _IndexDB:
    """Minimal in-memory indexList stand-in for merge tests."""

    def __init__(self):
        self._next = 10
        self.index = {
            1: {"id": 1, "mal_id": 62604, "kitsu_id": None, "anilist_id": None, "anidb_id": None},
            2: {"id": 2, "mal_id": None, "kitsu_id": None, "anilist_id": 138380, "anidb_id": None},
        }
        self.deleted: list[int] = []
        self.updated: list[tuple] = []

    def get_lock(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def sql(self, sql, params=(), save=False):
        sql_norm = " ".join(sql.split())
        if sql_norm.startswith("SELECT id, mal_id"):
            ids = params
            return [
                tuple(self.index[i].values())
                for i in ids
                if i in self.index
            ]
        if sql_norm.startswith("SELECT id FROM indexList WHERE mal_id"):
            mal_id = params[0]
            for row in self.index.values():
                if row.get("mal_id") == mal_id:
                    return [(row["id"],)]
            return []
        if sql_norm.startswith("UPDATE indexList SET mal_id"):
            mal_id, row_id = params
            self.index[row_id]["mal_id"] = mal_id
            self.updated.append(("mal_id", row_id, mal_id))
            return []
        if sql_norm.startswith("DELETE FROM"):
            row_id = params[0]
            self.deleted.append(row_id)
            self.index.pop(row_id, None)
            return []
        if sql_norm.startswith("UPDATE "):
            return []
        return []

    def save(self):
        pass


@pytest.fixture
def api_utils():
    obj = APIUtils.__new__(APIUtils)
    obj.database = _IndexDB()
    obj.apiKey = "anilist_id"
    obj.defer_writes = False
    obj.queue = None
    return obj


def test_save_mapped_merges_into_existing_mal_row(api_utils):
    # Internal id 2 (anilist) should fold into id 1 (existing mal row).
    canonical = api_utils.save_mapped(2, [("mal_id", 62604)])
    assert canonical == 1
    assert 2 in api_utils.database.deleted
    assert api_utils.database.index[1]["mal_id"] == 62604


def test_save_mapped_links_unknown_mapping_on_same_row(api_utils):
    api_utils.database.index[3] = {
        "id": 3,
        "mal_id": None,
        "kitsu_id": 99,
        "anilist_id": None,
        "anidb_id": None,
    }
    canonical = api_utils.save_mapped(3, [("mal_id", 777)])
    assert canonical == 3
    assert api_utils.database.index[3]["mal_id"] == 777
