"""Edge-case unit tests for ``application.services.database_manager.DatabaseManager``.

Uses in-memory fake databases. Never opens a real DB connection.
"""

from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest


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
    """A minimal fake `BaseDB`-shaped object.

    Mirrors the real ``BaseDB`` contract: ``save()`` is the no-argument
    transaction-commit hook, and per-row writes go through
    ``set(id, data, table, save=...)``.
    """

    USE_CONNECTION_POOL = False

    def __init__(self):
        self.saved = []
        self.metadata_saved = []
        self.metadata_calls = []
        self._lock = _NopLock()
        self.sql_calls: List[Tuple[str, Tuple]] = []
        self.sql_responses: Dict[str, Any] = {}
        self.procedure_calls: List[Tuple[str, Tuple]] = []
        self.procedure_results: List[Any] = []
        self.filter_results: List[Any] = []
        self.metadata_bulk_called = False
        self.metadata_bulk_input: Any = None
        self.save_called = False
        self.commit_count = 0
        self.raise_close = False
        self.is_init_value = True

    def get_lock(self):
        return self._lock

    def save(self):
        self.save_called = True
        self.commit_count += 1

    def set(self, id, data, table, save: bool = True):
        self.saved.append(SimpleNamespace(id=id, **{k: v for k, v in data.items() if k != "id"}))
        if save:
            self.save()

    def is_initialized(self):
        return self.is_init_value

    def close(self):
        if self.raise_close:
            raise RuntimeError("close fail")

    def sql(self, query: str, params: Tuple = (), save: bool = True):
        self.sql_calls.append((query, params))
        return self.sql_responses.get(query, [])

    def procedure(self, name, *args):
        self.procedure_calls.append((name, args))
        if self.procedure_results:
            return ([], self.procedure_results.pop(0))
        return ([], [])

    def get_all_metadata_bulk(self, anime_batch, use_eager_loading=True):
        self.metadata_bulk_called = True
        self.metadata_bulk_input = anime_batch
        return anime_batch

    def get_all_metadata(self, anime):
        return anime

    def filter(self, **kwargs):
        # Return a "list-like" object with `.empty()`
        items = self.filter_results.pop(0) if self.filter_results else []
        return SimpleNamespace(empty=lambda: not items, items=items)

    def save_metadata(self, anime_id, metadata):
        self.metadata_calls.append((anime_id, metadata))


# ---------------------------------------------------------------------------
# Search anime: input sanitization edges
# ---------------------------------------------------------------------------


