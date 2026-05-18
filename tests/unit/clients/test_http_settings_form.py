"""Unit tests for :mod:`clients.http.settings_form`."""

from __future__ import annotations

from clients.http import settings_form as sf


def _minimal_settings() -> dict:
    return {
        "anime": {"hideRated": True, "animePerPage": 50},
        "logs": {"enabled_categories": ["HTTP", "SEARCH"]},
        "UI": {
            "colors": {"Blue": "#56D8EF"},
            "tagcolors": {"SEEN": "Blue"},
        },
    }


class _FakeForm(dict):
    def getlist(self, key: str) -> list[str]:
        val = self.get(key)
        if val is None:
            return []
        if isinstance(val, list):
            return val
        return [val]


def test_build_sections_orders_tier_one_first():
    sections = sf.build_sections(_minimal_settings())
    names = [s["name"] for s in sections]
    assert names.index("anime") < names.index("UI")


def test_parse_form_bool_unchecked_round_trip():
    current = _minimal_settings()
    form = _FakeForm(
        {
            "__bool__": "anime.hideRated",
        }
    )
    out = sf.parse_form(form, current)
    assert out["anime"]["hideRated"] is False


def test_parse_form_int_coercion():
    current = _minimal_settings()
    form = _FakeForm({"anime.animePerPage": "25"})
    out = sf.parse_form(form, current)
    assert out["anime"]["animePerPage"] == 25


def test_build_context_exposes_palette():
    ctx = sf.build_context(_minimal_settings())
    assert "color_palette" in ctx
    assert ctx["color_palette"]["Blue"] == "#56D8EF"
