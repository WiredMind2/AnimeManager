"""Tests for torrent on-disk presence detection."""

from __future__ import annotations

from application.services.torrent_file_presence import (
    TorrentReconcileAction,
    episodes_in_range_present,
    folder_has_video_files,
    parse_episode_range_from_name,
    should_mark_deleted,
    should_reconcile_torrent,
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


def test_parse_episode_range_from_batch_name():
    name = "[SubsPlease] Chitose-kun wa Ramune Bin no Naka (01-13) (720p) [Batch]"
    assert parse_episode_range_from_name(name) == (1, 13)


def test_episodes_in_range_present_detects_matching_file(tmp_path):
    show = tmp_path / "Show - 1"
    show.mkdir()
    (show / "Show - 05.mkv").write_bytes(b"x")
    assert episodes_in_range_present(str(show), 1, 13) is True


def test_episodes_in_range_absent_when_only_out_of_range_files(tmp_path):
    show = tmp_path / "Show - 1"
    show.mkdir()
    (show / "Show - 14.mkv").write_bytes(b"x")
    assert episodes_in_range_present(str(show), 1, 13) is False


def test_should_reconcile_batch_deleted_when_range_files_missing(tmp_path):
    show = tmp_path / "Show - 1"
    show.mkdir()
    (show / "Show - 14.mkv").write_bytes(b"x")
    batch_name = "[SubsPlease] Example (01-13) (720p) [Batch]"
    action = should_reconcile_torrent(
        status="complete",
        save_path=str(show),
        anime_folder=str(show),
        torrent_name=batch_name,
    )
    assert action == TorrentReconcileAction.MARK_DELETED


def test_should_reconcile_batch_kept_when_range_files_present(tmp_path):
    show = tmp_path / "Show - 1"
    show.mkdir()
    (show / "Show - 03.mkv").write_bytes(b"x")
    batch_name = "[SubsPlease] Example (01-13) (720p) [Batch]"
    action = should_reconcile_torrent(
        status="complete",
        save_path=str(show),
        anime_folder=str(show),
        torrent_name=batch_name,
    )
    assert action == TorrentReconcileAction.SKIP


def test_should_reconcile_error_state_without_files(tmp_path):
    show = tmp_path / "Show - 1"
    show.mkdir()
    action = should_reconcile_torrent(
        status=None,
        save_path=str(show),
        anime_folder=str(show),
        live_state="missingfiles",
    )
    assert action == TorrentReconcileAction.MARK_DELETED


def test_should_reconcile_skips_active_download_without_files(tmp_path):
    show = tmp_path / "Show - 1"
    show.mkdir()
    action = should_reconcile_torrent(
        status=None,
        save_path=str(show),
        anime_folder=str(show),
        live_state="downloading",
        live_progress=0.1,
    )
    assert action == TorrentReconcileAction.SKIP


def test_should_reconcile_deleted_removes_from_client():
    action = should_reconcile_torrent(
        status="deleted",
        save_path="/missing",
        anime_folder="/missing",
    )
    assert action == TorrentReconcileAction.REMOVE_FROM_CLIENT


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
