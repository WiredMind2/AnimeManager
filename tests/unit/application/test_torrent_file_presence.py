"""Tests for torrent on-disk presence detection."""

from __future__ import annotations

from application.services.torrent_file_presence import (
    folder_has_video_files,
    should_mark_deleted,
)


def test_folder_has_video_files_detects_mkv(tmp_path):
    show = tmp_path / "Show - 1"
    show.mkdir()
    (show / "episode.mkv").write_bytes(b"x")
    assert folder_has_video_files(str(show)) is True


def test_folder_has_video_files_false_when_empty(tmp_path):
    show = tmp_path / "Show - 1"
    show.mkdir()
    assert folder_has_video_files(str(show)) is False


def test_should_mark_deleted_when_complete_and_no_files(tmp_path):
    show = tmp_path / "Show - 1"
    show.mkdir()
    assert (
        should_mark_deleted(
            status="complete",
            save_path=str(show),
            anime_folder=None,
        )
        is True
    )


def test_should_mark_deleted_false_when_files_remain(tmp_path):
    show = tmp_path / "Show - 1"
    show.mkdir()
    (show / "episode.mkv").write_bytes(b"x")
    assert (
        should_mark_deleted(
            status="complete",
            save_path=str(show),
            anime_folder=None,
        )
        is False
    )


def test_should_mark_deleted_false_for_non_complete_status(tmp_path):
    show = tmp_path / "Show - 1"
    show.mkdir()
    assert (
        should_mark_deleted(
            status="saved",
            save_path=str(show),
            anime_folder=None,
        )
        is False
    )
