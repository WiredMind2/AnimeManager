"""Tests for anime folder naming helpers."""

from __future__ import annotations

from shared.utils.folder_names import format_anime_folder_name, format_anime_folder_title


def test_format_anime_folder_title_sanitizes_special_chars():
    assert format_anime_folder_title("Naruto: Shippuden!") == "Naruto Shippuden"
    assert format_anime_folder_title("Test-Anime") == "Test Anime"


def test_format_anime_folder_title_none_returns_space():
    assert format_anime_folder_title(None) == " "


def test_format_anime_folder_name_with_title():
    assert format_anime_folder_name("Naruto", 1907) == "Naruto - 1907"


def test_format_anime_folder_name_empty_title_falls_back_to_id():
    assert format_anime_folder_name("", 42) == "anime_42"
    assert format_anime_folder_name("!!!", 42) == "anime_42"


def test_format_anime_folder_name_collapses_whitespace():
    assert format_anime_folder_name("  Foo   Bar  ", 1) == "Foo Bar - 1"
