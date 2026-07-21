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


def test_resolve_anime_folder_prefers_folder_with_videos(tmp_path):
    root = tmp_path / "Animes"
    empty = root / "Z Empty - 2210"
    filled = root / "A Filled - 2210"
    empty.mkdir(parents=True)
    filled.mkdir(parents=True)
    (filled / "ep01.mkv").write_bytes(b"x")

    class _TmpFM(_FakeFM):
        def list(self, _path: str):
            return ["Z Empty - 2210", "A Filled - 2210"]

        def isdir(self, path: str) -> bool:
            return path.endswith("2210")

    scanner = LocalEpisodeScanner(
        file_manager=_TmpFM(),
        database=_FakeDB("Whatever"),
        anime_path=str(root),
    )
    assert scanner.resolve_anime_folder(2210).replace("\\", "/") == str(filled).replace(
        "\\", "/"
    )


def test_scan_episodes_empty_when_folder_missing():
    scanner = LocalEpisodeScanner(
        file_manager=SimpleNamespace(exists=lambda _p: False, list=lambda _p: []),
        database=_FakeDB(),
        anime_path="/animes",
    )
    assert scanner.scan_episodes("/missing") == []
