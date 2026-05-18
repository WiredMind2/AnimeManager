"""Lookup and search success-path tests for :class:`DatabaseManager`."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from adapters.legacy.legacy_classes import Anime, AnimeList


@pytest.fixture
def DatabaseManager():
    from application.services.database_manager import DatabaseManager as _DM

    return _DM


def _silent_logger(*_a, **_kw):
    return None


class _NopLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeDB:
    USE_CONNECTION_POOL = False

    def __init__(self):
        self.sql_calls = []
        self.sql_responses = {}
        self.procedure_results = []
        self._lock = _NopLock()

    def get_lock(self):
        return self._lock

    def is_initialized(self):
        return True

    def save(self):
        return None

    def sql(self, query, params=(), save=True):
        self.sql_calls.append((query, params))
        if query in self.sql_responses:
            return self.sql_responses[query]
        for key, value in self.sql_responses.items():
            if key.split()[0:3] == query.split()[0:3]:
                return value
        return []

    def procedure(self, name, *args):
        keys = [
            "id",
            "title",
            "picture",
            "date_from",
            "date_to",
            "synopsis",
            "episodes",
            "duration",
            "rating",
            "status",
            "broadcast",
            "last_seen",
            "trailer",
        ]
        rows = self.procedure_results.pop(0) if self.procedure_results else []
        return (keys, rows)

    def get_all_metadata_bulk(self, anime_batch, use_eager_loading=True):
        return anime_batch

    def filter(self, **kwargs):
        return SimpleNamespace(empty=lambda: True)


class TestSearchAnimeSuccess:
    def test_returns_anime_list_with_metadata(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.procedure_results = [
            [
                (
                    1,
                    "Naruto",
                    None,
                    None,
                    None,
                    "syn",
                    220,
                    24,
                    "PG-13",
                    "FINISHED",
                    None,
                    None,
                    None,
                    0.9,
                )
            ]
        ]
        mgr.set_database(db)
        result = mgr.search_anime("naruto")
        assert isinstance(result, AnimeList)
        assert not result.empty()
        first = next(iter(result))
        assert isinstance(first, Anime)
        assert first.title == "Naruto"
        assert db.procedure_results == []


class TestTorrentAndTitleLookups:
    def test_list_anime_torrent_pairs_maps_rows(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()

        def _sql(query, params=(), save=True):
            db.sql_calls.append((query, params))
            if "torrentsIndex" in query and "torrents" in query:
                return [(1, "ABC"), (2, " DEF ")]
            return []

        db.sql = _sql
        mgr.set_database(db)
        assert mgr.list_anime_torrent_pairs() == [(1, "ABC"), (2, "DEF")]

    def test_list_anime_torrent_pairs_on_error_returns_empty(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.sql = MagicMock(side_effect=RuntimeError("db down"))
        mgr.set_database(db)
        assert mgr.list_anime_torrent_pairs() == []

    def test_get_anime_ids_by_hashes(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()

        def _sql(query, params=(), save=True):
            db.sql_calls.append((query, params))
            if "torrentsIndex" in query and "LOWER(value) IN" in query:
                return [("abc", 3), ("def", 4)]
            return []

        db.sql = _sql
        mgr.set_database(db)
        assert mgr.get_anime_ids_by_hashes(["ABC", "def"]) == {
            "abc": 3,
            "def": 4,
        }

    def test_get_anime_titles_skips_blank(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()

        def _sql(query, params=(), save=True):
            db.sql_calls.append((query, params))
            if "FROM anime WHERE id IN" in query:
                return [(1, "One"), (2, "")]
            return []

        db.sql = _sql
        mgr.set_database(db)
        assert mgr.get_anime_titles([1, 2]) == {1: "One"}


class TestBatchedWriteFlush:
    def test_flush_write_batch_ignores_empty(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        mgr.set_database(_FakeDB())
        mgr._flush_write_batch([])
        mgr._flush_write_batch([None, None])

    def test_flush_write_batch_calls_upsert(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        mgr.set_database(db)
        mgr.upsert_anime_batch = MagicMock(return_value=2)
        mgr._flush_write_batch([SimpleNamespace(id=1), SimpleNamespace(id=2)])
        mgr.upsert_anime_batch.assert_called_once()
