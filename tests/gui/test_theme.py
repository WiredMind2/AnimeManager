"""Tests for the legacy-parity theme module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clients.tk import theme as theme_module


def test_load_theme_returns_default_palette(monkeypatch):
    theme_module.reset_theme_cache()
    monkeypatch.setenv("ANIMEMANAGER_SETTINGS", "/nonexistent/__missing__.json")
    theme = theme_module.load_theme()
    assert theme.colors["Gray2"] == "#181915"
    assert theme.colors["Gray3"] == "#282923"
    assert theme.colors["Gray4"] == "#373734"
    assert theme.colors["White"] == "#F0F0FF"
    assert theme.tag_colors["NONE"] == "White"
    assert theme.tag_colors["WATCHING"] == "Orange"


def test_load_theme_reads_settings_file(tmp_path: Path, monkeypatch):
    theme_module.reset_theme_cache()
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "UI": {
                    "colors": {"Gray3": "#111111", "Custom": "#abcdef"},
                    "tagcolors": {"NONE": "Orange"},
                },
                "windows": {
                    "mainWindowTitle": "Test Title",
                    "mainWindowWidth": 1000,
                    "mainWindowHeight": 700,
                },
                "anime": {"animePerRow": 5, "animePerPage": 20},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ANIMEMANAGER_SETTINGS", str(settings_path))

    theme = theme_module.load_theme()
    assert theme.colors["Gray3"] == "#111111"
    assert theme.colors["Custom"] == "#abcdef"
    # untouched defaults still present
    assert theme.colors["Gray2"] == "#181915"
    assert theme.tag_colors["NONE"] == "Orange"
    assert theme.window["title"] == "Test Title"
    assert theme.window["width"] == 1000
    assert theme.window["height"] == 700
    assert theme.window["anime_per_row"] == 5
    assert theme.window["anime_per_page"] == 20


def test_filter_options_include_legacy_entries():
    theme_module.reset_theme_cache()
    theme = theme_module.load_theme()
    codes = [opt.filter for opt in theme.filter_options]
    for required in (
        "LIKED",
        "SEEN",
        "WATCHING",
        "WATCHLIST",
        "FINISHED",
        "AIRING",
        "UPCOMING",
        "RATED",
        "SEASON",
        "RANDOM",
        "NONE",
        "DEFAULT",
    ):
        assert required in codes


def test_menu_options_include_legacy_actions():
    theme_module.reset_theme_cache()
    theme = theme_module.load_theme()
    actions = {opt.action for opt in theme.menu_options}
    assert {"characters", "disks", "logs", "settings", "reload", "exit"}.issubset(actions)


def test_apply_dark_window_does_not_raise(tk_root):
    theme_module.reset_theme_cache()
    theme_module.apply_dark_window(tk_root)
    # Background should now match the dark palette.
    assert tk_root.cget("bg") == theme_module.load_theme().color("Gray3")


def test_tag_color_falls_back_to_white(monkeypatch):
    theme_module.reset_theme_cache()
    theme = theme_module.load_theme()
    assert theme.tag_color("WATCHING") == theme.color("Orange")
    assert theme.tag_color(None) == theme.color("White")
    assert theme.tag_color("UNKNOWN_TAG") == theme.color("White")


def test_resolve_font_returns_tuple(tk_root):
    family, size, weight = theme_module.resolve_font(13)
    assert isinstance(family, str)
    assert size == 13
    assert weight == "normal"
