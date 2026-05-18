"""Additional merge edge cases for :class:`AnimeMergeService`."""

from __future__ import annotations

import sqlite3

from application.services.anime_merge_service import AnimeMergeService


class _SqliteDB:
    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.cur = self.con.cursor()
        self.cur.executescript(
            """
            CREATE TABLE anime (
                id INTEGER PRIMARY KEY,
                title TEXT,
                picture TEXT,
                date_from INTEGER,
                date_to INTEGER,
                synopsis TEXT,
                episodes INTEGER,
                duration INTEGER,
                rating TEXT,
                status TEXT,
                broadcast TEXT,
                trailer TEXT
            );
            CREATE TABLE indexList (
                id INTEGER PRIMARY KEY,
                mal_id INTEGER,
                kitsu_id INTEGER,
                anilist_id INTEGER,
                anidb_id INTEGER
            );
            CREATE TABLE user_tags (
                anime_id INTEGER,
                user_id INTEGER,
                tag TEXT,
                liked INTEGER
            );
            CREATE TABLE episode_progress (
                anime_id INTEGER,
                user_id INTEGER,
                file_id TEXT,
                status TEXT,
                position_seconds REAL,
                updated_at TEXT
            );
            CREATE TABLE torrentsIndex (id INTEGER, value TEXT);
            CREATE TABLE title_synonyms (id INTEGER, value TEXT);
            CREATE TABLE genres (id INTEGER, value TEXT);
            CREATE TABLE anime_torrent_search_memory (
                anime_id INTEGER PRIMARY KEY,
                query TEXT
            );
            CREATE TABLE animeRelations (
                id INTEGER,
                type TEXT,
                name TEXT,
                rel_id INTEGER
            );
            CREATE TABLE characterRelations (
                id INTEGER,
                anime_id INTEGER,
                role TEXT
            );
            """
        )
        self.con.commit()

    def sql(self, query, params=(), save=False):
        self.cur.execute(query, params)
        if save:
            self.con.commit()
        if query.lstrip().upper().startswith("SELECT"):
            return self.cur.fetchall()
        return []


def test_merge_from_external_links_multiple_ids():
    db = _SqliteDB()
    db.sql("INSERT INTO anime(id, title) VALUES(?, ?)", (1, "A"), save=True)
    db.sql("INSERT INTO anime(id, title) VALUES(?, ?)", (2, "B"), save=True)
    db.sql("INSERT INTO indexList(id, mal_id) VALUES(?, ?)", (1, 50), save=True)
    db.sql("INSERT INTO indexList(id, mal_id) VALUES(?, ?)", (2, 50), save=True)
    merger = AnimeMergeService(db)
    result = merger.merge_from_external_mappings(2, [("mal_id", 50)])
    assert result.canonical_id in (1, 2)
    assert len(db.sql("SELECT id FROM anime")) == 1


def test_merge_user_tags_keeps_existing_tag():
    db = _SqliteDB()
    db.sql("INSERT INTO anime(id, title) VALUES(?, ?)", (1, "A"), save=True)
    db.sql("INSERT INTO anime(id, title) VALUES(?, ?)", (2, "B"), save=True)
    db.sql("INSERT INTO indexList(id) VALUES(?)", (1,), save=True)
    db.sql("INSERT INTO indexList(id) VALUES(?)", (2,), save=True)
    db.sql(
        "INSERT INTO user_tags(anime_id, user_id, tag, liked) VALUES(?, ?, ?, ?)",
        (1, 7, "WATCHING", 0),
        save=True,
    )
    db.sql(
        "INSERT INTO user_tags(anime_id, user_id, tag, liked) VALUES(?, ?, ?, ?)",
        (2, 7, "", 1),
        save=True,
    )
    merger = AnimeMergeService(db)
    assert merger.merge_two_ids(1, 2) is True
    tag, liked = db.sql(
        "SELECT tag, liked FROM user_tags WHERE anime_id=? AND user_id=?",
        (1, 7),
    )[0]
    assert tag == "WATCHING"
    assert liked == 0


def test_merge_skips_when_index_row_missing():
    db = _SqliteDB()
    db.sql("INSERT INTO anime(id, title) VALUES(?, ?)", (1, "A"), save=True)
    merger = AnimeMergeService(db)
    assert merger.merge_two_ids(1, 99) is False


def test_backfill_stops_when_no_progress():
    db = _SqliteDB()
    db.sql("INSERT INTO anime(id, title) VALUES(?, ?)", (1, "A"), save=True)
    db.sql("INSERT INTO indexList(id, anilist_id) VALUES(?, ?)", (1, 100), save=True)
    merger = AnimeMergeService(db)
    stats = merger.backfill_existing_duplicates(max_passes=2)
    assert stats["merged"] == 0
