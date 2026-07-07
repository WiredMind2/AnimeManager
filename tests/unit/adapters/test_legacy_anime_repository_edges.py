"""Edge-case tests for detail-tier repository reads."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest

from adapters.legacy.runtime import LegacyAnimeRepositoryAdapter
from domain.errors import InfrastructureError, NotFoundError


class _Database:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._lock = threading.RLock()
        self.conn.executescript(
            """
            CREATE TABLE anime (
                id INTEGER PRIMARY KEY,
                title TEXT,
                date_from INTEGER,
                date_to INTEGER,
                status TEXT,
                episodes INTEGER,
                last_seen TEXT
            );
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
            CREATE TABLE indexList (
                id INTEGER PRIMARY KEY,
                mal_id INTEGER
            );
            """
        )
        self.conn.commit()

    @contextmanager
    def get_lock(self):
        with self._lock:
            yield self

    def sql(
        self,
        query: str,
        params: tuple[Any, ...] = (),
        save: bool = False,
        to_dict: bool = False,
    ):
        cur = self.conn.execute(query, params)
        if save:
            self.conn.commit()
            return []
        rows = cur.fetchall()
        if not to_dict:
            return rows
        cols = [d[0] for d in cur.description or []]
        return [dict(zip(cols, row)) for row in rows]

    def get(self, item_id: int, table: str = "anime"):
        rows = self.sql(f"SELECT * FROM {table} WHERE id=?", (item_id,), to_dict=True)
        if not rows:
            return None
        return rows[0]


class _Runtime:
    def __init__(self, db: _Database) -> None:
        self.database = db
        self.api = MagicMock()


@pytest.fixture
def adapter():
    db = _Database()
    db.conn.execute(
        "INSERT INTO anime(id, title, date_from, status, episodes) VALUES (1, 'Test', ?, 'AIRING', 12)",
        (int((__import__('datetime').datetime.now(__import__('datetime').timezone.utc) - __import__('datetime').timedelta(days=10)).timestamp()),),
    )
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
    return LegacyAnimeRepositoryAdapter(_Runtime(db)), db


def test_get_characters_returns_joined_rows(adapter):
    repo, _ = adapter
    items = repo.get_characters(1)
    assert items == [
        {
            "id": 5,
            "name": "Hero",
            "picture": "pic.jpg",
            "description": "Bio",
            "role": "main",
        }
    ]


def test_get_character_includes_animeography(adapter):
    repo, _ = adapter
    payload = repo.get_character(5)
    assert payload is not None
    assert payload["name"] == "Hero"
    assert payload["animeography"] == [
        {"anime_id": 1, "title": "Test", "role": "main"}
    ]


def test_get_anime_pictures(adapter):
    repo, _ = adapter
    assert repo.get_anime_pictures(1) == [
        {"url": "https://example.com/l.jpg", "size": "large"}
    ]


def test_get_anime_enriches_airing_lines(adapter):
    repo, _ = adapter
    entity = repo.get_anime(1)
    assert entity is not None
    assert isinstance(entity.airing_lines, list)


def test_refresh_anime_characters_delegates_to_api(adapter):
    repo, _ = adapter

    class _Char:
        id = 9
        name = "New"
        picture = None
        desc = None
        animeography = {1: "supporting"}

    repo._runtime.api.animeCharacters.return_value = [_Char()]

    items = repo.refresh_anime_characters(1)
    assert len(items) >= 1
    repo._runtime.api.animeCharacters.assert_called_once_with(1)


def test_refresh_character_not_found(adapter):
    repo, _ = adapter
    repo._runtime.api.character.return_value = None
    with pytest.raises(NotFoundError):
        repo.refresh_character(404)
