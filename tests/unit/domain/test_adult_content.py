"""Tests for adult torrent heuristics."""

from __future__ import annotations

import pytest

from domain.policies.adult_content import is_adult_torrent


@pytest.mark.parametrize(
    ("name", "engine_url", "expected"),
    [
        ("SubsPlease Naruto 1080p", "", False),
        ("[SubsPlease] Hentai Collection 1080p", "", True),
        ("Some Release [18+]", "", True),
        ("Clean anime batch", "https://nyaa.si/", False),
        ("Adult release", "https://sukebei.nyaa.si/view/1", True),
    ],
)
def test_is_adult_torrent(name: str, engine_url: str, expected: bool) -> None:
    assert is_adult_torrent(name, engine_url) is expected
