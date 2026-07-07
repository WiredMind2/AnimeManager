"""Extended tests for :class:`LocalEpisodeScanner`."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from adapters.file.local_episode_scanner import LocalEpisodeScanner
from adapters.persistence.models import Anime


class _DiskFM:
    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def list(self, path: str):
        return os.listdir(path) if os.path.isdir(path) else []

    def isdir(self, path: str) -> bool:
        return os.path.isdir(path)

    def isfile(self, path: str) -> bool:
        return os.path.isfile(path)


class _FakeDB:
    def __init__(self, anime=None):
        self._anime = anime or {"id": 7, "title": "Test Anime"}

    def get(self, *, id: int, table: str):
        if table != "anime":
            return None
        data = dict(self._anime)
        data["id"] = id
        return data


def test_resolve_anime_folder_no_path_returns_empty():
    scanner = LocalEpisodeScanner(
        file_manager=_DiskFM(),
        database=_FakeDB(),
        anime_path="",
    )
    assert scanner.resolve_anime_folder(1) == ""


def test_resolve_anime_folder_no_file_manager_returns_empty():
    scanner = LocalEpisodeScanner(
        file_manager=None,
        database=_FakeDB(),
        anime_path="/animes",
    )
    assert scanner.resolve_anime_folder(1) == ""


def test_resolve_anime_folder_missing_anime_returns_empty():
    scanner = LocalEpisodeScanner(
        file_manager=_DiskFM(),
        database=SimpleNamespace(get=lambda **_: None),
        anime_path="/animes",
    )
    assert scanner.resolve_anime_folder(1) == ""


def test_resolve_anime_folder_wraps_dict_in_anime_model(tmp_path):
    anime_dir = tmp_path / "animes"
    anime_dir.mkdir()
    scanner = LocalEpisodeScanner(
        file_manager=_DiskFM(),
        database=_FakeDB({"id": 9, "title": "One Piece"}),
        anime_path=str(anime_dir),
    )
    folder = scanner.resolve_anime_folder(9)
    assert folder.endswith("One Piece - 9")


def test_resolve_anime_folder_anime_instance(tmp_path):
    anime_dir = tmp_path / "animes"
    anime_dir.mkdir()
    db = SimpleNamespace(
        get=lambda *, id, table: Anime({"id": id, "title": "Bleach"})
    )
    scanner = LocalEpisodeScanner(
        file_manager=_DiskFM(),
        database=db,
        anime_path=str(anime_dir),
    )
    assert scanner.resolve_anime_folder(5).endswith("Bleach - 5")


def test_scan_episodes_parses_season_and_episode(tmp_path):
    folder = tmp_path / "show"
    folder.mkdir()
    (folder / "Show S01E02.mkv").write_bytes(b"x")
    (folder / "Show S01E01.mkv").write_bytes(b"y")

    scanner = LocalEpisodeScanner(
        file_manager=_DiskFM(),
        database=_FakeDB(),
        anime_path=str(tmp_path),
    )
    eps = scanner.scan_episodes(str(folder))
    assert len(eps) == 2
    assert eps[0]["episode"] in ("01", "02")
    assert all(e["path"].endswith(".mkv") for e in eps)


def test_scan_episodes_assigns_fallback_episode_numbers(tmp_path):
    folder = tmp_path / "flat"
    folder.mkdir()
    (folder / "part_a.mkv").write_bytes(b"a")
    (folder / "part_b.mkv").write_bytes(b"b")

    scanner = LocalEpisodeScanner(
        file_manager=_DiskFM(),
        database=_FakeDB(),
        anime_path=str(tmp_path),
    )
    eps = scanner.scan_episodes(str(folder))
    assert len(eps) == 2
    assert eps[0]["episode"] == "01"
    assert eps[1]["episode"] == "02"


def test_scan_episodes_skips_non_video_files(tmp_path):
    folder = tmp_path / "mixed"
    folder.mkdir()
    (folder / "notes.txt").write_text("nope")
    (folder / "video.mp4").write_bytes(b"v")

    scanner = LocalEpisodeScanner(
        file_manager=_DiskFM(),
        database=_FakeDB(),
        anime_path=str(tmp_path),
    )
    eps = scanner.scan_episodes(str(folder))
    assert len(eps) == 1
    assert eps[0]["path"].endswith("video.mp4")
