"""Tests for anime metadata completeness policy."""

from domain.entities import AnimeEntity
from domain.policies.anime_metadata import is_anime_metadata_missing


def test_complete_entity_is_not_missing():
    entity = AnimeEntity(
        id=42,
        title="Full Metal",
        title_synonyms=["Fullmetal Alchemist", "Hagane no Renkinjutsushi"],
    )
    assert is_anime_metadata_missing(entity) is False


def test_title_without_synonyms_is_missing():
    entity = AnimeEntity(id=42, title="Full Metal")
    assert is_anime_metadata_missing(entity) is True


def test_empty_title_is_missing():
    entity = AnimeEntity(id=42, title="")
    assert is_anime_metadata_missing(entity) is True


def test_whitespace_title_is_missing():
    entity = AnimeEntity(id=42, title="   ")
    assert is_anime_metadata_missing(entity) is True


def test_zero_id_uses_catalog_id():
    entity = AnimeEntity(id=0, title="")
    assert is_anime_metadata_missing(entity, catalog_id=1932) is True


def test_zero_id_with_title_but_no_synonyms_is_missing():
    entity = AnimeEntity(id=0, title="Recovered")
    assert is_anime_metadata_missing(entity, catalog_id=1932) is True


def test_zero_id_with_title_and_synonyms_is_not_missing():
    entity = AnimeEntity(
        id=0,
        title="Recovered",
        title_synonyms=["Alt"],
    )
    assert is_anime_metadata_missing(entity, catalog_id=1932) is False


def test_none_entity_without_catalog_id_is_not_missing():
    assert is_anime_metadata_missing(None) is False


def test_none_entity_with_catalog_id_is_missing():
    assert is_anime_metadata_missing(None, catalog_id=1932) is True


def test_invalid_catalog_id_is_not_missing():
    entity = AnimeEntity(id=0, title="")
    assert is_anime_metadata_missing(entity, catalog_id=0) is False
