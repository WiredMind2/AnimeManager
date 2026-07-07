"""Tests for character→anime relation persistence."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest

from adapters.api.APIUtils import APIUtils


class _Database:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._lock = threading.RLock()
        self.conn.execute(
            """
            CREATE TABLE characterRelations (
                id INTEGER NOT NULL,
                anime_id INTEGER NOT NULL,
                role TEXT
            )
            """
        )
        self.conn.commit()

    @contextmanager
    def get_lock(self):
        with self._lock:
            yield self

    def sql(self, query: str, params: tuple[Any, ...] = (), save: bool = False):
        cur = self.conn.execute(query, params)
        if save:
            self.conn.commit()
            return []
        return list(cur.fetchall())


@pytest.fixture
def api_utils():
    db = _Database()
    inst = APIUtils.__new__(APIUtils)
    inst.database = db
    return inst, db


def test_save_animeography_inserts_new_relation(api_utils):
    api, db = api_utils
    api.save_animeography(7, {42: "main"})

    rows = db.sql("SELECT id, anime_id, role FROM characterRelations")
    assert rows == [(7, 42, "main")]


def test_save_animeography_updates_existing_role(api_utils):
    api, db = api_utils
    api.save_animeography(7, {42: "main"})
    api.save_animeography(7, {42: "supporting"})

    rows = db.sql("SELECT id, anime_id, role FROM characterRelations")
    assert rows == [(7, 42, "supporting")]


def test_save_animeography_persists_multiple_anime(api_utils):
    api, db = api_utils
    api.save_animeography(7, {42: "main", 99: "supporting"})

    rows = db.sql("SELECT id, anime_id, role FROM characterRelations ORDER BY anime_id")
    assert rows == [(7, 42, "main"), (7, 99, "supporting")]
