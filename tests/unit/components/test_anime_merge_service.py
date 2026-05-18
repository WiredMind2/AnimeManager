from __future__ import annotations

import sqlite3

from application.services.anime_merge_service import AnimeMergeService


class _SqliteDB:
    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.cur = self.con.cursor()
        self._create_schema()

    def _create_schema(self) -> None:
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
            CREATE TABLE torrentsIndex (id INTEGER, value TEXT);
            CREATE TABLE title_synonyms (id INTEGER, value TEXT);
            CREATE TABLE genres (id INTEGER, value TEXT);
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


def _seed(db: _SqliteDB) -> None:
    db.sql(
        "INSERT INTO anime(id, title, synopsis, episodes) VALUES(?, ?, ?, ?)",
        (1, "Naruto", "short", 12),
        save=True,
    )
    db.sql(
        "INSERT INTO anime(id, title, synopsis, episodes) VALUES(?, ?, ?, ?)",
        (2, "Naruto Shippuden", "much longer synopsis", None),
        save=True,
    )
    db.sql(
        "INSERT INTO indexList(id, mal_id) VALUES(?, ?)",
        (1, 100),
        save=True,
    )
    db.sql(
        "INSERT INTO indexList(id, kitsu_id) VALUES(?, ?)",
        (2, 200),
        save=True,
    )
    db.sql(
        "INSERT INTO torrentsIndex(id, value) VALUES(?, ?)",
        (2, "abc123"),
        save=True,
    )
    db.sql(
        "INSERT INTO title_synonyms(id, value) VALUES(?, ?)",
        (2, "Naruto alt"),
        save=True,
    )
    db.sql(
        "INSERT INTO user_tags(anime_id, user_id, tag, liked) VALUES(?, ?, ?, ?)",
        (2, 4, "WATCHLIST", 1),
        save=True,
    )
    db.sql(
        "INSERT INTO episode_progress("
        "anime_id, user_id, file_id, status, position_seconds, updated_at"
        ") VALUES(?, ?, ?, ?, ?, ?)",
        (2, 4, "ep-0001", "watching", 300.0, "2026-01-01T00:00:00+00:00"),
        save=True,
    )
    db.sql(
        "INSERT INTO anime_torrent_search_memory(anime_id, query) VALUES(?, ?)",
        (2, "naruto subsplease"),
        save=True,
    )
    db.sql(
        "INSERT INTO animeRelations(id, type, name, rel_id) VALUES(?, ?, ?, ?)",
        (2, "anime", "SEQUEL", 1),
        save=True,
    )


def test_merge_from_external_mappings_remaps_user_state():
    db = _SqliteDB()
    _seed(db)
    merger = AnimeMergeService(db)

    result = merger.merge_from_external_mappings(2, [("mal_id", 100)])

    assert result.canonical_id == 2
    # User data from id=1 is minimal, so id=2 keeps ownership.
    assert db.sql("SELECT id FROM anime ORDER BY id") == [(2,)]
    assert db.sql("SELECT value FROM torrentsIndex WHERE id=2") == [("abc123",)]
    assert db.sql("SELECT value FROM title_synonyms WHERE id=2") == [("Naruto alt",)]
    assert db.sql(
        "SELECT tag, liked FROM user_tags WHERE anime_id=? AND user_id=?",
        (2, 4),
    ) == [("WATCHLIST", 1)]
    assert db.sql(
        "SELECT status, position_seconds FROM episode_progress "
        "WHERE anime_id=? AND user_id=? AND file_id=?",
        (2, 4, "ep-0001"),
    ) == [("watching", 300.0)]


def test_conflicting_external_ids_skip_merge():
    db = _SqliteDB()
    db.sql("INSERT INTO anime(id, title) VALUES(?, ?)", (1, "A"), save=True)
    db.sql("INSERT INTO anime(id, title) VALUES(?, ?)", (2, "B"), save=True)
    db.sql(
        "INSERT INTO indexList(id, mal_id, kitsu_id) VALUES(?, ?, ?)",
        (1, 100, 777),
        save=True,
    )
    db.sql(
        "INSERT INTO indexList(id, mal_id, kitsu_id) VALUES(?, ?, ?)",
        (2, 100, 888),
        save=True,
    )
    merger = AnimeMergeService(db)

    merged = merger.merge_two_ids(1, 2)

    assert merged is False
    assert db.sql("SELECT id FROM anime ORDER BY id") == [(1,), (2,)]


def test_backfill_is_idempotent():
    db = _SqliteDB()
    _seed(db)
    # Link duplicate IDs through a shared AniList id.
    db.sql(
        "UPDATE indexList SET anilist_id=? WHERE id=?",
        (500, 1),
        save=True,
    )
    db.sql(
        "UPDATE indexList SET anilist_id=? WHERE id=?",
        (500, 2),
        save=True,
    )
    merger = AnimeMergeService(db)

    first = merger.backfill_existing_duplicates()
    second = merger.backfill_existing_duplicates()

    assert first["merged"] >= 1
    assert second["merged"] == 0


