"""Tests for MyAnimeListNet catalog identity resolution."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from adapters.api.MyAnimeListNet import MyAnimeListNetWrapper


class _IndexDB:
    """Minimal in-memory indexList stand-in for merge tests."""

    def __init__(self):
        self._next = 100
        self.index = {
            1: {
                "id": 1,
                "mal_id": 46488,
                "kitsu_id": None,
                "anilist_id": 128757,
                "anidb_id": None,
            },
        }
        self.deleted: list[int] = []

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
        if "FROM indexList WHERE mal_id" in sql_norm:
            mal_id = int(params[0])
            for row in self.index.values():
                if row.get("mal_id") == mal_id:
                    return [(row["id"],)]
            return []
        if "FROM indexList WHERE kitsu_id" in sql_norm:
            kitsu_id = int(params[0])
            for row in self.index.values():
                if row.get("kitsu_id") == kitsu_id:
                    return [(row["id"],)]
            return []
        if "FROM indexList WHERE anilist_id" in sql_norm:
            anilist_id = int(params[0])
            for row in self.index.values():
                if row.get("anilist_id") == anilist_id:
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
            row_id = int(params[0])
            self.deleted.append(row_id)
            self.index.pop(row_id, None)
            return []
        if sql_norm.startswith("UPDATE "):
            return []
        return []

    def save(self):
        pass

    def procedure(self, name, *args):
        return (name, *args), []


def _minimal_mal_node(mal_id: int = 46488) -> dict:
    return {
        "id": mal_id,
        "title": "Young Ladies Don't Play Fighting Games",
        "alternative_titles": {"en": "Young Ladies Don't Play Fighting Games"},
        "start_date": "2026-07-07",
        "end_date": "",
        "main_picture": {"medium": "http://example.com/p.jpg"},
        "synopsis": "Test synopsis",
        "num_episodes": 12,
        "average_episode_duration": 1440,
        "rating": "pg-13",
        "status": "currently_airing",
        "genres": [{"name": "Comedy"}],
    }


@pytest.fixture
def mal_wrapper():
    wrapper = MyAnimeListNetWrapper.__new__(MyAnimeListNetWrapper)
    wrapper.database = _IndexDB()
    wrapper.apiKey = "mal_id"
    wrapper.defer_writes = False
    wrapper.queue = None
    return wrapper


def test_mal_convert_anime_uses_resolve_catalog_id(mal_wrapper):
    with patch.object(mal_wrapper, "resolve_catalog_id", wraps=mal_wrapper.resolve_catalog_id) as resolve:
        with patch.object(mal_wrapper, "save_pictures"):
            with patch.object(mal_wrapper, "save_genres"):
                with patch.object(mal_wrapper, "getStatus", return_value="AIRING", create=True):
                    out = mal_wrapper._convertAnime(_minimal_mal_node())
        resolve.assert_called_once_with({"mal_id": 46488})
    assert out["id"] == 1


def test_mal_convert_anime_folds_into_existing_cross_provider_row(mal_wrapper):
    with patch.object(mal_wrapper, "save_pictures"):
        with patch.object(mal_wrapper, "save_genres"):
            with patch.object(mal_wrapper, "getStatus", return_value="AIRING", create=True):
                out = mal_wrapper._convertAnime(_minimal_mal_node())
    assert out["id"] == 1
    assert 1 in mal_wrapper.database.index
    assert mal_wrapper.database.index[1]["mal_id"] == 46488
