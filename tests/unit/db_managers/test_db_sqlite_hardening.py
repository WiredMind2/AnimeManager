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
