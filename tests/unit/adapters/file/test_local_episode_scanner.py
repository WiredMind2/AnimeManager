"""Tests for local episode folder resolution."""

from __future__ import annotations

from types import SimpleNamespace

from adapters.file.local_episode_scanner import LocalEpisodeScanner
from shared.utils.folder_names import format_anime_folder_name


class _FakeFM:
    def __init__(self, folders: list[str] | None = None):
        self._folders = folders or []

    def list(self, _path: str):
        return self._folders

    def isdir(self, _path: str) -> bool:
        return True

    def exists(self, path: str) -> bool:
        return bool(path)

    def isfile(self, _path: str) -> bool:
        return False


class _FakeDB:
    def __init__(self, title: str = "Naruto"):
        self._title = title

    def get(self, *, id: int, table: str):
        assert table == "anime"
        return {"id": id, "title": self._title}


def test_resolve_anime_folder_when_not_on_disk_yet():
    scanner = LocalEpisodeScanner(
        file_manager=_FakeFM([]),
        database=_FakeDB("Test: Anime"),
        anime_path="/animes",
    )
    folder = scanner.resolve_anime_folder(1907)
    assert folder == f"/animes/{format_anime_folder_name('Test: Anime', 1907)}"


def test_resolve_anime_folder_existing_match():
    scanner = LocalEpisodeScanner(
        file_manager=_FakeFM(["Naruto - 1907"]),
        database=_FakeDB(),
        anime_path="/animes",
    )
    assert scanner.resolve_anime_folder(1907) == "/animes/Naruto - 1907"


def test_scan_episodes_empty_when_folder_missing():
    scanner = LocalEpisodeScanner(
        file_manager=SimpleNamespace(exists=lambda _p: False, list=lambda _p: []),
        database=_FakeDB(),
        anime_path="/animes",
    )
    assert scanner.scan_episodes("/missing") == []
