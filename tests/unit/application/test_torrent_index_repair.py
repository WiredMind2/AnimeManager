"""Tests for torrent index repair."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from application.services.database_manager import DatabaseManager
from application.services.torrent_index_repair import TorrentIndexRepairService


class _FakeFM:
    def exists(self, path: str) -> bool:
        return bool(path)

    def list(self, path: str):
        import os

        if not os.path.isdir(path):
            return []
        return os.listdir(path)

    def isdir(self, path: str) -> bool:
        import os

        return os.path.isdir(path)


class _FakeDB:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._lock = threading.RLock()
        self.conn.executescript(
            """
            CREATE TABLE torrents (
                hash TEXT PRIMARY KEY,
                name TEXT,
                trackers TEXT,
                save_path TEXT,
                status TEXT
            );
            CREATE TABLE torrentsIndex (id INTEGER, value TEXT);
            """
        )
        self.conn.commit()

    @contextmanager
    def get_lock(self):
        with self._lock:
            yield self

    def sql(self, query: str, params=(), save: bool = False, to_dict: bool = False):
        cur = self.conn.execute(query, tuple(params))
        if save:
            self.conn.commit()
            return []
        rows = list(cur.fetchall())
        cur.close()
        return rows

    def save(self) -> None:
        self.conn.commit()

    def get(self, *, id: int, table: str):
        return {"id": id, "title": "Test Anime"}


class _FakeDBManager(DatabaseManager):
    def __init__(self, db: _FakeDB):
        super().__init__()
        self._db = db

    def get_database(self):
        return self._db

    def get_connection(self):
        return self._db.get_lock()


class _FakeScanner:
    def __init__(self, anime_path: str):
        self._anime_path = anime_path

    def resolve_anime_folder(self, anime_id: int) -> str:
        import os

        return os.path.join(self._anime_path, f"Test Anime - {anime_id}")


def _build_service(tmp_path: Path):
    anime_path = tmp_path / "Animes"
    folder = anime_path / "Test Anime - 7"
    folder.mkdir(parents=True)
    (folder / "[ANi] Example - 01.mp4").write_bytes(b"x")
    db = _FakeDB()
    db.conn.execute(
        "INSERT INTO torrents(hash, name, trackers, save_path, status) "
        "VALUES (?, ?, ?, ?, ?)",
        ("abc123", "[ANi] Example - 01", "[]", str(folder), "complete"),
    )
    db.conn.commit()
    db_manager = _FakeDBManager(db)
    scanner = _FakeScanner(str(anime_path))
    service = TorrentIndexRepairService(
        db_manager=db_manager,
        scanner=scanner,
        torrent_manager=None,
        anime_path=str(anime_path),
    )
    return service, db


def test_detect_issues_flags_missing_index(tmp_path):
    service, _db = _build_service(tmp_path)
    issues = service.detect_issues()
    kinds = {issue.kind for issue in issues}
    assert "missing_index" in kinds


def test_repair_inserts_missing_index_row(tmp_path):
    service, db = _build_service(tmp_path)
    result = service.repair_unindexed_torrents()
    assert result.repaired_index_rows == 1
    row = db.conn.execute(
        "SELECT id, value FROM torrentsIndex WHERE id=7 AND value='abc123'"
    ).fetchone()
    assert row == (7, "abc123")
