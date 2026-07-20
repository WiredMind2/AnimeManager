"""Tests for provider payload conversion helpers."""

from __future__ import annotations

import pytest

import adapters.api.provider_payload as provider_payload
from adapters.api.provider_payload import (
    anime_record_to_legacy_anime,
    anime_to_provider_payload,
    external_ids_from_anime,
    legacy_anime_to_record,
    payload_to_anime_record,
    provider_name_for_api_key,
)
from adapters.persistence.models import Anime
from shared.contracts import AnimeRecord, ProviderAnimePayload, ProviderName, payload_fingerprint


def test_provider_name_for_api_key_maps_known_keys():
    assert provider_name_for_api_key("mal_id") == ProviderName.JIKAN
    assert provider_name_for_api_key("anilist_id") == ProviderName.ANILIST
    assert provider_name_for_api_key("kitsu_id") == ProviderName.KITSU
    assert provider_name_for_api_key("anidb_id") == ProviderName.ANIDB
    assert provider_name_for_api_key("unknown") == ProviderName.UNKNOWN


def test_external_ids_from_anime_filters_unknown_keys():
    out = external_ids_from_anime(
        Anime(),
        index_external_ids={"mal_id": 5, "foo": 1},
        primary_api_key="anilist_id",
        primary_external_id=8,
    )
    assert out == {"mal_id": 5, "anilist_id": 8}


def test_anime_to_provider_payload_normalizes_metadata():
    anime = Anime()
    anime.id = 11
    anime.title = "Steins;Gate"
    anime.title_synonyms = ["Steins Gate", ""]
    anime.genres = ["Sci-Fi", None]
    anime.status = "FINISHED"

    payload = anime_to_provider_payload(
        anime,
        source_provider=ProviderName.JIKAN,
        external_ids={"mal_id": 9253, "bad": "ignored"},
    )

    assert payload.title == "Steins;Gate"
    assert payload.title_synonyms == ("Steins Gate",)
    assert payload.genres == ("Sci-Fi",)
    assert payload.external_ids == {"mal_id": 9253}
    assert payload.source_provider == ProviderName.JIKAN


def test_anime_record_to_legacy_anime_copies_metadata():
    record = AnimeRecord(
        id=22,
        title="Samurai Champloo",
        title_synonyms=("SamCham",),
        genres=("Action", "Adventure"),
        source_provider=ProviderName.ANILIST,
    )
    anime = anime_record_to_legacy_anime(record)
    data, meta = anime.save_format()
    assert data["id"] == 22
    assert data["title"] == "Samurai Champloo"
    assert meta["title_synonyms"] == ["SamCham"]
    assert meta["genres"] == ["Action", "Adventure"]


def test_legacy_anime_to_record_supports_dict_and_catalog_override():
    record = legacy_anime_to_record(
        {
            "id": "99",
            "title": "Monster",
            "title_synonyms": ("Monster TV",),
            "genres": ["Drama", "Mystery"],
            "episodes": "74",
        },
        catalog_id=77,
        external_ids={"anilist_id": "19", "junk": "x"},
    )
    assert record is not None
    assert record.id == 77
    assert record.title == "Monster"
    assert record.episodes == 74
    assert record.title_synonyms == ("Monster TV",)
    assert record.genres == ("Drama", "Mystery")
    assert record.external_ids == {"anilist_id": 19}


def test_legacy_anime_to_record_handles_invalid_scalars_and_unknown_ids():
    class _LegacyAnime:
        id = "not-an-int"
        title = "X"
        synopsis = "  "
        episodes = "NaN"
        duration = "??"
        status = " "
        rating = "R"
        date_from = "bad"
        date_to = "also-bad"
        picture = "  "
        trailer = None
        broadcast = " "
        title_synonyms = "Alias"
        genres = "Action"

    assert legacy_anime_to_record(_LegacyAnime(), external_ids={"mal_id": "bad"}) is None

    record = legacy_anime_to_record(
        _LegacyAnime(),
        catalog_id=15,
        external_ids={"mal_id": "44", "unknown": "ignored"},
    )
    assert record is not None
    assert record.id == 15
    assert record.source_provider == ProviderName.JIKAN
    assert record.episodes is None
    assert record.duration is None
    assert record.status is None
    assert record.rating == "R"
    assert record.picture is None
    assert record.title_synonyms == ("Alias",)
    assert record.genres == ("Action",)


def test_anime_to_provider_payload_reads_schedule_external_ids():
    anime = Anime()
    anime.title = "Schedule Row"
    anime._schedule_external_ids = {"anilist_id": 42, "mal_id": 7}

    payload = anime_to_provider_payload(anime)

    assert payload.external_ids == {"anilist_id": 42, "mal_id": 7}
    assert payload.title == "Schedule Row"


def test_anime_to_provider_payload_reads_pending_pictures():
    anime = Anime()
    anime.title = "Cover Test"
    anime._schedule_external_ids = {"mal_id": 1}
    anime._pending_pictures = [
        {"url": "http://x/small.jpg", "size": "small"},
        {"url": "", "size": "large"},
        {"url": "http://x/large.jpg", "size": "large", "width": 400},
    ]

    payload = anime_to_provider_payload(anime)

    assert len(payload.picture_variants) == 2
    assert payload.picture_variants[0]["url"] == "http://x/small.jpg"
    assert payload.picture_variants[1]["width"] == 400


def test_payload_to_anime_record_materializes_catalog_row():
    payload = ProviderAnimePayload(
        title="Monster",
        external_ids={"mal_id": 19},
        title_synonyms=("Monster TV",),
        genres=("Drama",),
        source_provider=ProviderName.JIKAN,
        picture_variants=({"url": "http://x.jpg", "size": "medium"},),
    )

    record = payload_to_anime_record(
        payload,
        77,
        external_ids={"mal_id": 19, "anilist_id": 5},
    )

    assert record.id == 77
    assert record.title == "Monster"
    assert record.external_ids == {"mal_id": 19, "anilist_id": 5}
    assert record.title_synonyms == ("Monster TV",)
    assert record.picture_variants[0]["size"] == "medium"


def test_payload_fingerprint_prefers_external_ids():
    payload = ProviderAnimePayload(
        title="X",
        external_ids={"mal_id": 1},
        source_provider=ProviderName.JIKAN,
    )
    assert payload_fingerprint(payload) == ("ext", ("mal_id", 1))


def test_anime_record_to_legacy_anime_tolerates_setattr_failures(monkeypatch):
    class _BrokenAnime(dict):
        def __setattr__(self, _name, _value):
            raise RuntimeError("blocked")

    monkeypatch.setattr(provider_payload, "Anime", _BrokenAnime)
    record = AnimeRecord(id=7, title="Blocked", title_synonyms=("A",), genres=("B",))
    anime = anime_record_to_legacy_anime(record)
    assert isinstance(anime, _BrokenAnime)
