"""Unit tests for ``application.services.anime_write_service``."""

from __future__ import annotations

from application.services.anime_write_service import (
    AnimeWriteService,
    PersistResult,
    WriteSource,
)
from shared.contracts import AnimeRecord, ProviderName


class _DBManager:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.upserts = []

    def upsert_anime_batch(self, records):
        if self.fail:
            raise RuntimeError("boom")
        self.upserts.append(list(records))
        return len(records)


def _record(anime_id: int, *, title: str = "Title") -> AnimeRecord:
    return AnimeRecord(
        id=anime_id,
        title=title,
        title_synonyms=(title, f"{title} Alt"),
        genres=("Action",),
        source_provider=ProviderName.JIKAN,
    )


def test_persist_records_empty_returns_zero():
    service = AnimeWriteService(db_manager=_DBManager())
    result = service.persist_records([], source=WriteSource.SEARCH)
    assert isinstance(result, PersistResult)
    assert result.persisted == 0
    assert result.errors == []


def test_persist_records_converts_records_and_counts_metadata():
    db = _DBManager()
    service = AnimeWriteService(db_manager=db)

    result = service.persist_records(
        [_record(1, title="Naruto"), _record(2, title="Bleach")],
        source=WriteSource.SEARCH,
    )

    assert result.persisted == 2
    assert result.errors == []
    assert result.metadata_keys_written == {"title_synonyms": 2, "genres": 2}
    assert len(db.upserts) == 1
    first = db.upserts[0][0]
    data, meta = first.save_format()
    assert data["id"] == 1
    assert meta["title_synonyms"] == ["Naruto", "Naruto Alt"]
    assert meta["genres"] == ["Action"]


def test_persist_records_reports_errors():
    service = AnimeWriteService(db_manager=_DBManager(fail=True))
    result = service.persist_records([_record(7)], source=WriteSource.SCHEDULE)
    assert result.persisted == 0
    assert len(result.errors) == 1
    assert "RuntimeError" in result.errors[0]


def test_persist_records_skips_provisional_ids():
    db = _DBManager()
    service = AnimeWriteService(db_manager=db)
    result = service.persist_records(
        [_record(-1426116332, title="Orphan"), _record(2808, title="Real")],
        source=WriteSource.SEARCH,
    )
    assert result.persisted == 1
    assert result.errors == []
    assert len(db.upserts) == 1
    assert len(db.upserts[0]) == 1
    assert db.upserts[0][0].id == 2808


def test_persist_legacy_anime_rejects_provisional_id():
    db = _DBManager()
    service = AnimeWriteService(db_manager=db)
    ok = service.persist_legacy_anime(
        {"id": -99, "title": "Bad"},
        source=WriteSource.STREAM,
    )
    assert ok is False
    assert db.upserts == []


def test_persist_legacy_anime_accepts_dict_payload():
    db = _DBManager()
    service = AnimeWriteService(db_manager=db)
    ok = service.persist_legacy_anime(
        {
            "title": "Cowboy Bebop",
            "title_synonyms": ["Cowboy Bebop", "CB"],
            "genres": ["Action", "Sci-Fi"],
            "episodes": 26,
        },
        source=WriteSource.HYDRATION,
        catalog_id=9,
        external_ids={"mal_id": 1, "noop": 2},
    )
    assert ok is True
    saved = db.upserts[0][0]
    data, meta = saved.save_format()
    assert data["id"] == 9
    assert data["episodes"] == 26
    assert meta["title_synonyms"] == ["Cowboy Bebop", "CB"]
    assert meta["genres"] == ["Action", "Sci-Fi"]