def test_merge_from_external_mappings_empty_returns_skipped():
    db = _SqliteDB()
    merger = AnimeMergeService(db)
    result = merger.merge_from_external_mappings(1, [])
    assert result.canonical_id == 1
    assert result.skipped_reason == "no_mappings"


def test_merge_from_external_mappings_ignores_invalid_entries():
    db = _SqliteDB()
    db.sql("INSERT INTO anime(id, title) VALUES(?, ?)", (5, "Solo"), save=True)
    merger = AnimeMergeService(db)
    result = merger.merge_from_external_mappings(
        5,
        [("not_a_column", 1), ("mal_id", "x"), ("mal_id", 100)],
    )
    assert result.canonical_id == 5
    rows = db.sql("SELECT mal_id FROM indexList WHERE id=?", (5,))
    assert rows == [(100,)]


def test_merge_two_ids_same_id_is_noop():
    db = _SqliteDB()
    merger = AnimeMergeService(db)
    assert merger.merge_two_ids(3, 3) is False


def test_merge_prefers_longer_synopsis_and_fills_empty_fields():
    db = _SqliteDB()
    db.sql(
        "INSERT INTO anime(id, title, synopsis, picture, episodes) "
        "VALUES(?, ?, ?, ?, ?)",
        (1, "Short title", "tiny", None, None),
        save=True,
    )
    db.sql(
        "INSERT INTO anime(id, title, synopsis, picture, episodes) "
        "VALUES(?, ?, ?, ?, ?)",
        (2, "", "much longer synopsis text", "pic.png", 24),
        save=True,
    )
    db.sql("INSERT INTO indexList(id, mal_id) VALUES(?, ?)", (1, 10), save=True)
    db.sql("INSERT INTO indexList(id, mal_id) VALUES(?, ?)", (2, 10), save=True)
    merger = AnimeMergeService(db)
    assert merger.merge_two_ids(1, 2) is True
    row = db.sql(
        "SELECT title, synopsis, picture, episodes FROM anime WHERE id=1"
    )[0]
    assert row[1] == "much longer synopsis text"
    assert row[2] == "pic.png"
    assert row[3] == 24


def test_episode_progress_merge_keeps_newer_timestamp():
    db = _SqliteDB()
    db.sql("INSERT INTO anime(id, title) VALUES(?, ?)", (1, "A"), save=True)
    db.sql("INSERT INTO anime(id, title) VALUES(?, ?)", (2, "B"), save=True)
    db.sql("INSERT INTO indexList(id) VALUES(?)", (1,), save=True)
    db.sql("INSERT INTO indexList(id) VALUES(?)", (2,), save=True)
    db.sql(
        "INSERT INTO episode_progress("
        "anime_id, user_id, file_id, status, position_seconds, updated_at"
        ") VALUES(?, ?, ?, ?, ?, ?)",
        (1, 1, "ep-1", "paused", 10.0, "2026-01-01T00:00:00+00:00"),
        save=True,
    )
    db.sql(
        "INSERT INTO episode_progress("
        "anime_id, user_id, file_id, status, position_seconds, updated_at"
        ") VALUES(?, ?, ?, ?, ?, ?)",
        (2, 1, "ep-1", "watching", 500.0, "2026-06-01T00:00:00+00:00"),
        save=True,
    )
    merger = AnimeMergeService(db)
    assert merger.merge_two_ids(1, 2) is True
    status, pos = db.sql(
        "SELECT status, position_seconds FROM episode_progress "
        "WHERE anime_id=? AND user_id=? AND file_id=?",
        (1, 1, "ep-1"),
    )[0]
    assert status == "watching"
    assert pos == 500.0


def test_merge_logs_on_conflict():
    db = _SqliteDB()
    db.sql("INSERT INTO anime(id, title) VALUES(?, ?)", (1, "A"), save=True)
    db.sql("INSERT INTO anime(id, title) VALUES(?, ?)", (2, "B"), save=True)
    db.sql(
        "INSERT INTO indexList(id, mal_id, kitsu_id) VALUES(?, ?, ?)",
        (1, 1, 100),
        save=True,
    )
    db.sql(
        "INSERT INTO indexList(id, mal_id, kitsu_id) VALUES(?, ?, ?)",
        (2, 1, 200),
        save=True,
    )
    logs: list[tuple] = []
    merger = AnimeMergeService(db, log=lambda cat, msg: logs.append((cat, msg)))
    assert merger.merge_two_ids(1, 2) is False
    assert logs and logs[0][0] == "API_MERGE"
