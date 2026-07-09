"""Tests for provider payload conversion helpers."""

from __future__ import annotations

import pytest

import adapters.api.provider_payload as provider_payload
from adapters.api.provider_payload import (
    anime_record_to_legacy_anime,
    anime_to_provider_payload,
    external_ids_from_anime,
    legacy_anime_to_record,
    provider_name_for_api_key,
)
from adapters.persistence.models import Anime
from shared.contracts import AnimeRecord, ProviderName


def test_provider_name_for_api_key_maps_known_keys():
    assert provider_name_for_api_key("mal_id") == ProviderName.JIKAN
    assert provider_name_for_api_key("anilist_id") == ProviderName.ANILIST
    assert provider_name_for_api_key("kitsu_id") == ProviderName.KITSU
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


def test_anime_record_to_legacy_anime_tolerates_setattr_failures(monkeypatch):
    class _BrokenAnime(dict):
        def __setattr__(self, _name, _value):
            raise RuntimeError("blocked")

    monkeypatch.setattr(provider_payload, "Anime", _BrokenAnime)
    record = AnimeRecord(id=7, title="Blocked", title_synonyms=("A",), genres=("B",))
    anime = anime_record_to_legacy_anime(record)
    assert isinstance(anime, _BrokenAnime)
