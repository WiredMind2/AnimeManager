"""Edge case tests for ``shared.contracts`` ingestion DTOs."""

from __future__ import annotations

import pytest

from shared.contracts import (
    VALID_ASSET_SIZES,
    VALID_RELATION_TYPES,
    AnimeRecord,
    IngestionResult,
    IngestionStatus,
    MediaAssetRecord,
    ProviderName,
    RelationRecord,
)


class TestAnimeRecord:
    def test_defaults(self):
        rec = AnimeRecord(id=1, title="t")
        assert rec.title_synonyms == ()
        assert rec.genres == ()
        assert rec.external_ids == {}
        assert rec.source_provider == ProviderName.UNKNOWN

    def test_external_ids_are_per_instance(self):
        a = AnimeRecord(id=1, title="a")
        b = AnimeRecord(id=2, title="b")
        a.external_ids["mal_id"] = 1
        assert b.external_ids == {}

    def test_frozen(self):
        rec = AnimeRecord(id=1, title="t")
        with pytest.raises(Exception):
            rec.title = "x"  # type: ignore[misc]
        with pytest.raises(Exception):
            rec.episodes = 12  # type: ignore[misc]

    def test_to_dict_preserves_provider(self):
        rec = AnimeRecord(
            id=42,
            title="t",
            source_provider=ProviderName.JIKAN,
            genres=("Action", "Drama"),
        )
        out = rec.to_dict()
        assert out["id"] == 42
        assert out["title"] == "t"
        # asdict returns the raw enum representation
        assert out["source_provider"] in {ProviderName.JIKAN, "jikan"}
        assert out["genres"] == ("Action", "Drama")

    def test_hashable_when_frozen(self):
        rec = AnimeRecord(id=1, title="t")
        # Cannot be hashed because external_ids is a dict (unhashable).
        with pytest.raises(TypeError):
            hash(rec)

    def test_equality_by_fields(self):
        a = AnimeRecord(id=1, title="t")
        b = AnimeRecord(id=1, title="t")
        assert a == b

    def test_inequality_when_field_differs(self):
        a = AnimeRecord(id=1, title="t")
        b = AnimeRecord(id=2, title="t")
        assert a != b


class TestRelationRecord:
    def test_frozen(self):
        rel = RelationRecord(id=1, rel_id=2, type="anime", name="prequel")
        with pytest.raises(Exception):
            rel.id = 99  # type: ignore[misc]

    def test_equality(self):
        a = RelationRecord(id=1, rel_id=2, type="anime", name="sequel")
        b = RelationRecord(id=1, rel_id=2, type="anime", name="sequel")
        assert a == b
        assert hash(a) == hash(b)


class TestMediaAssetRecord:
    def test_construction_and_frozen(self):
        rec = MediaAssetRecord(id=1, url="https://x", size="medium")
        with pytest.raises(Exception):
            rec.size = "small"  # type: ignore[misc]

    def test_size_not_validated_in_dto(self):
        # The DTO accepts any string; validation lives in the application layer.
        MediaAssetRecord(id=1, url="https://x", size="totally-invalid")


class TestIngestionResult:
    def test_successful_providers_floor_zero(self):
        # failed > total should clamp the successful count to zero
        r = IngestionResult(
            status=IngestionStatus.FAILED,
            failed_providers=10,
            total_providers=3,
        )
        assert r.successful_providers == 0

    def test_successful_providers_handles_normal_case(self):
        r = IngestionResult(
            status=IngestionStatus.COMPLETE,
            failed_providers=1,
            total_providers=4,
        )
        assert r.successful_providers == 3

    def test_records_default_independent_per_instance(self):
        a = IngestionResult(status=IngestionStatus.COMPLETE)
        b = IngestionResult(status=IngestionStatus.COMPLETE)
        a.records.append(AnimeRecord(id=1, title="x"))
        assert b.records == []

    def test_errors_default_independent_per_instance(self):
        a = IngestionResult(status=IngestionStatus.COMPLETE)
        b = IngestionResult(status=IngestionStatus.COMPLETE)
        a.errors.append("oops")
        assert b.errors == []

    def test_is_mutable(self):
        r = IngestionResult(status=IngestionStatus.COMPLETE)
        r.failed_providers = 5  # mutable summary is intentional
        assert r.failed_providers == 5


class TestConstants:
    def test_status_values(self):
        assert IngestionStatus.COMPLETE.value == "complete"
        assert IngestionStatus.PARTIAL.value == "partial"
        assert IngestionStatus.FAILED.value == "failed"

    def test_provider_name_values(self):
        assert ProviderName.JIKAN.value == "jikan"
        assert ProviderName.ANILIST.value == "anilist"
        assert ProviderName.KITSU.value == "kitsu"
        assert ProviderName.MAL.value == "myanimelist"
        assert ProviderName.UNKNOWN.value == "unknown"

    def test_provider_name_str_inheritance(self):
        # ProviderName extends `str` so it compares equal to its value.
        assert ProviderName.JIKAN == "jikan"

    def test_valid_relation_types_frozen(self):
        assert isinstance(VALID_RELATION_TYPES, frozenset)
        with pytest.raises(AttributeError):
            VALID_RELATION_TYPES.add("x")  # type: ignore[attr-defined]

    def test_valid_asset_sizes_frozen(self):
        assert isinstance(VALID_ASSET_SIZES, frozenset)
        with pytest.raises(AttributeError):
            VALID_ASSET_SIZES.add("x")  # type: ignore[attr-defined]
