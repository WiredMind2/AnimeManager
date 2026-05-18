"""Additional restore and overview tests for :class:`DownloadManager`."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def DownloadManager():
    from application.services.download_manager import DownloadManager as _DM

    return _DM


def _silent_logger(*_a, **_kw):
    return None


class _FakeDB:
    def __init__(self, pairs=None, torrent_data=None):
        self.pairs = list(pairs or [])
        self.torrent_data = dict(torrent_data or {})

    def list_anime_torrent_pairs(self):
        return list(self.pairs)

    def get_torrent_data(self, hash_value):
        return self.torrent_data.get(str(hash_value).lower())


class TestRestoreMore:
    def test_restore_waits_then_returns_none_when_list_never_ready(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.name = "LibTorrent"
        tm.list.side_effect = RuntimeError("not ready")
        mgr.set_torrent_manager(tm)
        mgr.set_database_manager(_FakeDB(pairs=[(1, "a" * 40)]))
        try:
            with patch.object(time, "time", side_effect=[0.0, 100.0]):
                assert mgr._restore_persisted_torrents_once() is None
        finally:
            mgr.close()

    def test_restore_list_failure_after_ready_returns_none(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.name = "LibTorrent"
        tm.list.side_effect = [None, RuntimeError("list failed")]
        mgr.set_torrent_manager(tm)
        mgr.set_database_manager(_FakeDB(pairs=[(1, "c" * 40)]))
        try:
            assert mgr._restore_persisted_torrents_once() is None
        finally:
            mgr.close()

    def test_maybe_restore_marks_complete_for_non_libtorrent(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.name = "Transmission"
        mgr.set_torrent_manager(tm)
        try:
            mgr._maybe_restore_persisted_torrents()
            assert mgr._persisted_restore_completed is True
        finally:
            mgr.close()

    def test_close_shuts_down_executor(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        executor = mgr._executor
        mgr.close()
        assert mgr._executor is None
        assert executor is not None


class TestWatchingTagCallback:
    def test_watching_callback_invoked(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        calls: list[tuple[int, int]] = []
        mgr.set_watching_tag_callback(lambda aid, uid: calls.append((aid, uid)))
        try:
            mgr._set_user_tag(1, 9)
        finally:
            mgr.close()
        assert calls == [(1, 9)]
