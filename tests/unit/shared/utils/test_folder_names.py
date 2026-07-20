"""Tests for anime folder naming helpers."""

from __future__ import annotations

from shared.utils.folder_names import (
    choose_canonical_anime_folder_name,
    format_anime_folder_name,
    format_anime_folder_title,
    match_anime_folder_names,
    parse_anime_id_from_folder_name,
)


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


def test_parse_anime_id_from_folder_name_title_suffix():
    assert parse_anime_id_from_folder_name("Naruto - 1907") == 1907


def test_parse_anime_id_from_folder_name_anime_prefix():
    assert parse_anime_id_from_folder_name("anime_42") == 42


def test_match_anime_folder_names_filters_by_id():
    entries = ["Naruto - 1907", "Bleach - 3", "anime_1907", "Misc"]
    assert match_anime_folder_names(entries, 1907) == ["Naruto - 1907", "anime_1907"]


def test_choose_canonical_anime_folder_name_prefers_video_files(tmp_path):
    root = tmp_path / "Animes"
    root.mkdir()
    old = root / "Old Title - 2210"
    new = root / "New Title - 2210"
    old.mkdir()
    new.mkdir()
    (old / "ep01.mkv").write_text("x", encoding="utf-8")

    chosen = choose_canonical_anime_folder_name(
        ["New Title - 2210", "Old Title - 2210"],
        animes_root=str(root),
        has_video_files=lambda path: "Old Title" in path,
    )
    assert chosen == "Old Title - 2210"

