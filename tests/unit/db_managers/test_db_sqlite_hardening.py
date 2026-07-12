"""SQLite connection hardening tests."""

from __future__ import annotations

import sqlite3

from adapters.persistence.dbManager import _configure_sqlite_connection, db_instance


def test_configure_sqlite_connection_sets_busy_timeout():
    con = sqlite3.connect(":memory:")
    try:
        _configure_sqlite_connection(con, busy_timeout_ms=7500)
        row = con.execute("PRAGMA busy_timeout").fetchone()
        assert row is not None
        assert int(row[0]) == 7500
    finally:
        con.close()


def test_db_instance_ensure_connection_sets_busy_timeout():
    db = db_instance(":memory:")
    db._ensure_connection()
    row = db.con.execute("PRAGMA busy_timeout").fetchone()
    assert row is not None
    assert int(row[0]) == 5000
    db.close()
    db.con.close()


def test_db_instance_initializes_base_query_cache():
    db = db_instance(":memory:")
    assert hasattr(db, "_query_cache")
    assert isinstance(db._query_cache, dict)


def test_db_instance_sql_select_works_without_manual_cache_priming():
    db = db_instance(":memory:")
    row = db.sql("SELECT 1 AS n", to_dict=True)
    assert row == [{"n": 1}]
    db.close()
    db.con.close()
