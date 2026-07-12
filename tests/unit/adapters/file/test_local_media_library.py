"""Tests for :class:`LocalMediaLibraryAdapter`."""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from adapters.file.local_episode_scanner import LocalEpisodeScanner
from adapters.file.local_media_library import LocalMediaLibraryAdapter


class _FakeFM:
    def __init__(self, *, data_path: str = "", exists: bool = True):
        self.settings = {"dataPath": data_path}
        self._exists = exists

    def exists(self, path: str) -> bool:
        return self._exists and bool(path) and os.path.exists(path)

    def list(self, path: str):
        if not os.path.isdir(path):
            return []
        return os.listdir(path)

    def isdir(self, path: str) -> bool:
        return os.path.isdir(path)

    def isfile(self, path: str) -> bool:
        return os.path.isfile(path)

    def delete(self, path: str) -> None:
        import shutil

        shutil.rmtree(path)


class _FakeDB:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._lock = threading.RLock()
        self.conn.executescript(
            """
            CREATE TABLE torrents (hash TEXT, status TEXT);
            CREATE TABLE torrentsIndex (id INTEGER, value TEXT);
            """
        )
        self.conn.commit()
        self.updates: list[tuple] = []

    @contextmanager
    def get_lock(self):
        with self._lock:
            yield self

    def sql(self, query: str, params=(), save: bool = False, to_dict: bool = False):
        cur = self.conn.execute(query, tuple(params))
        if save:
            self.conn.commit()
            self.updates.append(params)
            return []
        rows = list(cur.fetchall())
        cur.close()
        return rows

    def get(self, *, id: int, table: str):
        return {"id": id, "title": "Test Anime"}


class _FakeDBManager:
    def __init__(self, db: _FakeDB):
        self._db = db

    def get_database(self):
        return self._db


def _build_adapter(tmp_path: Path, episodes: list[tuple[str, str]]):
    """Create adapter with real episode files under tmp_path/animes/."""
    anime_dir = tmp_path / "animes" / "Test Anime - 7"
    anime_dir.mkdir(parents=True)
    for name, content in episodes:
        (anime_dir / name).write_bytes(content.encode())

    scanner = LocalEpisodeScanner(
        file_manager=_FakeFM(exists=True),
        database=_FakeDB(),
        anime_path=str(tmp_path / "animes"),
    )
    db = _FakeDB()
    return LocalMediaLibraryAdapter(
        scanner=scanner,
        file_manager=_FakeFM(data_path=str(tmp_path), exists=True),
        db_manager=_FakeDBManager(db),
    ), db, anime_dir


def test_list_episode_files_returns_metadata(tmp_path):
    adapter, _, anime_dir = _build_adapter(
        tmp_path,
        [("Episode 01.mkv", "video"), ("Episode 02.mkv", "video2")],
    )
    files = adapter.list_episode_files(7)
    assert len(files) == 2
    assert all(f["file_id"].startswith("ep-") for f in files)
    assert files[0]["size_bytes"] == len(b"video")
    assert files[0]["path"].endswith(".mkv")


def test_list_episode_files_empty_when_no_folder(tmp_path):
    scanner = LocalEpisodeScanner(
        file_manager=_FakeFM(exists=False),
        database=_FakeDB(),
        anime_path=str(tmp_path / "missing"),
    )
    adapter = LocalMediaLibraryAdapter(
        scanner=scanner,
        file_manager=_FakeFM(exists=False),
        db_manager=_FakeDBManager(_FakeDB()),
    )
    assert adapter.list_episode_files(1) == []


def test_delete_episode_file_removes_matching_file(tmp_path):
    adapter, _, _ = _build_adapter(tmp_path, [("Episode 01.mkv", "gone")])
    files = adapter.list_episode_files(7)
    file_id = files[0]["file_id"]
    assert adapter.delete_episode_file(7, file_id) is True
    assert adapter.list_episode_files(7) == []


def test_delete_episode_file_rejects_bad_id(tmp_path):
    adapter, _, _ = _build_adapter(tmp_path, [("Episode 01.mkv", "x")])
    assert adapter.delete_episode_file(7, "") is False
    assert adapter.delete_episode_file(7, "missing-id") is False


