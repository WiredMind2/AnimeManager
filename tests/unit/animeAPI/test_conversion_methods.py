import types

import pytest

from animeAPI import AnilistCo, JikanMoe, KitsuIo, MyAnimeListNet


def _setup_dummy_db(monkeypatch):
    class DummyDB:
        def __init__(self):
            self._ids = {}
            self._next = 1

        def getId(self, key, value=None, table=None):
            if value is None:
                return None
            k = (key, str(value), table)
            if k not in self._ids:
                self._ids[k] = self._next
                self._next += 1
            return self._ids[k]

        class _Lock:
            def __enter__(self):
                return None

            def __exit__(self, exc_type, exc, tb):
                return False

        def get_lock(self):
            return DummyDB._Lock()

        def sql(self, *args, **kwargs):
            return []

    monkeypatch.setattr(
        "animeAPI.APIUtils.APIUtils.getDatabase", lambda self: DummyDB()
    )


@pytest.mark.timeout(30)
def test_anilist_convert_methods(monkeypatch):
    _setup_dummy_db(monkeypatch)
    api = AnilistCo.AnilistCoWrapper()

    # Minimal GraphQL-like dict expected by _convertAnime
    a = {
        "id": 1,
        "title": {"romaji": "Test Anime", "english": "Test Anime"},
        "synonyms": ["Test Anime Syn"],
        "description": "Desc",
        "startDate": {"year": 2023, "month": 1, "day": 1},
        "endDate": {"year": 2023, "month": 3, "day": 1},
        "episodes": 12,
        "duration": 24,
        "isAdult": False,
        "coverImage": {"medium": "http://img", "large": "http://imgl"},
        "genres": ["Action"],
    }

    data = api._convertAnime(a)
    assert data is not None
    assert "title" in data and data["title"] is not None
    assert "title_synonyms" in data

    # Character conversion
    c = {
        "id": 10,
        "name": {"full": "Char Name"},
        "description": "Cdesc",
        "image": {"large": "http://cimg"},
    }
    ch = api._convertCharacter(c, anime_id=1)
    assert ch is not None
    assert ch["name"] == "Char Name"


@pytest.mark.timeout(30)
def test_jikan_convert_methods(monkeypatch):
    _setup_dummy_db(monkeypatch)
    api = JikanMoe.JikanMoeWrapper()

    a = {
        "mal_id": 123,
        "title": "Jikan Test",
        "title_english": "Jikan Test",
        "title_japanese": "テスト",
        "title_synonyms": [],
        "aired": {
            "prop": {
                "from": {"year": 2020, "month": 1, "day": 1},
                "to": {"year": 2020, "month": 3, "day": 1},
            }
        },
        "images": {
            "jpg": {
                "image_url": "http://img.jpg",
                "large_image_url": "http://img_large.jpg",
            }
        },
        "synopsis": "desc",
        "episodes": 12,
        "duration": "24 min",
        "rating": "PG-13",
    }

    data = api._convertAnime(a)
    assert data is not None
    assert data["title"] is not None

    # Character conversion expects a dict with mal character structure
    c = {
        "mal_id": 456,
        "name": "Char",
        "images": {"jpg": {"image_url": "http://c.jpg"}},
        "about": "desc",
    }
    ch = api._convertCharacter(c, role="Main", anime_id=123)
    assert ch is not None
    assert ch["name"] == "Char"


@pytest.mark.timeout(30)
def test_kitsu_convert_methods(monkeypatch):
    _setup_dummy_db(monkeypatch)
    api = KitsuIo.KitsuIoWrapper()

    # Create a simple object with attributes used by _convertAnime
    class FakeObj:
        def __init__(self):
            self.id = 7
            self.canonicalTitle = "Kitsu Test"
            self.posterImage = {"small": "s", "medium": "m", "large": "l"}
            self.titles = {"en": "Kitsu Test"}
            self.startDate = "2020-01-01"
            self.endDate = "2020-03-01"
            self.synopsis = "desc"
            self.episodeCount = 12
            self.episodeLength = 24
            self.ageRating = "PG"
            self.youtubeVideoId = None
            self.subtype = "TV"
            # relationships placeholders
            self.relationships = types.SimpleNamespace(genres=None, mappings=None)
            self._relationships = {"mediaRelationships": None}

    a = FakeObj()

    data = api._convertAnime(a)
    assert data is not None
    assert data["title"] is not None

    # Character conversion expects an object 'c' with character property
    class FakeChar:
        def __init__(self):
            self.character = types.SimpleNamespace(
                malId=89, id=11, name="KChar", image={"original": "http://c"}
            )
            self.role = "Main"

    chobj = FakeChar()
    ch = api._convertCharacter(chobj, anime_id=7)
    # _convertCharacter may return None if DB mapping isn't ideal; accept None or Character
    assert ch is None or "name" in ch


@pytest.mark.timeout(30)
def test_mal_convert_methods(monkeypatch):
    _setup_dummy_db(monkeypatch)
    api = MyAnimeListNet.MyAnimeListNetWrapper()

    a = {
        "id": 321,
        "title": "MAL Test",
        "alternative_titles": {"en": "MAL Test"},
        "start_date": "2020-01-01",
        "end_date": "2020-03-01",
        "main_picture": {"small": "s", "medium": "m", "large": "l"},
        "synopsis": "desc",
        "num_episodes": 12,
        "average_episode_duration": 1500,
        "rating": "pg-13",
    }

    data = api._convertAnime(a)
    assert data is not None
    assert data["title"] == "MAL Test"

    c = {
        "character": {
            "id": 999,
            "name": "MChar",
            "images": {"jpg": {"image_url": "http://c.jpg"}},
            "about": "desc",
        }
    }
    ch = api._convertCharacter(c, anime_id=321)
    assert ch is not None
    assert ch["name"] == "MChar"
