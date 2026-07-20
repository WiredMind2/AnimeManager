"""Tests for genre domain policies."""

from __future__ import annotations

import pytest

from domain.errors import ValidationError
from domain.policies.genre import (
    format_genre_label,
    genres_contain_all,
    normalize_genre,
    normalize_genres,
)


def test_normalize_genre_single():
    assert normalize_genre(" comedy ") == "Comedy"


def test_normalize_genres_from_comma_string():
    assert normalize_genres("Comedy, Action") == ["Action", "Comedy"]


def test_normalize_genres_dedupes_and_sorts():
    assert normalize_genres(["comedy", "Action", "Comedy"]) == ["Action", "Comedy"]


def test_normalize_genres_rejects_empty():
    with pytest.raises(ValidationError):
        normalize_genres("")
    with pytest.raises(ValidationError):
        normalize_genres([])


def test_normalize_genres_rejects_unknown():
    with pytest.raises(ValidationError):
        normalize_genres("Action,NotAGenre")


def test_format_genre_label_multi():
    assert format_genre_label(["Comedy", "Action"]) == "Action + Comedy"
    assert format_genre_label("Drama") == "Drama"


def test_genres_contain_all():
    assert genres_contain_all(["Action", "Comedy", "Drama"], ["Comedy", "Action"])
    assert not genres_contain_all(["Action"], ["Action", "Comedy"])
