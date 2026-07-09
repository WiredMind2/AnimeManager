"""Tests for genre id/name resolution in persistence metadata."""

from __future__ import annotations

from unittest.mock import MagicMock

from adapters.persistence.genre_metadata import (
    normalize_genre_values_for_store,
    resolve_stored_genre_values,
)


def test_resolve_stored_genre_values_maps_index_ids_to_names():
    db = MagicMock()
    db.sql.return_value = [(5, "Comedy"), (9, "Action")]

    names = resolve_stored_genre_values(db, [5, 9])

    assert names == ["Action", "Comedy"]


def test_resolve_stored_genre_values_keeps_legacy_text_values():
    db = MagicMock()

    names = resolve_stored_genre_values(db, ["Action", "Drama"])

    assert names == ["Action", "Drama"]
    db.sql.assert_not_called()


def test_normalize_genre_values_for_store_maps_names_to_ids():
    db = MagicMock()
    db.sql.side_effect = [
        [(1,)],
        [(5,)],
    ]

    stored = normalize_genre_values_for_store(db, ["comedy"])

    assert stored == [5]


def test_normalize_genre_values_for_store_without_index_table():
    db = MagicMock()
    db.sql.side_effect = RuntimeError("no such table")

    stored = normalize_genre_values_for_store(db, ["Action", "Sci-Fi"])

    assert stored == ["Action", "Sci-Fi"]
