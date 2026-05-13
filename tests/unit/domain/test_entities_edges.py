"""Edge case tests for ``domain.entities`` (AnimeEntity, TorrentEntity, from_legacy_anime).

Focus areas:
* slots-based dataclass behaviour and defensive defaults.
* ``from_legacy_anime`` coercion from dicts, mappings, attribute-bearing objects, ``None``.
* Boundary numeric handling, fall-through to legacy ``like``/``liked`` boolean fields.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from domain.entities import AnimeEntity, TorrentEntity, from_legacy_anime


class TestAnimeEntityDefaults:
    def test_minimal_required_fields_only(self):
        entity = AnimeEntity(id=1, title="x")
        assert entity.title_synonyms == []
        assert entity.genres == []
        assert entity.picture is None
        assert entity.liked is None

    def test_default_lists_are_per_instance(self):
        a = AnimeEntity(id=1, title="a")
        b = AnimeEntity(id=2, title="b")
        a.genres.append("Action")
        assert b.genres == []

    def test_supports_unicode_and_long_titles(self):
        long_title = "ナ" * 5000
        entity = AnimeEntity(id=1, title=long_title)
        assert len(entity.title) == 5000

    def test_negative_dates_allowed(self):
        entity = AnimeEntity(id=1, title="t", date_from=-1, date_to=-100000)
        assert entity.date_from == -1
        assert entity.date_to == -100000

    def test_zero_id_allowed(self):
        AnimeEntity(id=0, title="")


class TestTorrentEntityDefaults:
    def test_minimal_required_fields_only(self):
        torrent = TorrentEntity(link="magnet:?xt=urn:btih:abc", name="t")
        assert torrent.size == 0
        assert torrent.seeds == 0
        assert torrent.leech == 0
        assert torrent.hash is None


class TestFromLegacyAnime:
    def test_returns_zero_id_when_missing(self):
        e = from_legacy_anime({})
        assert e.id == 0
        assert e.title == ""

    def test_attribute_object_fallback(self):
        obj = SimpleNamespace(
            id=12,
            title="t",
            picture="p.jpg",
            title_synonyms=["alt"],
            genres=["Action"],
            liked=True,
        )

        e = from_legacy_anime(obj)
        assert e.id == 12
        assert e.title == "t"
        assert e.picture == "p.jpg"
        assert e.title_synonyms == ["alt"]
        assert e.genres == ["Action"]
        assert e.liked is True

    def test_dict_takes_priority_over_attributes(self):
        class Obj:
            def __init__(self):
                self.id = 99
                self.title = "old"

            def __iter__(self):
                return iter({"id": 1, "title": "new"}.items())

        e = from_legacy_anime(Obj())
        assert e.id == 1
        assert e.title == "new"

    def test_string_id_is_coerced_to_int(self):
        e = from_legacy_anime({"id": "42", "title": "x"})
        assert e.id == 42

    def test_invalid_id_string_raises_value_error(self):
        with pytest.raises(ValueError):
            from_legacy_anime({"id": "not a number", "title": "x"})

    def test_title_none_becomes_empty_string(self):
        e = from_legacy_anime({"id": 1, "title": None})
        assert e.title == ""

    def test_title_synonyms_none_becomes_empty_list(self):
        e = from_legacy_anime({"id": 1, "title": "x", "title_synonyms": None})
        assert e.title_synonyms == []

    def test_genres_none_becomes_empty_list(self):
        e = from_legacy_anime({"id": 1, "title": "x", "genres": None})
        assert e.genres == []

    def test_legacy_like_falsy_becomes_false(self):
        e = from_legacy_anime({"id": 1, "title": "x", "like": 0})
        assert e.liked is False

    def test_legacy_like_truthy_becomes_true(self):
        e = from_legacy_anime({"id": 1, "title": "x", "like": 1})
        assert e.liked is True

    def test_liked_falls_back_to_liked_field(self):
        e = from_legacy_anime({"id": 1, "title": "x", "liked": True})
        assert e.liked is True

    def test_both_none_yields_none_liked(self):
        e = from_legacy_anime({"id": 1, "title": "x"})
        assert e.liked is None

    def test_unsupported_input_yields_zero_anime(self):
        e = from_legacy_anime(42)
        assert e.id == 0
        assert e.title == ""

    def test_none_input_yields_zero_anime(self):
        e = from_legacy_anime(None)
        assert e.id == 0
        assert e.title == ""

    def test_synopsis_and_status_preserved(self):
        e = from_legacy_anime(
            {
                "id": 5,
                "title": "t",
                "synopsis": "a short summary",
                "status": "FINISHED",
                "episodes": 12,
                "rating": "R+",
            }
        )
        assert e.synopsis == "a short summary"
        assert e.status == "FINISHED"
        assert e.episodes == 12
        assert e.rating == "R+"
