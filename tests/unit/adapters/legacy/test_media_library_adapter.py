"""Tests for :class:`~adapters.legacy.runtime.LegacyMediaLibraryAdapter`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from adapters.legacy.runtime import LegacyMediaLibraryAdapter


class _FakeRuntime:
    """Minimal stand-in for :class:`~adapters.legacy.runtime.LegacyRuntime`."""

    def __init__(self) -> None:
        self.fm = MagicMock()

    def getFolder(self, id=None, anime=None):  # noqa: ANN001
        return "/nonexistent/library-folder"

    def getEpisodes(self, folder):  # noqa: ANN001
        return []


def test_list_episode_files_includes_torrent_save_path(tmp_path: Path) -> None:
    """When the library folder scan is empty, torrent ``path`` rows still surface."""
    mkv = tmp_path / "show - 01.mkv"
    mkv.write_bytes(b"\x00")

    download = MagicMock()
    download.get_active_downloads.return_value = [
        {"anime_id": 7, "path": str(mkv)},
    ]
    download.get_torrents_overview.return_value = {}

    adapter = LegacyMediaLibraryAdapter(_FakeRuntime(), download_port=download)
    rows = adapter.list_episode_files(7)
    assert len(rows) == 1
    assert rows[0]["path"] == str(mkv)
    assert rows[0]["file_id"].startswith("ep-")
    download.get_active_downloads.assert_called()


def test_delete_episode_file_allows_torrent_root_when_library_missing(
    tmp_path: Path,
) -> None:
    """Deleting must work when ``getFolder`` does not exist but the file is under a torrent path."""
    mkv = tmp_path / "ep.mkv"
    mkv.write_bytes(b"\x00")

    download = MagicMock()
    download.get_active_downloads.return_value = [
        {"anime_id": 3, "path": str(mkv)},
    ]
    download.get_torrents_overview.return_value = {}

    fm = MagicMock()
    fm.exists.return_value = False

    class Rt(_FakeRuntime):
        def __init__(self) -> None:
            super().__init__()
            self.fm = fm

    adapter = LegacyMediaLibraryAdapter(Rt(), download_port=download)
    rows = adapter.list_episode_files(3)
    assert adapter.delete_episode_file(3, rows[0]["file_id"]) is True
    assert not mkv.exists()
