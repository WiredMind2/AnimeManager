"""Tests for :class:`AnimeRepositoryAdapter`."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from adapters.persistence.anime_repository import AnimeRepositoryAdapter
from adapters.persistence.models import Anime
from domain.errors import InfrastructureError


class _SqliteDB:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._lock = threading.RLock()
        self.conn.executescript(
            """
            CREATE TABLE anime (id INTEGER PRIMARY KEY, title TEXT);
            CREATE TABLE title_synonyms (id INTEGER, value TEXT);
            CREATE TABLE torrents (hash TEXT PRIMARY KEY, name TEXT, trackers TEXT,
                                   save_path TEXT, status TEXT);
            CREATE TABLE torrentsIndex (id INTEGER, value TEXT);
            CREATE TABLE animeRelations (id INTEGER, type TEXT, related_id INTEGER);
            CREATE TABLE characters (
                id INTEGER PRIMARY KEY,
                name TEXT,
                picture TEXT,
                description TEXT
            );
            CREATE TABLE characterRelations (
                id INTEGER NOT NULL,
                anime_id INTEGER NOT NULL,
                role TEXT
            );
            CREATE TABLE pictures (
                id INTEGER NOT NULL,
                url TEXT,
                size TEXT
            );
            """
        )
        self.conn.execute("INSERT INTO anime (id, title) VALUES (?, ?)", (1, "Naruto"))
        self.conn.commit()

    @contextmanager
    def get_lock(self):
        with self._lock:
            yield self

    def get(self, item_id: int, *, table: str = "anime"):
        if table == "anime":
            row = self.conn.execute(
                "SELECT id, title FROM anime WHERE id=?", (item_id,)
            ).fetchone()
            if not row:
                return None
            return {"id": row[0], "title": row[1]}
        if table == "characters":
            rows = self.sql(
                "SELECT * FROM characters WHERE id=?", (item_id,), to_dict=True
            )
            if not rows:
                return None
            return rows[0]
        return None

    def sql(
        self,
        query: str,
        params: tuple[Any, ...] = (),
        save: bool = False,
        to_dict: bool = False,
    ):
        cur = self.conn.execute(query, tuple(params))
        if save:
            self.conn.commit()
            return []
        if to_dict:
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        else:
            rows = list(cur.fetchall())
        cur.close()
        return rows


class _FakeDBManager:
    def __init__(self, db: _SqliteDB | None) -> None:
        self._db = db
        self.search_results: list[Any] = []
        self.list_results: tuple[list[Any], Any] = ([], None)
        self.season_results: list[Any] = []

    def get_database(self):
        return self._db

    def search_anime(self, query: str, *, limit: int = 50):
        return self.search_results

    def get_anime_list(self, *, criteria, listrange, hide_rated, user_id):
        return self.list_results

    def list_anime_by_airing_season(self, year, season, *, limit: int = 50):
        return self.season_results


class _FakeConfig:
    def __init__(self) -> None:
        self.settings = {"UI": {"tagcolors": {}}}

    def update_settings(self, updates: dict) -> dict:
        self.settings.update(updates)
        return self.settings


class _FakeAPI:
    def __init__(self, db: _SqliteDB | None = None) -> None:
        self._db = db
        self.characters_by_anime: dict[int, list[Any]] = {}
        self.character_by_id: dict[int, Any] = {}
        self.pictures_by_anime: dict[int, list[dict]] = {}
        self.saved_pictures: list[tuple[int, list[dict]]] = []

    def animeCharacters(self, anime_id: int):
        return iter(self.characters_by_anime.get(anime_id, []))

    def character(self, character_id: int):
        return self.character_by_id.get(character_id)

    def animePictures(self, anime_id: int):
        return self.pictures_by_anime.get(anime_id, [])

    def save_pictures(self, anime_id: int, pictures: list[dict]) -> None:
        self.saved_pictures.append((anime_id, pictures))
        if self._db is None:
            return
        self._db.conn.execute("DELETE FROM pictures WHERE id=?", (anime_id,))
        for pic in pictures:
            self._db.conn.execute(
                "INSERT INTO pictures(id, url, size) VALUES (?, ?, ?)",
                (anime_id, pic["url"], pic["size"]),
            )
        self._db.conn.commit()


@pytest.fixture
def repo():
    db = _SqliteDB()
    db_manager = _FakeDBManager(db)
    config = _FakeConfig()
    return AnimeRepositoryAdapter(db_manager, config), db_manager, db, config


def test_search_maps_results_to_entities(repo):
    adapter, db_manager, _, _ = repo
    db_manager.search_results = [{"id": 5, "title": "Bleach"}]
    results = adapter.search("bleach", limit=10)
    assert len(results) == 1
    assert results[0].id == 5
    assert results[0].title == "Bleach"


def test_search_empty_returns_empty_list(repo):
    adapter, db_manager, _, _ = repo
    db_manager.search_results = []
    assert adapter.search("x") == []


def test_list_anime_with_next_page(repo):
    adapter, db_manager, _, _ = repo
    db_manager.list_results = ([{"id": 1, "title": "A"}], 2)
    items, has_next = adapter.list_anime("all", 0, 50, False, 1)
    assert len(items) == 1
    assert has_next is True


def test_list_anime_empty(repo):
    adapter, db_manager, _, _ = repo
    db_manager.list_results = ([], None)
    items, has_next = adapter.list_anime("all", 0, 50, None, None)
    assert items == []
    assert has_next is False


def test_list_by_airing_season(repo):
    adapter, db_manager, _, _ = repo
    db_manager.season_results = [{"id": 3, "title": "Seasonal"}]
    results = adapter.list_by_airing_season(2024, "WINTER")
    assert results[0].title == "Seasonal"


def test_get_anime_returns_entity(repo):
    adapter, _, _, _ = repo
    entity = adapter.get_anime(1)
    assert entity is not None
    assert entity.id == 1
    assert entity.title == "Naruto"


def test_get_anime_missing_returns_none(repo):
    adapter, _, _, _ = repo
    assert adapter.get_anime(999) is None


def test_get_anime_no_database_returns_none():
    adapter = AnimeRepositoryAdapter(_FakeDBManager(None), _FakeConfig())
    assert adapter.get_anime(1) is None


def test_get_anime_db_exception_returns_none(repo):
    adapter, _, db, _ = repo

    def _boom(*_a, **_k):
        raise RuntimeError("db down")

    db.get = _boom  # type: ignore[method-assign]
    assert adapter.get_anime(1) is None


def test_get_anime_anime_model_instance(repo):
    adapter, _, db, _ = repo
    db.get = lambda anime_id, table="anime": Anime({"id": anime_id, "title": "X"})  # type: ignore[method-assign]
    entity = adapter.get_anime(1)
    assert entity is not None
    assert entity.title == "X"


def test_search_terms_round_trip(repo):
    adapter, _, db, _ = repo
    assert adapter.get_search_terms(1) == []
    assert adapter.add_search_term(1, "Shippuden") is True
    assert adapter.get_search_terms(1) == ["Shippuden"]
    assert adapter.add_search_term(1, "Shippuden") is False
    assert adapter.remove_search_term(1, "Shippuden") is True


def test_add_search_term_no_db_returns_false():
    adapter = AnimeRepositoryAdapter(_FakeDBManager(None), _FakeConfig())
    assert adapter.add_search_term(1, "x") is False


def test_add_search_term_db_error_raises(repo):
    adapter, _, db, _ = repo

    @contextmanager
    def _broken_lock():
        raise sqlite3.OperationalError("locked")

    db.get_lock = _broken_lock  # type: ignore[method-assign]
    with pytest.raises(InfrastructureError):
        adapter.add_search_term(1, "term")


def test_disabled_search_titles_round_trip(repo):
    adapter, _, _, _ = repo
    assert adapter.get_disabled_search_titles(1) == []
    assert adapter.disable_search_title(1, "bad title") is True
    assert adapter.get_disabled_search_titles(1) == ["bad title"]
    assert adapter.disable_search_title(1, "bad title") is False
    assert adapter.enable_search_title(1, "bad title") is True
    assert adapter.get_disabled_search_titles(1) == []


def test_settings_get_and_update(repo):
    adapter, _, _, config = repo
    assert "UI" in adapter.get_settings()
    updated = adapter.update_settings({"foo": "bar"})
    assert updated["foo"] == "bar"
    assert config.settings["foo"] == "bar"


def test_get_relations(repo):
    adapter, _, db, _ = repo
    db.conn.execute(
        "INSERT INTO animeRelations (id, type, related_id) VALUES (1, 'anime', 2)"
    )
    db.conn.commit()
    rows = adapter.get_relations(1, "anime")
    assert len(rows) == 1


def test_get_relations_no_db():
    adapter = AnimeRepositoryAdapter(_FakeDBManager(None), _FakeConfig())
    assert adapter.get_relations(1) == []


def test_get_anime_torrents_parses_json_trackers(repo):
    adapter, _, db, _ = repo
    db.conn.execute(
        "INSERT INTO torrents VALUES (?, ?, ?, ?, ?)",
        ("abc", "Pack", json.dumps(["http://tracker"]), "/save", "complete"),
    )
    db.conn.execute("INSERT INTO torrentsIndex VALUES (?, ?)", (1, "abc"))
    db.conn.commit()
    torrents = adapter.get_anime_torrents(1)
    assert len(torrents) == 1
    assert torrents[0]["hash"] == "abc"
    assert torrents[0]["status"] == "complete"
    assert torrents[0]["trackers"] == ["http://tracker"]
    assert torrents[0]["path"] == "/save"


def test_get_anime_torrents_skips_malformed_rows(repo):
    adapter, _, db, _ = repo
    db.conn.execute("INSERT INTO torrents VALUES ('h', 'n', NULL, NULL, NULL)")
    db.conn.execute("INSERT INTO torrentsIndex VALUES (1, 'h')")
    db.conn.commit()
    assert len(adapter.get_anime_torrents(1)) == 1


def test_ensure_disabled_search_titles_table_raises_when_no_db():
    adapter = AnimeRepositoryAdapter(_FakeDBManager(None), _FakeConfig())
    with pytest.raises(InfrastructureError):
        adapter._ensure_disabled_search_titles_table()


def _seed_character_data(db: _SqliteDB) -> None:
    db.conn.execute(
        "INSERT INTO characters(id, name, picture, description) VALUES (5, 'Hero', 'pic.jpg', 'Bio')"
    )
    db.conn.execute(
        "INSERT INTO characterRelations(id, anime_id, role) VALUES (5, 1, 'main')"
    )
    db.conn.execute(
        "INSERT INTO pictures(id, url, size) VALUES (1, 'https://example.com/l.jpg', 'large')"
    )
    db.conn.commit()


def test_get_characters_returns_joined_rows(repo):
    adapter, _, db, _ = repo
    _seed_character_data(db)
    items = adapter.get_characters(1)
    assert items == [
        {
            "id": 5,
            "name": "Hero",
            "picture": "pic.jpg",
            "description": "Bio",
            "role": "main",
        }
    ]


def test_get_character_includes_animeography(repo):
    adapter, _, db, _ = repo
    _seed_character_data(db)
    payload = adapter.get_character(5)
    assert payload is not None
    assert payload["name"] == "Hero"
    assert payload["animeography"] == [
        {"anime_id": 1, "title": "Naruto", "role": "main"}
    ]


def test_get_anime_pictures(repo):
    adapter, _, db, _ = repo
    _seed_character_data(db)
    pictures = adapter.get_anime_pictures(1)
    assert pictures == [{"url": "https://example.com/l.jpg", "size": "large"}]


def test_refresh_anime_characters_upserts_and_returns(repo):
    adapter, db_manager, db, config = repo
    api = _FakeAPI(db)
    adapter = AnimeRepositoryAdapter(db_manager, config, api=api)
    api.characters_by_anime[1] = [
        SimpleNamespace(
            id=7,
            name="Rival",
            picture="rival.jpg",
            desc="A rival",
            role="Supporting",
        )
    ]
    items = adapter.refresh_anime_characters(1)
    assert items == [
        {
            "id": 7,
            "name": "Rival",
            "picture": "rival.jpg",
            "description": "A rival",
            "role": "supporting",
        }
    ]


def test_refresh_anime_characters_no_api_raises(repo):
    adapter, _, _, _ = repo
    with pytest.raises(InfrastructureError, match="Metadata API not configured"):
        adapter.refresh_anime_characters(1)


def test_refresh_anime_pictures_normalizes_jpg(repo):
    adapter, db_manager, db, config = repo
    api = _FakeAPI(db)
    adapter = AnimeRepositoryAdapter(db_manager, config, api=api)
    api.pictures_by_anime[1] = [
        {
            "jpg": {
                "small_image_url": "https://example.com/s.jpg",
                "image_url": "https://example.com/m.jpg",
                "large_image_url": "https://example.com/l.jpg",
            }
        }
    ]
    pictures = adapter.refresh_anime_pictures(1)
    assert pictures == [
        {"url": "https://example.com/s.jpg", "size": "small"},
        {"url": "https://example.com/m.jpg", "size": "medium"},
        {"url": "https://example.com/l.jpg", "size": "large"},
    ]
