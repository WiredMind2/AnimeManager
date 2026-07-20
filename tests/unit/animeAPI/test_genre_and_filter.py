"""Provider unit tests for multi-genre AND filtering."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def AnilistCoWrapper():
    from adapters.api.AnilistCo import AnilistCoWrapper as _W

    return _W


def test_anilist_genre_and_post_filters(AnilistCoWrapper):
    inst = object.__new__(AnilistCoWrapper)
    rows = [
        {"id": 1, "genres": ["Action", "Comedy"]},
        {"id": 2, "genres": ["Action"]},
        {"id": 3, "genres": ["Action", "Comedy", "Drama"]},
    ]

    def fake_iterate(query, variables):
        assert variables["genres"] == ["Action", "Comedy"]
        yield from rows

    inst.iterate = fake_iterate
    inst.pagination_query = SimpleNamespace(add_field=lambda field: field)
    inst.media_fields = []
    inst._convertAnime = MagicMock(
        side_effect=lambda media: {"id": media["id"], "title": f"t{media['id']}"}
    )

    results = list(AnilistCoWrapper.genre(inst, ["Action", "Comedy"], limit=10))
    assert [r["id"] for r in results] == [1, 3]


@pytest.fixture
def KitsuIoWrapper():
    from adapters.api.KitsuIo import KitsuIoWrapper as _W

    return _W


def test_kitsu_genre_and_post_filters(KitsuIoWrapper, monkeypatch):
    inst = object.__new__(KitsuIoWrapper)
    keep = SimpleNamespace(
        genres=[{"name": "Action"}, {"name": "Comedy"}],
    )
    drop = SimpleNamespace(genres=[{"name": "Action"}])

    class FakeSession:
        def iterate(self, resource, modifier):
            _ = (resource, modifier)
            yield keep
            yield drop

    inst.s = FakeSession()
    inst._ANIME_INCLUSION = object()
    inst._convertAnime = MagicMock(
        side_effect=lambda raw: {"id": id(raw), "title": "ok"}
    )

    # Filter(...) + inclusion needs Filter to be importable; patch Filter to identity-ish.
    import adapters.api.KitsuIo as mod

    class FakeFilter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __add__(self, other):
            return self

    monkeypatch.setattr(mod, "Filter", FakeFilter)

    results = list(KitsuIoWrapper.genre(inst, ["Action", "Comedy"], limit=10))
    assert len(results) == 1
    assert results[0]["title"] == "ok"
