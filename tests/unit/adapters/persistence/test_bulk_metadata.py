"""Tests for bulk metadata fetch guards."""

from __future__ import annotations

from adapters.persistence.base import BaseDB, _ID_VALUE_METADATA_TABLES
from adapters.persistence.models import Anime


class _BulkMetaDB(BaseDB):
    def __init__(self) -> None:
        super().__init__()
        self.queries: list[str] = []

    def sql(self, query, params=(), save=False, to_dict=False, get_description=False):
        self.queries.append(" ".join(query.split()))
        return []

    def log(self, *args, **kwargs):
        pass


def test_anime_metadata_keys_exclude_torrents():
    anime = Anime(id=1, title="Test")
    assert "torrents" not in anime.metadata_keys
    assert set(anime.metadata_keys).issubset(_ID_VALUE_METADATA_TABLES)


def test_fetch_bulk_metadata_skips_non_id_value_tables():
    db = _BulkMetaDB()
    db._fetch_bulk_metadata([1, 2], ["title_synonyms", "genres", "torrents"])
    assert db.queries
    assert all("torrents" not in q.lower() for q in db.queries)
    assert any("title_synonyms" in q for q in db.queries)
    assert any("genres" in q for q in db.queries)
