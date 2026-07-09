"""Regression tests for MariaDB connection recovery and lock stability."""

from __future__ import annotations

import threading

import pytest

from adapters.persistence.base import ConnectionPool, _PooledConnectionHandle


def test_connection_pool_discard_closes_without_requeue():
    closed: list[object] = []

    class _Conn:
        def close(self):
            closed.append(self)

        def ping(self, reconnect=False):
            return None

    pool = ConnectionPool(factory=_Conn, pool_size=2)
    pool.drain()
    before = len(closed)
    conn = pool.get_connection()
    pool.return_connection(conn, discard=True)
    assert len(closed) == before + 1
    assert pool._pool.qsize() == 0


def test_pooled_handle_tracks_discard_flag():
    handle = _PooledConnectionHandle(object())
    assert handle.discard is False
    handle.discard = True
    assert handle.discard is True


def test_recover_connections_preserves_db_lock():
    from adapters.persistence.embeddedMariaDB import EmbeddedMariaDB

    db = object.__new__(EmbeddedMariaDB)
    db.settings = {}
    db.lock = threading.RLock()
    original_lock = db.lock
    db.log = lambda *args, **kwargs: None
    db.close = lambda: None
    db.db = None
    db.connection_pool = ConnectionPool(
        factory=lambda: type("C", (), {"close": lambda self: None, "ping": lambda self, reconnect=False: None})(),
        pool_size=2,
    )
    db._pinned_sql_conn = None
    db._init_connection_pool = lambda: (_ for _ in ()).throw(
        AssertionError("_init_connection_pool must not run during recovery")
    )
    db._connect_to_database = lambda: setattr(db, "db", object())
    db.get_cursor = lambda: setattr(db, "cur", object())

    with db.lock:
        db._recover_connections()
        assert db.lock is original_lock
        # still held by this ``with`` block — release must not raise


def test_execute_sql_marks_pool_connection_bad_on_index_error():
    from adapters.persistence.embeddedMariaDB import EmbeddedMariaDB

    db = object.__new__(EmbeddedMariaDB)
    db._io_stats_lock = threading.Lock()
    db._query_count = 0
    db._commit_count = 0
    db._telemetry = type("T", (), {"increment": lambda *a, **k: None})()

    class _BadCursor:
        description = None

        def execute(self, *_args, **_kwargs):
            raise IndexError("bytearray index out of range")

    conn_mgr = _PooledConnectionHandle(object())
    conn_mgr.cur = _BadCursor()
    conn_mgr.db = type("DB", (), {"rollback": lambda self: None})()

    marked: list[object] = []
    db._mark_pool_connection_bad = lambda cm: marked.append(cm)

    with pytest.raises(IndexError):
        db._execute_sql(conn_mgr, "SELECT 1", [])
    assert marked == [conn_mgr]


def test_handle_sql_error_retries_index_error():
    from adapters.persistence.embeddedMariaDB import handle_sql_error

    attempts = {"n": 0}

    class _DB:
        _pinned_sql_conn = None
        cur = object()

        def get_cursor(self):
            return None

        def _recover_connections(self):
            return None

        def _mark_pool_connection_bad(self, _cm):
            return None

    @handle_sql_error
    def _fn(self):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise IndexError("bytearray index out of range")
        return "ok"

    assert _fn(_DB()) == "ok"
    assert attempts["n"] == 2
