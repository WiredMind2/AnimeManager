#!/usr/bin/env python3
"""Apply minimal SQLite schema upgrades for legacy databases."""

from __future__ import annotations

import sqlite3
import sys


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, name: str) -> set[str]:
    if not _table_exists(conn, name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({name})").fetchall()}


def _torrent_columns_ok(conn: sqlite3.Connection, name: str) -> bool:
    return {"hash", "name", "trackers"}.issubset(_table_columns(conn, name))


def _torrent_index_columns_ok(conn: sqlite3.Connection) -> bool:
    return {"id", "value"}.issubset(_table_columns(conn, "torrentsIndex"))


def upgrade(conn: sqlite3.Connection) -> list[str]:
    applied: list[str] = []

    if not _table_exists(conn, "user_tags"):
        conn.execute(
            """
            CREATE TABLE user_tags (
                anime_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                tag TEXT,
                liked INTEGER,
                UNIQUE(anime_id, user_id)
            )
            """
        )
        applied.append("user_tags")

    if not _table_exists(conn, "torrents") or not _torrent_columns_ok(conn, "torrents"):
        if _table_exists(conn, "torrents"):
            conn.execute("DROP TABLE torrents")
        conn.execute(
            """
            CREATE TABLE torrents (
                hash TEXT PRIMARY KEY,
                name TEXT,
                trackers TEXT,
                save_path TEXT,
                status TEXT
            )
            """
        )
        applied.append("torrents")

    if not _table_exists(conn, "torrentsIndex") or not _torrent_index_columns_ok(conn):
        if _table_exists(conn, "torrentsIndex"):
            conn.execute("DROP TABLE torrentsIndex")
        conn.execute(
            "CREATE TABLE torrentsIndex (id INTEGER, value TEXT)"
        )
        applied.append("torrentsIndex")

    anime_cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(anime)").fetchall()
    }
    if "last_seen" not in anime_cols:
        conn.execute("ALTER TABLE anime ADD COLUMN last_seen TEXT")
        applied.append("anime.last_seen")

    conn.commit()
    return applied


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path-to-animeData.db>", file=sys.stderr)
        return 2

    path = sys.argv[1]
    conn = sqlite3.connect(path)
    try:
        applied = upgrade(conn)
    finally:
        conn.close()

    if applied:
        print("Applied:", ", ".join(applied))
    else:
        print("No changes needed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