class TestSearchAnime:
    def test_returns_none_for_none_terms(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        mgr.set_database(_FakeDB())
        assert mgr.search_anime(None) is None  # type: ignore[arg-type]

    def test_returns_none_for_empty_terms(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        mgr.set_database(_FakeDB())
        assert mgr.search_anime("") is None
        assert mgr.search_anime("   ") is None

    def test_returns_none_for_only_punctuation(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        mgr.set_database(_FakeDB())
        # All non-alnum collapse to spaces and then trimmed away.
        assert mgr.search_anime("!!!---@@@") is None

    def test_returns_none_when_db_has_no_results(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.procedure_results = [[]]
        mgr.set_database(db)
        assert mgr.search_anime("naruto") is None

    def test_db_exception_returns_none(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.procedure = MagicMock(side_effect=RuntimeError("boom"))
        mgr.set_database(db)
        assert mgr.search_anime("naruto") is None

    def test_search_terms_normalization_strips_punctuation(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.procedure_results = [[]]
        mgr.set_database(db)
        mgr.search_anime("@@@ naruto !!! shippuden")
        # procedure was called with cleaned terms
        called_name, args = db.procedure_calls[-1]
        assert called_name == "search_anime_fast"
        assert "naruto" in args[0] and "shippuden" in args[0]
        # No `@` or `!` in the cleaned string.
        assert "@" not in args[0]
        assert "!" not in args[0]


# ---------------------------------------------------------------------------
# get_anime_list: query building + pagination
# ---------------------------------------------------------------------------


class TestGetAnimeList:
    def test_db_exception_returns_none_pair(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.filter = MagicMock(side_effect=RuntimeError("boom"))
        mgr.set_database(db)
        result = mgr.get_anime_list("DEFAULT", listrange=(0, 10))
        assert result == (None, None)

    def test_empty_filter_no_next_page(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.filter_results = [[]]
        mgr.set_database(db)
        result, next_fn = mgr.get_anime_list("DEFAULT", listrange=(0, 10))
        assert result is not None
        assert next_fn is None

    def test_non_empty_filter_yields_next_page(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.filter_results = [["a", "b"], []]
        mgr.set_database(db)
        result, next_fn = mgr.get_anime_list("DEFAULT", listrange=(0, 10))
        assert result is not None
        assert callable(next_fn)
        # Calling next_fn returns next page.
        result2, _ = next_fn()
        assert result2 is not None

    def test_default_user_id_is_4(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.filter_results = [[]]
        mgr.set_database(db)
        with patch.object(mgr, "_build_query_args", wraps=mgr._build_query_args) as bqa:
            mgr.get_anime_list("DEFAULT", listrange=(0, 10))
            assert bqa.call_args.args[3] == 4

    def test_hide_rated_attr_used_when_none(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        mgr.hide_rated = False
        db = _FakeDB()
        db.filter_results = [[]]
        mgr.set_database(db)
        with patch.object(mgr, "_build_query_args", wraps=mgr._build_query_args) as bqa:
            mgr.get_anime_list("DEFAULT", listrange=(0, 10))
            assert bqa.call_args.args[2] is False


# ---------------------------------------------------------------------------
# Connection / lifecycle edges
# ---------------------------------------------------------------------------


class TestConnection:
    def test_get_connection_raises_when_uninitialized(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        with pytest.raises(RuntimeError):
            with mgr.get_connection():
                pass

    def test_get_connection_pool_branch(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.USE_CONNECTION_POOL = True
        mgr.set_database(db)
        # Should not call get_lock when using a pool.
        with mgr.get_connection() as cur:
            assert cur is db

    def test_get_connection_pool_exception_propagates(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.USE_CONNECTION_POOL = True
        mgr.set_database(db)
        with pytest.raises(RuntimeError):
            with mgr.get_connection():
                raise RuntimeError("inside")

    def test_get_connection_lock_exception_propagates(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        mgr.set_database(db)
        with pytest.raises(ValueError):
            with mgr.get_connection():
                raise ValueError("inside")

    def test_is_initialized_false_without_db(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        assert mgr.is_initialized() is False

    def test_is_initialized_propagates_from_db(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.is_init_value = False
        mgr.set_database(db)
        assert mgr.is_initialized() is False
        db.is_init_value = True
        assert mgr.is_initialized() is True

    def test_close_swallows_db_close_exception(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.raise_close = True
        mgr.set_database(db)
        mgr.close()
        assert mgr.get_database() is None

    def test_stop_alias_is_close(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        mgr.set_database(db)
        mgr._stop()
        assert mgr.get_database() is None

    def test_close_idempotent(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        mgr.set_database(_FakeDB())
        mgr.close()
        mgr.close()  # second call must not raise

    def test_set_database_overwrites(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db1 = _FakeDB()
        db2 = _FakeDB()
        mgr.set_database(db1)
        assert mgr.get_database() is db1
        mgr.set_database(db2)
        assert mgr.get_database() is db2


# ---------------------------------------------------------------------------
# Save torrent
# ---------------------------------------------------------------------------


class TestSaveTorrent:
    def test_save_with_list_trackers_json_dumps(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.sql_responses = {
            "SELECT EXISTS(SELECT 1 FROM torrentsIndex WHERE id=? AND value=?)": [(0,)],
            "SELECT EXISTS(SELECT 1 FROM torrents WHERE hash=?)": [(0,)],
        }
        mgr.set_database(db)
        torrent = SimpleNamespace(
            hash="abcd",
            name="some torrent",
            trackers=["udp://t1", "udp://t2"],
        )
        mgr.save_torrent(7, torrent)
        # JSON dumps must be invoked.
        torrents_insert = [c for c in db.sql_calls if "INSERT INTO torrents(" in c[0]]
        assert torrents_insert
        _, params = torrents_insert[0]
        assert json.loads(params[2]) == ["udp://t1", "udp://t2"]

    def test_save_with_none_trackers_dumps_empty(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.sql_responses = {
            "SELECT EXISTS(SELECT 1 FROM torrentsIndex WHERE id=? AND value=?)": [(0,)],
            "SELECT EXISTS(SELECT 1 FROM torrents WHERE hash=?)": [(0,)],
        }
        mgr.set_database(db)
        torrent = SimpleNamespace(hash="x", name="n", trackers=None)
        mgr.save_torrent(1, torrent)
        torrents_insert = [c for c in db.sql_calls if "INSERT INTO torrents(" in c[0]]
        _, params = torrents_insert[0]
        assert params[2] == "[]"

    def test_save_skips_inserts_when_already_exists(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.sql_responses = {
            "SELECT EXISTS(SELECT 1 FROM torrentsIndex WHERE id=? AND value=?)": [(1,)],
            "SELECT EXISTS(SELECT 1 FROM torrents WHERE hash=?)": [(1,)],
        }
        mgr.set_database(db)
        torrent = SimpleNamespace(hash="x", name="n", trackers=[])
        mgr.save_torrent(1, torrent)
        inserts = [c for c in db.sql_calls if "INSERT" in c[0]]
        assert not inserts

    def test_save_torrent_exception_propagates(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.sql = MagicMock(side_effect=RuntimeError("oops"))
        mgr.set_database(db)
        torrent = SimpleNamespace(hash="x", name="n", trackers=[])
        with pytest.raises(RuntimeError):
            mgr.save_torrent(1, torrent)

    def test_get_torrent_data_returns_first_row(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.sql_responses = {
            "SELECT name, trackers FROM torrents WHERE hash=? LIMIT 1": [
                ("Naruto", '["http://x"]')
            ],
        }
        mgr.set_database(db)
        assert mgr.get_torrent_data("h") == ("Naruto", '["http://x"]')

    def test_get_torrent_data_empty_returns_none(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.sql_responses = {
            "SELECT name, trackers FROM torrents WHERE hash=? LIMIT 1": [],
        }
        mgr.set_database(db)
        assert mgr.get_torrent_data("h") is None

    def test_get_torrent_data_exception_returns_none(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.sql = MagicMock(side_effect=RuntimeError("boom"))
        mgr.set_database(db)
        assert mgr.get_torrent_data("h") is None


# ---------------------------------------------------------------------------
# Anime CRUD edges
# ---------------------------------------------------------------------------


class TestAnimeCRUD:
    def test_get_anime_metadata_db_exception_returns_anime(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.get_all_metadata = MagicMock(side_effect=RuntimeError("boom"))
        mgr.set_database(db)
        anime = SimpleNamespace(id=42)
        assert mgr.get_anime_metadata(anime) is anime

    def test_update_anime_exception_propagates(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.set = MagicMock(side_effect=RuntimeError("oh no"))
        mgr.set_database(db)
        with pytest.raises(RuntimeError):
            mgr.update_anime(SimpleNamespace(id=1))

    def test_upsert_anime_batch_empty_returns_zero(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        mgr.set_database(db)
        assert mgr.upsert_anime_batch([]) == 0

    def test_upsert_anime_batch_skips_failed_records(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()

        def fake_set(id, data, table, save=True):
            if id == 2:
                raise RuntimeError("bad")
            db.saved.append(SimpleNamespace(id=id))

        db.set = fake_set
        mgr.set_database(db)
        result = mgr.upsert_anime_batch(
            [SimpleNamespace(id=1), SimpleNamespace(id=2), SimpleNamespace(id=3)]
        )
        # 1 and 3 succeed, 2 fails.
        assert result == 2
        assert {a.id for a in db.saved} == {1, 3}

    def test_upsert_metadata_batch_empty(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        mgr.set_database(_FakeDB())
        assert mgr.upsert_metadata_batch([]) == 0

    def test_upsert_metadata_skips_empty(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        mgr.set_database(db)
        n = mgr.upsert_metadata_batch([(1, {}), (2, {"x": 1}), (3, None)])
        assert n == 1
        assert db.metadata_calls == [(2, {"x": 1})]

    def test_upsert_metadata_save_exception_skipped(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        db.save_metadata = MagicMock(side_effect=RuntimeError("bad"))
        mgr.set_database(db)
        assert mgr.upsert_metadata_batch([(1, {"x": 1}), (2, {"y": 2})]) == 0


# ---------------------------------------------------------------------------
# Queue stats / disabled queue
# ---------------------------------------------------------------------------


class TestQueueStats:
    def test_write_queue_stats_empty_when_disabled(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        assert mgr.write_queue_stats() == {}

    def test_enable_batched_writes_is_idempotent(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        mgr.set_database(_FakeDB())
        mgr.enable_batched_writes(batch_size=2, max_latency_ms=50)
        wq1 = mgr._write_queue
        mgr.enable_batched_writes(batch_size=10, max_latency_ms=100)
        assert mgr._write_queue is wq1
        mgr.close()

    def test_enqueue_anime_falls_back_to_sync(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _FakeDB()
        mgr.set_database(db)
        assert mgr.enqueue_anime(SimpleNamespace(id=5)) is True
        assert any(getattr(a, "id", None) == 5 for a in db.saved)
