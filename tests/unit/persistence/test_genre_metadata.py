"""Genre metadata reads resolve genresIndex ids to display names."""

import sqlite3

import pytest

from adapters.persistence.base import BaseDB


class _GenreDb(BaseDB):
    def __init__(self, conn):
        super().__init__()
        self._conn = conn

    def sql(self, sql, params=(), save=False, to_dict=False, get_description=False):
        cur = self._conn.execute(sql, params)
        if get_description:
            return cur.fetchall(), cur.description
        return cur.fetchall()


@pytest.fixture
def genre_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE genres (id INTEGER, value TEXT);
        CREATE TABLE genresIndex (id INTEGER PRIMARY KEY, value TEXT);
        INSERT INTO genresIndex(id, value) VALUES (1, 'Action'), (2, 'Comedy');
        INSERT INTO genres(id, value) VALUES (10, '1'), (10, '2');
        INSERT INTO genres(id, value) VALUES (20, 'Slice Of Life');
        """
    )
    return _GenreDb(conn)


def test_fetch_genre_metadata_resolves_index_ids(genre_db):
    resolved = genre_db._fetch_genre_metadata([10, 20])
    assert resolved[10] == ["Action", "Comedy"]
    assert resolved[20] == ["Slice Of Life"]


def test_fetch_genre_metadata_for_id(genre_db):
    assert genre_db._fetch_genre_metadata_for_id(10) == ["Action", "Comedy"]


def test_fetch_bulk_metadata_uses_genre_names(genre_db):
    bulk = genre_db._fetch_bulk_metadata([10], ["genres"])
    assert bulk[10]["genres"] == ["Action", "Comedy"]
