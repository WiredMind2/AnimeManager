"""Tests for persisted torrent lifecycle status."""

from __future__ import annotations

from unittest.mock import patch

from application.services.database_manager import DatabaseManager


class _FakeDb:
    def __init__(self):
        self.calls: list[tuple] = []
        self._columns = {"hash", "name", "trackers", "save_path", "status"}

    def sql(self, query, params=(), save=False, to_dict=False):
        self.calls.append((query, params, save, to_dict))
        q = " ".join(str(query).split()).upper()
        if "PRAGMA TABLE_INFO" in q:
            return [(i, col, "TEXT", 0, None, 0) for i, col in enumerate(sorted(self._columns))]
        if "SELECT T.HASH, T.NAME, T.TRACKERS, T.SAVE_PATH, I.ID, T.STATUS" in q:
            return [
                ("abc123", "Name", "[]", "/tmp/anime", 1, "deleted"),
                ("def456", "Other", "[]", "/tmp/other", 2, "complete"),
            ]
        if "SELECT STATUS FROM TORRENTS" in q:
            return [("deleted",)]
        if "EXISTS" in q:
            return [(1,)]
        return []

    def save(self):
        pass


def test_list_torrents_for_restore_skips_deleted():
    dm = DatabaseManager()
    fake = _FakeDb()

    with patch.object(dm, "get_connection") as gc:
        gc.return_value.__enter__ = lambda s: fake
        gc.return_value.__exit__ = lambda s, *a: None
        rows = dm.list_torrents_for_restore()

    assert len(rows) == 1
    assert rows[0]["hash"] == "def456"


def test_update_and_get_torrent_status():
    dm = DatabaseManager()
    fake = _FakeDb()

    with patch.object(dm, "get_connection") as gc:
        gc.return_value.__enter__ = lambda s: fake
        gc.return_value.__exit__ = lambda s, *a: None
        dm.update_torrent_status("abc123", "deleted")
        status = dm.get_torrent_status("abc123")

    assert status == "deleted"
    updates = [
        c
        for c in fake.calls
        if "UPDATE TORRENTS SET STATUS" in " ".join(str(c[0]).split()).upper()
    ]
    assert updates
