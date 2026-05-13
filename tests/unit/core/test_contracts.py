"""Tests for `shared.contracts` DTOs."""

from __future__ import annotations

import pytest

from ....shared.contracts import (
    AnimeRecord,
    IngestionResult,
    IngestionStatus,
    ProviderName,
    RelationRecord,
    VALID_ASSET_SIZES,
    VALID_RELATION_TYPES,
)


def test_anime_record_is_frozen():
    rec = AnimeRecord(id=1, title="t")
    with pytest.raises(Exception):
        rec.id = 2  # type: ignore[misc]


def test_anime_record_to_dict_roundtrip():
    rec = AnimeRecord(id=42, title="t", episodes=12)
    out = rec.to_dict()
    assert out["id"] == 42
    assert out["title"] == "t"
    assert out["episodes"] == 12
    assert "external_ids" in out


def test_relation_record_is_frozen():
    rel = RelationRecord(id=1, rel_id=2, type="anime", name="prequel")
    with pytest.raises(Exception):
        rel.type = "manga"  # type: ignore[misc]


def test_ingestion_result_helper():
    r = IngestionResult(
        status=IngestionStatus.PARTIAL,
        failed_providers=2,
        total_providers=5,
    )
    assert r.successful_providers == 3


def test_provider_name_values():
    assert ProviderName.JIKAN.value == "jikan"
    assert ProviderName.ANILIST.value == "anilist"


def test_constants_present():
    assert "anime" in VALID_RELATION_TYPES
    assert "large" in VALID_ASSET_SIZES
