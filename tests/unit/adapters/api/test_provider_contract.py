"""Provider adapter contract parity tests."""

from __future__ import annotations

import pytest

from adapters.api import AnilistCo, JikanMoe, KitsuIo, MyAnimeListNet
from adapters.api.provider_contract import (
    OPTIONAL_METHODS,
    REQUIRED_METHODS,
    validate_provider,
)


@pytest.mark.unit
@pytest.mark.stability_gate
@pytest.mark.parametrize(
    "module,cls_name",
    [
        (AnilistCo, "AnilistCoWrapper"),
        (JikanMoe, "JikanMoeWrapper"),
        (KitsuIo, "KitsuIoWrapper"),
        (MyAnimeListNet, "MyAnimeListNetWrapper"),
    ],
)
def test_wrapper_exposes_required_contract(module, cls_name):
    cls = getattr(module, cls_name)
    inst = cls.__new__(cls)
    inst.apiKey = "test_id"
    inst.searchAnime = lambda *a, **k: ()
    inst.anime = lambda *a, **k: {}
    assert validate_provider(inst) == []


@pytest.mark.unit
@pytest.mark.stability_gate
def test_required_and_optional_method_names_are_documented():
    assert "searchAnime" in REQUIRED_METHODS
    assert "schedule" in OPTIONAL_METHODS
