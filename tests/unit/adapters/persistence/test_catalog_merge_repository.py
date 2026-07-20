"""Tests for :class:`CatalogMergeRepository` torrent index handling."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager

from adapters.persistence.catalog_repository import CatalogMergeRepository


class _MergeDB:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._lock = threading.RLock()
        self.issued_sql: list[str] = []
        self.conn.executescript(
            """
            CREATE TABLE anime (id INTEGER PRIMARY KEY, title TEXT);
            CREATE TABLE indexList (
                id INTEGER PRIMARY KEY,
                mal_id INTEGER,
                kitsu_id INTEGER,
                anilist_id INTEGER,
                anidb_id INTEGER
            );
            CREATE TABLE title_synonyms (id INTEGER, value TEXT);
            CREATE TABLE genres (id INTEGER, value TEXT);
            CREATE TABLE pictures (id INTEGER, url TEXT, size TEXT);
            CREATE UNIQUE INDEX uniq_pictures_id_size ON pictures(id, size);
            CREATE TABLE broadcasts (id INTEGER PRIMARY KEY, value TEXT);
            CREATE TABLE animeRelations (id INTEGER, type TEXT, related_id INTEGER);
            CREATE TABLE torrents (
                hash TEXT PRIMARY KEY,
                name TEXT,
                trackers TEXT,
                save_path TEXT,
                status TEXT
            );
            CREATE TABLE torrentsIndex (id INTEGER, value TEXT);
            CREATE TABLE characterRelations (anime_id INTEGER, role TEXT);
            CREATE TABLE user_tags (anime_id INTEGER, tag TEXT);
            """
        )
        self.conn.execute("INSERT INTO anime VALUES (1, 'Canonical')")
        self.conn.execute("INSERT INTO anime VALUES (2, 'Duplicate')")
        self.conn.execute(
            "INSERT INTO indexList VALUES (1, 100, NULL, NULL, NULL)"
        )
        self.conn.execute(
            "INSERT INTO indexList VALUES (2, NULL, 200, NULL, NULL)"
        )
        self.conn.commit()

    @contextmanager
    def get_lock(self):
        with self._lock:
            yield self

    def sql(self, query, params=(), save=False):
        self.issued_sql.append(" ".join(query.split()))
        cur = self.conn.execute(query, params)
        if save:
            self.conn.commit()
        if query.strip().upper().startswith("SELECT"):
            return cur.fetchall()
        self.conn.commit()
        return []

    def save(self):
        self.conn.commit()


def test_merge_repoints_unique_torrents_index_hash():
    db = _MergeDB()
    db.conn.execute(
        "INSERT INTO torrents VALUES ('hash-a', 'A', '[]', '/a', NULL)"
    )
    db.conn.execute("INSERT INTO torrentsIndex VALUES (2, 'hash-a')")
    db.conn.commit()

    CatalogMergeRepository(db).merge(duplicate_id=2, canonical_id=1)

    rows = db.conn.execute("SELECT id, value FROM torrentsIndex").fetchall()
    assert rows == [(1, "hash-a")]
    torrents = db.conn.execute("SELECT hash FROM torrents").fetchall()
    assert torrents == [("hash-a",)]
    assert 2 not in {row[0] for row in db.conn.execute("SELECT id FROM anime").fetchall()}


def test_merge_dedupes_torrents_index_when_canonical_has_same_hash():
    db = _MergeDB()
    db.conn.execute(
        "INSERT INTO torrents VALUES ('shared', 'S', '[]', '/s', NULL)"
    )
    db.conn.execute("INSERT INTO torrentsIndex VALUES (1, 'shared')")
    db.conn.execute("INSERT INTO torrentsIndex VALUES (2, 'shared')")
    db.conn.commit()

    CatalogMergeRepository(db).merge(duplicate_id=2, canonical_id=1)

    rows = db.conn.execute("SELECT id, value FROM torrentsIndex").fetchall()
    assert rows == [(1, "shared")]
    assert db.conn.execute("SELECT COUNT(*) FROM torrents").fetchone()[0] == 1


def test_merge_does_not_issue_torrents_id_sql():
    db = _MergeDB()
    db.conn.execute("INSERT INTO torrentsIndex VALUES (2, 'only-dup')")
    db.conn.commit()

    CatalogMergeRepository(db).merge(duplicate_id=2, canonical_id=1)

    torrent_sql = [sql for sql in db.issued_sql if "torrents" in sql.lower()]
    assert torrent_sql
    assert all("torrentsindex" in sql.lower() for sql in torrent_sql)
    assert not any(
        sql.lower().startswith("update torrents set id")
        or sql.lower().startswith("delete from torrents where id")
        for sql in db.issued_sql
    )


def test_merge_dedupes_pictures_when_canonical_has_same_size():
    db = _MergeDB()
    db.conn.execute(
        "INSERT INTO pictures(id, url, size) VALUES (1, 'https://a/l.jpg', 'large')"
    )
    db.conn.execute(
        "INSERT INTO pictures(id, url, size) VALUES (2, 'https://b/l.jpg', 'large')"
    )
    db.conn.commit()

    CatalogMergeRepository(db).merge(duplicate_id=2, canonical_id=1)

    rows = db.conn.execute("SELECT id, size FROM pictures").fetchall()
    assert rows == [(1, "large")]


def test_merge_dedupes_broadcasts_when_canonical_row_exists():
    db = _MergeDB()
    db.conn.execute("INSERT INTO broadcasts VALUES (1, 'Mon 20:00')")
    db.conn.execute("INSERT INTO broadcasts VALUES (2, 'Tue 21:00')")
    db.conn.commit()

    CatalogMergeRepository(db).merge(duplicate_id=2, canonical_id=1)

    rows = db.conn.execute("SELECT id, value FROM broadcasts").fetchall()
    assert rows == [(1, "Mon 20:00")]


def test_merge_dedupes_genre_when_canonical_has_same_value():
    db = _MergeDB()
    db.conn.execute("INSERT INTO genres VALUES (1, 'Action')")
    db.conn.execute("INSERT INTO genres VALUES (2, 'Action')")
    db.conn.execute("INSERT INTO genres VALUES (2, 'Comedy')")
    db.conn.commit()

    CatalogMergeRepository(db).merge(duplicate_id=2, canonical_id=1)

    rows = db.conn.execute(
        "SELECT id, value FROM genres ORDER BY value"
    ).fetchall()
    assert rows == [(1, "Action"), (1, "Comedy")]


def test_purge_provisional_anime_rows_deletes_negative_pks():
    db = _MergeDB()
    db.conn.execute(
        "INSERT INTO anime VALUES (-1426116332, 'Orphan Higehiro')"
    )
    db.conn.execute(
        "INSERT INTO title_synonyms VALUES (-1426116332, 'Higehiro')"
    )
    db.conn.execute(
        "INSERT INTO genres VALUES (-1426116332, 'Drama')"
    )
    db.conn.commit()

    deleted = CatalogMergeRepository(db).purge_provisional_anime_rows()

    assert deleted == 1
    ids = [row[0] for row in db.conn.execute("SELECT id FROM anime").fetchall()]
    assert -1426116332 not in ids
    assert 1 in ids
    assert (
        db.conn.execute(
            "SELECT COUNT(*) FROM title_synonyms WHERE id < 0"
        ).fetchone()[0]
        == 0
    )


def test_title_repair_prefers_positive_canonical_over_provisional():
    db = _MergeDB()
    db.conn.execute("UPDATE anime SET title='Higehiro' WHERE id=1")
    db.conn.execute(
        "INSERT INTO anime VALUES (-500, 'Higehiro')"
    )
    db.conn.commit()

    merged = CatalogMergeRepository(db)._repair_by_title()

    assert merged == 1
    ids = {row[0] for row in db.conn.execute("SELECT id FROM anime").fetchall()}
    assert 1 in ids
    assert -500 not in ids
    assert db.conn.execute(
        "SELECT title FROM anime WHERE id=1"
    ).fetchone()[0] == "Higehiro"