def test_delete_episode_file_does_not_touch_torrent_db(tmp_path):
    adapter, db, _ = _build_adapter(
        tmp_path,
        [("Episode 01.mkv", "x"), ("Episode 02.mkv", "y")],
    )
    db.conn.execute("INSERT INTO torrents VALUES ('hash1', 'complete')")
    db.conn.execute("INSERT INTO torrentsIndex VALUES (7, 'hash1')")
    db.conn.commit()

    file_id = adapter.list_episode_files(7)[0]["file_id"]
    assert adapter.delete_episode_file(7, file_id) is True

    row = db.conn.execute(
        "SELECT status FROM torrents WHERE hash='hash1'"
    ).fetchone()
    assert row[0] == "complete"
    assert len(adapter.list_episode_files(7)) == 1


def test_get_stream_cache_root_creates_directory(tmp_path):
    adapter, _, _ = _build_adapter(tmp_path, [])
    root = adapter.get_stream_cache_root()
    assert root == str(tmp_path / "streams")
    assert os.path.isdir(root)


def test_get_stream_cache_root_fallback_without_data_path(tmp_path):
    scanner = LocalEpisodeScanner(
        file_manager=_FakeFM(),
        database=_FakeDB(),
        anime_path=str(tmp_path),
    )
    adapter = LocalMediaLibraryAdapter(
        scanner=scanner,
        file_manager=_FakeFM(data_path=""),
        db_manager=_FakeDBManager(_FakeDB()),
    )
    root = adapter.get_stream_cache_root()
    assert os.path.isdir(root)


def test_delete_episode_file_rejects_path_outside_folder(tmp_path):
    adapter, _, anime_dir = _build_adapter(tmp_path, [("Episode 01.mkv", "x")])
    files = adapter.list_episode_files(7)
    file_id = files[0]["file_id"]

    outside = tmp_path / "outside.mkv"
    outside.write_bytes(b"x")

    original_list = adapter.list_episode_files

    def _list_with_outside(anime_id: int):
        items = original_list(anime_id)
        if items:
            items = list(items)
            items[0] = dict(items[0])
            items[0]["path"] = str(outside)
        return items

    adapter.list_episode_files = _list_with_outside  # type: ignore[method-assign]
    assert adapter.delete_episode_file(7, file_id) is False
    assert outside.exists()


def test_delete_episode_file_returns_false_when_remove_fails(tmp_path, monkeypatch):
    adapter, _, _ = _build_adapter(tmp_path, [("Episode 01.mkv", "x")])
    file_id = adapter.list_episode_files(7)[0]["file_id"]

    def _fail_remove(_path):
        raise OSError("locked")

    monkeypatch.setattr(os, "remove", _fail_remove)
    assert adapter.delete_episode_file(7, file_id) is False



def test_list_episode_files_skips_invalid_entries(tmp_path, monkeypatch):
    adapter, _, _ = _build_adapter(tmp_path, [("Episode 01.mkv", "x")])
    valid_path = str(next(tmp_path.rglob("*.mkv")))

    monkeypatch.setattr(
        adapter._scanner,
        "scan_episodes",
        lambda _f: [
            {"path": ""},
            "bad",
            {"path": valid_path, "title": "Episode 01", "season": "1", "episode": "1"},
        ],
    )
    files = adapter.list_episode_files(7)
    assert len(files) == 1
    assert files[0]["path"] == valid_path


def test_delete_anime_folder_removes_entire_directory(tmp_path):
    adapter, _, anime_dir = _build_adapter(tmp_path, [("Episode 01.mkv", "x")])
    assert anime_dir.exists()
    assert adapter.delete_anime_folder(7) is True
    assert not anime_dir.exists()


def test_delete_anime_folder_rejects_path_outside_anime_root(tmp_path, monkeypatch):
    adapter, _, anime_dir = _build_adapter(tmp_path, [("Episode 01.mkv", "x")])

    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(adapter._scanner, "resolve_anime_folder", lambda _aid: str(outside))

    assert adapter.delete_anime_folder(7) is False
    assert outside.exists()
    assert anime_dir.exists()
