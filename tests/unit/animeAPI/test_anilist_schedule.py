"""Unit tests for AniList schedule()."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def AnilistCoWrapper():
    from adapters.api.AnilistCo import AnilistCoWrapper as _W

    return _W


def _make(AnilistCoWrapper):
    inst = object.__new__(AnilistCoWrapper)
    inst.media_fields = ["id", "title"]
    inst.pagination_query = MagicMock()
    inst.pagination_query.add_field = MagicMock(side_effect=lambda field: MagicMock())
    inst.log = MagicMock()
    inst._convertAnime = MagicMock(
        side_effect=lambda media: {"id": media["id"], "title": media["title"]}
    )
    return inst


def test_schedule_yields_current_season_media(AnilistCoWrapper):
    inst = _make(AnilistCoWrapper)
    inst.iterate = MagicMock(
        return_value=iter(
            [
                {"id": 11, "title": "A"},
                {"id": 12, "title": "B"},
            ]
        )
    )

    out = list(inst.schedule(limit=5))
    assert [item["id"] for item in out] == [11, 12]
    inst.iterate.assert_called_once()
    variables = inst.iterate.call_args[0][1]
    assert variables["season"] in {"WINTER", "SPRING", "SUMMER", "FALL"}
    assert isinstance(variables["seasonYear"], int)


def test_schedule_respects_limit(AnilistCoWrapper):
    inst = _make(AnilistCoWrapper)
    inst.iterate = MagicMock(
        return_value=iter({"id": i, "title": f"A{i}"} for i in range(1, 10))
    )

    out = list(inst.schedule(limit=2))
    assert len(out) == 2


def test_anime_characters_returns_empty_list(AnilistCoWrapper):
    inst = _make(AnilistCoWrapper)
    assert inst.animeCharacters(42) == []
