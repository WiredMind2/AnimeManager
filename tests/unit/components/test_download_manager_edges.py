"""Edge-case unit tests for ``application.services.download_manager.DownloadManager``.

These tests use in-memory fakes for every collaborator. They never hit the
network, never start real torrent clients, and never touch disk.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import types
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def DownloadManager():
    from application.services.download_manager import DownloadManager as _DM

    return _DM


@pytest.fixture
def DownloadTask():
    from application.services.download_manager import DownloadTask as _DT

    return _DT


def _silent_logger(*_a, **_kw):
    return None


# ---------------------------------------------------------------------------
# DownloadTask edges
# ---------------------------------------------------------------------------


class TestDownloadTask:
    def test_default_values(self, DownloadTask):
        t = DownloadTask(1)
        status = t.get_status()
        assert status["anime_id"] == 1
        assert status["url"] is None
        assert status["hash"] is None
        assert status["user_id"] is None
        assert status["cancelled"] is False
        assert status["elapsed_time"] >= 0

    def test_with_all_args(self, DownloadTask):
        t = DownloadTask(42, url="http://x/y.torrent", hash_value="abc", user_id=7)
        s = t.get_status()
        assert s["anime_id"] == 42
        assert s["url"] == "http://x/y.torrent"
        assert s["hash"] == "abc"
        assert s["user_id"] == 7

    def test_cancel_flips_flag(self, DownloadTask):
        t = DownloadTask(1)
        assert t.cancelled is False
        t.cancel()
        assert t.cancelled is True
        # idempotent
        t.cancel()
        assert t.cancelled is True

    def test_status_queue_is_independent_per_task(self, DownloadTask):
        a = DownloadTask(1)
        b = DownloadTask(2)
        assert a.status_queue is not b.status_queue

    def test_elapsed_time_monotonic(self, DownloadTask):
        t = DownloadTask(1)
        first = t.get_status()["elapsed_time"]
        time.sleep(0.01)
        second = t.get_status()["elapsed_time"]
        assert second >= first

    def test_negative_anime_id_accepted(self, DownloadTask):
        # No internal validation - documents current behavior
        t = DownloadTask(-1)
        assert t.get_status()["anime_id"] == -1


# ---------------------------------------------------------------------------
# DownloadManager: validation + queueing
# ---------------------------------------------------------------------------


class TestDownloadFileValidation:
    def test_requires_url_or_hash(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            assert mgr.download_file(1) is None
            assert mgr.download_file(1, url="") is None
            assert mgr.download_file(1, url=None, hash_value="") is None
        finally:
            mgr.close()

    def test_url_only_returns_status_queue(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            q = mgr.download_file(1, url="magnet:?xt=urn:btih:zzz")
            assert isinstance(q, queue.Queue)
        finally:
            mgr.close()

    def test_hash_only_returns_status_queue(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            q = mgr.download_file(2, hash_value="deadbeef")
            assert isinstance(q, queue.Queue)
        finally:
            mgr.close()

    def test_url_and_hash_both_returns_queue(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            q = mgr.download_file(3, url="magnet:?xt=urn:btih:x", hash_value="y")
            assert isinstance(q, queue.Queue)
        finally:
            mgr.close()


# ---------------------------------------------------------------------------
# Cancel / status / active downloads
# ---------------------------------------------------------------------------


class TestCancelAndStatus:
    def test_cancel_no_active_returns_false(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            assert mgr.cancel_download(99) is False
        finally:
            mgr.close()

    def test_get_status_returns_none_when_idle(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            assert mgr.get_download_status(99) is None
        finally:
            mgr.close()

    def test_get_active_downloads_empty_initially(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            assert mgr.get_active_downloads() == []
        finally:
            mgr.close()

    def test_active_download_visible_during_execution(
        self, DownloadManager, DownloadTask
    ):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            # Force a task into _active_downloads to test mid-flight visibility.
            task = DownloadTask(7, url="magnet:?xt=urn:btih:abc")
            with mgr._lock:
                mgr._active_downloads[7] = task
            status = mgr.get_download_status(7)
            assert status is not None
            assert status["anime_id"] == 7
            assert any(s["anime_id"] == 7 for s in mgr.get_active_downloads())
            assert mgr.cancel_download(7) is True
            assert task.cancelled is True
            # Cancellation evicts so the UI stops listing the entry.
            assert 7 not in mgr._active_downloads
            assert mgr.get_download_status(7) is None
        finally:
            mgr.close()


# ---------------------------------------------------------------------------
# URL handling: magnet vs http, validation
# ---------------------------------------------------------------------------


class TestPrepareTorrent:
    def test_is_magnet_link_true(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            assert mgr._is_magnet_link("magnet:?xt=urn:btih:abc") is True
        finally:
            mgr.close()

    def test_is_magnet_link_false_for_http(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            assert mgr._is_magnet_link("http://example.com/x.torrent") is False
        finally:
            mgr.close()

    def test_is_magnet_link_false_for_empty(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            assert mgr._is_magnet_link("") is False
        finally:
            mgr.close()

    def test_is_url_allowed_blocks_invalid(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            assert mgr._is_url_allowed("not-a-real-url") is False
        finally:
            mgr.close()

    def test_is_url_allowed_allows_simple_https(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            # validate_url accepts https URLs to public hosts
            with patch("shared.security.utils.validate_url") as vu:
                vu.return_value = (True, "ok")
                assert mgr._is_url_allowed("https://example.com/x.torrent") is True
        finally:
            mgr.close()


# ---------------------------------------------------------------------------
# Save torrent / get torrent data via DatabaseManager port
# ---------------------------------------------------------------------------


class _FakeDB:
    def __init__(self):
        self.saved = []
        self.torrent_data: Dict[str, Any] = {}
        self.raise_save = False
        self.pairs: List[tuple[int, str]] = []

    def list_anime_torrent_pairs(self):
        return list(self.pairs)

    def save_torrent(self, anime_id, torrent):
        if self.raise_save:
            raise RuntimeError("DB exploded")
        self.saved.append((anime_id, torrent))

    def get_torrent_data(self, hash_value):
        return self.torrent_data.get(hash_value)


class TestPortInteractions:
    def test_save_torrent_no_db_is_noop(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            torrent = MagicMock()
            mgr._save_torrent(1, torrent)  # should not raise
        finally:
            mgr.close()

    def test_save_torrent_db_exception_swallowed(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        db = _FakeDB()
        db.raise_save = True
        mgr.set_database_manager(db)
        try:
            torrent = MagicMock()
            # Must not propagate; logs and continues.
            mgr._save_torrent(1, torrent)
        finally:
            mgr.close()

    def test_save_torrent_happy_path(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        db = _FakeDB()
        mgr.set_database_manager(db)
        try:
            torrent = MagicMock()
            mgr._save_torrent(99, torrent)
            assert db.saved == [(99, torrent)]
        finally:
            mgr.close()

    def test_setter_methods_dont_raise(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            mgr.set_torrent_manager(MagicMock())
            mgr.set_file_manager(MagicMock())
            mgr.set_database_manager(_FakeDB())
        finally:
            mgr.close()


# ---------------------------------------------------------------------------
# Start download: torrent manager interactions
# ---------------------------------------------------------------------------


class TestStartDownload:
    def test_start_download_no_torrent_manager(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            t = MagicMock()
            t.to_magnet = MagicMock(return_value="magnet:?xt=urn:btih:abc")
            assert mgr._start_download(1, t) is False
        finally:
            mgr.close()

    def test_start_download_torrent_without_to_magnet(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        mgr.set_torrent_manager(MagicMock())
        try:
            t = types.SimpleNamespace()  # No to_magnet attr.
            assert mgr._start_download(1, t) is False
        finally:
            mgr.close()

    def test_start_download_empty_folder_returns_false(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        mgr.set_torrent_manager(tm)
        try:
            t = MagicMock()
            t.to_magnet.return_value = "magnet:?xt=urn:btih:abc"
            with patch.object(mgr, "_get_anime_folder", return_value=None):
                assert mgr._start_download(1, t) is False
        finally:
            mgr.close()

    def test_start_download_passes_path_to_torrent_manager(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.add.return_value = [MagicMock(hash="h1"), MagicMock(hash="h2")]
        mgr.set_torrent_manager(tm)
        try:
            t = MagicMock()
            t.to_magnet.return_value = "magnet:?xt=urn:btih:abc"
            assert mgr._start_download(5, t) is True
            tm.add.assert_called_once()
            call_kwargs = tm.add.call_args.kwargs
            assert call_kwargs.get("path") == "./anime_5"
            tm.move.assert_called_once()
            move_kwargs = tm.move.call_args.kwargs
            assert move_kwargs["hashes"] == ["h1", "h2"]
            assert move_kwargs["path"] == "./anime_5"
        finally:
            mgr.close()

    def test_start_download_torrent_manager_returns_empty(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.add.return_value = []
        mgr.set_torrent_manager(tm)
        try:
            t = MagicMock()
            t.to_magnet.return_value = "magnet:?xt=urn:btih:abc"
            assert mgr._start_download(5, t) is False
        finally:
            mgr.close()

    def test_start_download_exception_returns_false(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.add.side_effect = RuntimeError("network")
        mgr.set_torrent_manager(tm)
        try:
            t = MagicMock()
            t.to_magnet.return_value = "magnet:?xt=urn:btih:abc"
            assert mgr._start_download(5, t) is False
        finally:
            mgr.close()


# ---------------------------------------------------------------------------
# Move torrents
# ---------------------------------------------------------------------------


class TestMoveTorrentsToFolder:
    def test_non_iterable_torrents_is_safe(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            mgr._move_torrents_to_folder(None, "/tmp")
        finally:
            mgr.close()

    def test_empty_iterable_no_call(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        mgr.set_torrent_manager(tm)
        try:
            mgr._move_torrents_to_folder([], "/tmp")
            tm.move.assert_not_called()
        finally:
            mgr.close()

    def test_torrents_without_hash_skipped(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        mgr.set_torrent_manager(tm)
        try:
            obj = object()  # no hash attribute
            mgr._move_torrents_to_folder([obj], "/tmp")
            tm.move.assert_not_called()
        finally:
            mgr.close()

    def test_move_exception_swallowed(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.move.side_effect = RuntimeError("nope")
        mgr.set_torrent_manager(tm)
        try:
            mgr._move_torrents_to_folder([MagicMock(hash="x")], "/tmp")
        finally:
            mgr.close()


# ---------------------------------------------------------------------------
# Lifecycle: close idempotence
# ---------------------------------------------------------------------------


class TestExecuteDownload:
    """Cover the synchronous _execute_download path with all collaborators mocked."""

    def test_execute_with_no_torrent_prepared_marks_failure(
        self, DownloadManager, DownloadTask
    ):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            task = DownloadTask(1, url="magnet:?xt=urn:btih:abc")
            with patch.object(mgr, "_prepare_torrent", return_value=None):
                mgr._execute_download(task)
            # status_queue should have True (started) then False (no torrent).
            results = []
            while not task.status_queue.empty():
                results.append(task.status_queue.get_nowait())
            assert results == [True, False]
            assert 1 not in mgr._active_downloads
        finally:
            mgr.close()

    def test_execute_full_path_success(self, DownloadManager, DownloadTask):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        db = MagicMock()
        tm = MagicMock()
        tm.add.return_value = [MagicMock(hash="h")]
        mgr.set_torrent_manager(tm)
        mgr.set_database_manager(db)
        try:
            task = DownloadTask(1, url="magnet:?xt=urn:btih:abc", user_id=7)
            torrent = MagicMock()
            torrent.name = "[SubsPlease] Anime - 01.mkv"
            torrent.to_magnet.return_value = "magnet:?xt=urn:btih:abc"
            with patch.object(mgr, "_prepare_torrent", return_value=torrent):
                mgr._execute_download(task)
            results = []
            while not task.status_queue.empty():
                results.append(task.status_queue.get_nowait())
            # Started + success.
            assert results == [True, True]
            db.save_torrent.assert_called_once()
            # Regression: a successful download must stay visible in
            # ``get_active_downloads`` so the HTMX panel doesn't lose it
            # immediately after the hand-off to the torrent client.
            assert 1 in mgr._active_downloads
            status = mgr.get_download_status(1)
            assert status is not None
            assert status["state"] == "DOWNLOADING"
            assert status["name"] == "[SubsPlease] Anime - 01.mkv"
        finally:
            mgr.close()

    def test_execute_success_keeps_task_visible_for_ui_polling(
        self, DownloadManager, DownloadTask
    ):
        """The /ui/downloads panel polls every 4s. A successful start must
        not vanish from get_active_downloads(); only failure / cancel evict."""
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.add.return_value = [MagicMock(hash="h")]
        # A torrent-manager list() that yields nothing keeps the refresh
        # path a no-op so this test exercises the *initial* state seeded
        # by _execute_download itself.
        tm.list.return_value = []
        mgr.set_torrent_manager(tm)
        try:
            task = DownloadTask(
                844,
                url="magnet:?xt=urn:btih:abc",
                hash_value="deadbeef",
            )
            torrent = MagicMock()
            torrent.name = "anime.mkv"
            torrent.hash = "deadbeef"
            torrent.size = None
            torrent.to_magnet.return_value = "magnet:?xt=urn:btih:abc"
            with patch.object(mgr, "_prepare_torrent", return_value=torrent):
                mgr._execute_download(task)

            actives = mgr.get_active_downloads()
            assert len(actives) == 1
            assert actives[0]["anime_id"] == 844
            assert actives[0]["state"] == "DOWNLOADING"
            assert actives[0]["name"] == "anime.mkv"
            # progress is seeded to 0.0 so the UI can immediately render
            # an empty progress bar while it waits for the first poll;
            # the live torrent-manager value overrides it as soon as the
            # refresh tick fires.
            assert actives[0]["progress"] == 0.0
        finally:
            mgr.close()

    def test_execute_exception_marks_failure(self, DownloadManager, DownloadTask):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            task = DownloadTask(1, url="magnet:?xt=urn:btih:abc")
            with patch.object(mgr, "_prepare_torrent", side_effect=RuntimeError("oh no")):
                mgr._execute_download(task)
            results = []
            while not task.status_queue.empty():
                results.append(task.status_queue.get_nowait())
            assert results == [True, False]
            assert 1 not in mgr._active_downloads
        finally:
            mgr.close()


class TestPrepareTorrentDetails:
    def test_prepare_torrent_magnet_url(self, DownloadManager, DownloadTask):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            task = DownloadTask(1, url="magnet:?xt=urn:btih:abc")
            with patch(
                "adapters.legacy.legacy_classes.Torrent.from_magnet",
                return_value="MAGNET_TORRENT",
            ):
                result = mgr._prepare_torrent(task)
            assert result == "MAGNET_TORRENT"
        finally:
            mgr.close()

    def test_prepare_torrent_unsafe_url_blocked(self, DownloadManager, DownloadTask):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            task = DownloadTask(1, url="not-a-url")
            assert mgr._prepare_torrent(task) is None
        finally:
            mgr.close()

    def test_prepare_torrent_via_hash_returns_torrent(self, DownloadManager, DownloadTask):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        db = MagicMock()
        db.get_torrent_data.return_value = ("Naruto", ["udp://t1"])
        mgr.set_database_manager(db)
        try:
            task = DownloadTask(1, hash_value="dead")
            result = mgr._prepare_torrent(task)
            assert result is not None
            assert getattr(result, "hash") == "dead"
            # Trackers must survive as a list so ``to_magnet`` emits a
            # proper ``&tr=<url>`` per entry rather than treating a
            # JSON string as an iterable of characters.
            assert list(getattr(result, "trackers") or []) == ["udp://t1"]
        finally:
            mgr.close()

    def test_prepare_torrent_via_hash_decodes_json_trackers(
        self, DownloadManager, DownloadTask
    ):
        """Persisted ``trackers`` rows are JSON strings -- decoding
        them on restore is what keeps a re-added magnet pointing at
        the original tracker tier instead of urlencoding the literal
        JSON one character at a time."""
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        db = MagicMock()
        db.get_torrent_data.return_value = (
            "Naruto",
            '["udp://t1", "udp://t2"]',
        )
        mgr.set_database_manager(db)
        try:
            task = DownloadTask(1, hash_value="dead")
            result = mgr._prepare_torrent(task)
            assert result is not None
            assert list(getattr(result, "trackers") or []) == [
                "udp://t1",
                "udp://t2",
            ]
        finally:
            mgr.close()

    def test_decode_persisted_trackers_handles_shapes(self, DownloadManager):
        """The helper must coerce every plausible persisted shape into
        a list of URLs without raising."""
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            f = mgr._decode_persisted_trackers
            assert f(None) == []
            assert f([]) == []
            assert f("") == []
            assert f("   ") == []
            assert f("udp://only") == ["udp://only"]
            assert f("not json [oops") == ["not json [oops"]
            assert f('["a","b"]') == ["a", "b"]
            assert f(["a", "b"]) == ["a", "b"]
            assert f(("a", "b")) == ["a", "b"]
        finally:
            mgr.close()

    def test_prepare_torrent_via_hash_no_db_returns_none(
        self, DownloadManager, DownloadTask
    ):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            task = DownloadTask(1, hash_value="dead")
            assert mgr._prepare_torrent(task) is None
        finally:
            mgr.close()

    def test_prepare_torrent_via_hash_db_returns_none(self, DownloadManager, DownloadTask):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        db = MagicMock()
        db.get_torrent_data.return_value = None
        mgr.set_database_manager(db)
        try:
            task = DownloadTask(1, hash_value="dead")
            assert mgr._prepare_torrent(task) is None
        finally:
            mgr.close()

    def test_prepare_torrent_http_bad_status_returns_none(
        self, DownloadManager, DownloadTask
    ):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            task = DownloadTask(1, url="https://example.com/x.torrent")
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_resp.headers = {}
            with patch("shared.security.utils.validate_url", return_value=(True, "ok")):
                with patch("requests.get", return_value=mock_resp):
                    assert mgr._prepare_torrent(task) is None
        finally:
            mgr.close()

    def test_prepare_torrent_http_too_large_content_length_returns_none(
        self, DownloadManager, DownloadTask
    ):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            task = DownloadTask(1, url="https://example.com/x.torrent")
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"Content-Length": str(20 * 1024 * 1024)}
            with patch("shared.security.utils.validate_url", return_value=(True, "ok")):
                with patch("requests.get", return_value=mock_resp):
                    assert mgr._prepare_torrent(task) is None
        finally:
            mgr.close()

    def test_prepare_torrent_http_oversized_payload_returns_none(
        self, DownloadManager, DownloadTask
    ):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            task = DownloadTask(1, url="https://example.com/x.torrent")
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {}
            mock_resp.raw.read.return_value = b"x" * (10 * 1024 * 1024 + 2)
            with patch("shared.security.utils.validate_url", return_value=(True, "ok")):
                with patch("requests.get", return_value=mock_resp):
                    assert mgr._prepare_torrent(task) is None
        finally:
            mgr.close()

    def test_prepare_torrent_http_happy_path(self, DownloadManager, DownloadTask):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            task = DownloadTask(1, url="https://example.com/x.torrent")
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {}
            mock_resp.raw.read.return_value = b"torrent-content"
            with patch("shared.security.utils.validate_url", return_value=(True, "ok")):
                with patch("requests.get", return_value=mock_resp):
                    with patch(
                        "adapters.legacy.legacy_classes.Torrent.from_torrent",
                        return_value="HTTP_TORRENT",
                    ):
                        assert mgr._prepare_torrent(task) == "HTTP_TORRENT"
        finally:
            mgr.close()

    def test_prepare_torrent_exception_returns_none(
        self, DownloadManager, DownloadTask
    ):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            task = DownloadTask(1, url="https://example.com/x.torrent")
            with patch("shared.security.utils.validate_url", side_effect=RuntimeError("boom")):
                assert mgr._prepare_torrent(task) is None
        finally:
            mgr.close()


class TestLifecycle:
    def test_close_is_idempotent(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        mgr.close()
        # Second close should not raise.
        mgr.close()

    def test_close_cancels_active(self, DownloadManager, DownloadTask):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        task = DownloadTask(11, url="magnet:?xt=urn:btih:abc")
        with mgr._lock:
            mgr._active_downloads[11] = task
        mgr.close()
        assert task.cancelled is True

    def test_stop_alias_is_close(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        mgr._stop()  # alias for close
        assert mgr._executor is None

    def test_redownload_returns_zero(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            assert mgr.redownload(123) == 0
        finally:
            mgr.close()

    def test_redownload_requeues_persisted_hashes(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        db = _FakeDB()
        db.pairs = [(10, "a" * 40), (10, "a" * 40), (11, "b" * 40)]
        mgr.set_database_manager(db)
        try:
            with patch.object(mgr, "download_file", return_value=queue.Queue()) as dl:
                queued = mgr.redownload(10)
            assert queued == 1
            dl.assert_called_once_with(10, hash_value="a" * 40)
        finally:
            mgr.close()

    def test_get_anime_folder_format(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            assert mgr._get_anime_folder(42) == "./anime_42"
        finally:
            mgr.close()


# ---------------------------------------------------------------------------
# Live progress refresh (covers the bug where the Active Downloads progress
# bar never moved because DownloadTask was never updated after _execute_download
# handed off to the torrent client).
# ---------------------------------------------------------------------------


class TestRefreshActiveTaskStatus:
    """Verify that `get_active_downloads` pulls live torrent-manager state
    into each task so the UI's polling clients see fresh progress / bytes /
    speed without restarting the download or refreshing the page."""

    def _make_task(self, DownloadTask, anime_id=1, hash_value="aabb"):
        task = DownloadTask(anime_id, url="magnet:?xt=urn:btih:" + hash_value,
                            hash_value=hash_value)
        task.state = "DOWNLOADING"
        task.progress = 0.0
        return task

    def test_progress_mirrors_torrent_manager_dict_payload(
        self, DownloadManager, DownloadTask
    ):
        """LibTorrent returns dict rows; their fields must land on the task."""
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.list.return_value = [
            {
                "hash": "aabb",
                "name": "anime.mkv",
                "size": 1000,
                "downloaded": 250,
                "progress": 0.25,
                "state": "DOWNLOADING",
                "dl_speed": 500,
                "eta": 1,
                "path": "/data/anime",
            }
        ]
        mgr.set_torrent_manager(tm)
        try:
            task = self._make_task(DownloadTask)
            with mgr._lock:
                mgr._active_downloads[1] = task
            actives = mgr.get_active_downloads()
            assert len(actives) == 1
            entry = actives[0]
            assert entry["progress"] == 0.25
            assert entry["size"] == 1000
            assert entry["downloaded"] == 250
            assert entry["dl_speed"] == 500.0
            assert entry["eta"] == 1
            assert entry["state"] == "DOWNLOADING"
            assert entry["path"] == "/data/anime"
            assert entry["name"] == "anime.mkv"
        finally:
            mgr.close()

    def test_progress_derived_from_bytes_when_adapter_omits_it(
        self, DownloadManager, DownloadTask
    ):
        """qBittorrent's Torrent shim historically only carried size /
        downloaded; we must derive progress so the bar still moves."""
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        # ``Torrent`` is a dict subclass; mirror that by handing dict rows
        # without an explicit ``progress`` field.
        tm = MagicMock()
        tm.list.return_value = [
            {"hash": "AABB", "size": 2000, "downloaded": 500}
        ]
        mgr.set_torrent_manager(tm)
        try:
            task = self._make_task(DownloadTask, hash_value="aabb")
            with mgr._lock:
                mgr._active_downloads[1] = task
            entry = mgr.get_active_downloads()[0]
            assert entry["progress"] == pytest.approx(0.25)
            assert entry["size"] == 2000
            assert entry["downloaded"] == 500
        finally:
            mgr.close()

    def test_hash_match_is_case_insensitive(
        self, DownloadManager, DownloadTask
    ):
        """Different torrent clients normalise infohashes differently
        (qBittorrent lowercases, LibTorrent's str(info_hash()) mixes case).
        We must match regardless."""
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.list.return_value = [
            {"hash": "DEADBEEF", "size": 100, "downloaded": 75, "progress": 0.75}
        ]
        mgr.set_torrent_manager(tm)
        try:
            task = self._make_task(DownloadTask, hash_value="deadbeef")
            with mgr._lock:
                mgr._active_downloads[1] = task
            entry = mgr.get_active_downloads()[0]
            assert entry["progress"] == 0.75
        finally:
            mgr.close()

    def test_missing_hash_skips_refresh_quietly(
        self, DownloadManager, DownloadTask
    ):
        """If we don't yet know the infohash there's nothing to correlate
        against; the refresh must not crash and must not call list()."""
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        mgr.set_torrent_manager(tm)
        try:
            task = DownloadTask(1, url="magnet:?xt=urn:btih:abc")
            task.state = "DOWNLOADING"
            with mgr._lock:
                mgr._active_downloads[1] = task
            mgr.get_active_downloads()
            tm.list.assert_not_called()
        finally:
            mgr.close()

    def test_refresh_is_throttled(self, DownloadManager, DownloadTask):
        """Two rapid status reads must trigger at most one tm.list() call
        so a swarm of pollers doesn't hammer the torrent client."""
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.list.return_value = [
            {"hash": "aabb", "size": 100, "downloaded": 10, "progress": 0.1}
        ]
        mgr.set_torrent_manager(tm)
        try:
            task = self._make_task(DownloadTask)
            with mgr._lock:
                mgr._active_downloads[1] = task
            mgr.get_active_downloads()
            mgr.get_active_downloads()
            mgr.get_download_status(1)
            assert tm.list.call_count == 1
        finally:
            mgr.close()

    def test_list_exception_is_logged_and_swallowed(
        self, DownloadManager, DownloadTask
    ):
        """A flaky torrent client must not propagate up and break the
        status endpoint -- the UI keeps showing the last-known state."""
        mgr = DownloadManager(max_concurrent_downloads=1)
        captured: list[tuple[str, str]] = []

        def _capturing_logger(scope, message, *args, **kwargs):
            captured.append((scope, message))

        mgr.log = _capturing_logger
        tm = MagicMock()
        tm.list.side_effect = RuntimeError("client offline")
        mgr.set_torrent_manager(tm)
        try:
            task = self._make_task(DownloadTask)
            task.progress = 0.42  # last-known good
            with mgr._lock:
                mgr._active_downloads[1] = task
            entry = mgr.get_active_downloads()[0]
            assert entry["progress"] == 0.42
            assert any("Failed to refresh torrent status" in m for _, m in captured)
        finally:
            mgr.close()

    def test_no_torrent_manager_is_a_noop(self, DownloadManager, DownloadTask):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            task = self._make_task(DownloadTask)
            with mgr._lock:
                mgr._active_downloads[1] = task
            entry = mgr.get_active_downloads()[0]
            assert entry["progress"] == 0.0
            assert entry["state"] == "DOWNLOADING"
        finally:
            mgr.close()

    def test_libtorrent_style_state_string_is_uppercased(
        self, DownloadManager, DownloadTask
    ):
        """LibTorrent reports states like ``downloading`` / ``finished``;
        the UI's chip styling keys off uppercase tokens."""
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.list.return_value = [
            {"hash": "aabb", "size": 100, "downloaded": 100,
             "progress": 1.0, "state": "finished"}
        ]
        mgr.set_torrent_manager(tm)
        try:
            task = self._make_task(DownloadTask)
            with mgr._lock:
                mgr._active_downloads[1] = task
            entry = mgr.get_active_downloads()[0]
            assert entry["state"] == "FINISHED"
            assert entry["progress"] == 1.0
        finally:
            mgr.close()


class TestTorrentsOverview:
    """Verify the unified active/seeding/completed view used by the
    downloads page WebSocket and the ``/ui/downloads/overview.json``
    fallback endpoint."""

    def _make_db(self, anime_map=None, title_map=None):
        db = MagicMock()
        db.get_anime_ids_by_hashes.return_value = anime_map or {}
        db.get_anime_titles.return_value = title_map or {}
        return db

    def test_overview_buckets_torrents_by_state(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.list.return_value = [
            {"hash": "AAAA", "name": "ep01", "state": "downloading",
             "size": 100, "downloaded": 25, "progress": 0.25},
            {"hash": "BBBB", "name": "ep02", "state": "seeding",
             "size": 100, "downloaded": 100, "progress": 1.0},
            {"hash": "CCCC", "name": "ep03", "state": "finished",
             "size": 100, "downloaded": 100, "progress": 1.0},
            {"hash": "DDDD", "name": "ep04", "state": "error",
             "size": 100, "downloaded": 0, "progress": 0.0},
        ]
        mgr.set_torrent_manager(tm)
        mgr.set_database_manager(
            self._make_db(
                anime_map={
                    "aaaa": 1,
                    "bbbb": 2,
                    "cccc": 3,
                    "dddd": 4,
                },
                title_map={1: "A", 2: "B", 3: "C", 4: "D"},
            )
        )
        try:
            overview = mgr.get_torrents_overview()
            assert [r["hash"] for r in overview["active"]] == ["aaaa"]
            assert [r["hash"] for r in overview["seeding"]] == ["bbbb"]
            assert [r["hash"] for r in overview["completed"]] == ["cccc"]
            assert [r["hash"] for r in overview["error"]] == ["dddd"]
            assert overview["active"][0]["anime_id"] == 1
            assert overview["active"][0]["anime_title"] == "A"
        finally:
            mgr.close()

    def test_overview_falls_back_to_progress_when_state_missing(
        self, DownloadManager
    ):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.list.return_value = [
            {"hash": "AAAA", "size": 100, "downloaded": 100, "progress": 1.0},
            {"hash": "BBBB", "size": 100, "downloaded": 30, "progress": 0.3},
        ]
        mgr.set_torrent_manager(tm)
        mgr.set_database_manager(self._make_db())
        try:
            overview = mgr.get_torrents_overview()
            # 100% with no explicit state -> completed
            assert [r["hash"] for r in overview["completed"]] == ["aaaa"]
            # In-progress with no state -> active
            assert [r["hash"] for r in overview["active"]] == ["bbbb"]
        finally:
            mgr.close()

    def test_overview_returns_empty_when_torrent_manager_unset(
        self, DownloadManager
    ):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            overview = mgr.get_torrents_overview()
            assert overview == {
                "active": [],
                "seeding": [],
                "completed": [],
                "error": [],
                "other": [],
            }
        finally:
            mgr.close()

    def test_overview_swallows_torrent_manager_errors(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.list.side_effect = RuntimeError("boom")
        mgr.set_torrent_manager(tm)
        try:
            overview = mgr.get_torrents_overview()
            assert all(bucket == [] for bucket in overview.values())
        finally:
            mgr.close()

    def test_overview_surfaces_pending_tasks_not_yet_in_client(
        self, DownloadManager, DownloadTask
    ):
        """Just-queued downloads must show up under ``active`` even before
        the torrent client has registered them, so the UI doesn't go
        silent right after the user clicks 'Download'."""
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.list.return_value = []
        mgr.set_torrent_manager(tm)
        mgr.set_database_manager(self._make_db())
        try:
            task = DownloadTask(1, url="magnet:?xt=urn:btih:abc")
            task.state = "DOWNLOADING"
            task.name = "queued.mkv"
            with mgr._lock:
                mgr._active_downloads[1] = task
            overview = mgr.get_torrents_overview()
            actives = overview["active"]
            assert len(actives) == 1
            assert actives[0]["anime_id"] == 1
            assert actives[0]["name"] == "queued.mkv"
        finally:
            mgr.close()


# ---------------------------------------------------------------------------
# Persisted torrent restore (LibTorrent cold start)
# ---------------------------------------------------------------------------


class TestPersistedTorrentRestore:
    def test_restore_once_skips_non_libtorrent(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.name = "qBittorrent"
        tm.list.return_value = []
        mgr.set_torrent_manager(tm)
        db = _FakeDB()
        db.pairs = [(1, "a" * 40)]
        mgr.set_database_manager(db)
        try:
            assert mgr._restore_persisted_torrents_once() == 0
            tm.add.assert_not_called()
        finally:
            mgr.close()

    def test_restore_once_readds_persisted_not_in_session(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        tm = MagicMock()
        tm.name = "LibTorrent"
        tm.list.return_value = []
        mgr.set_torrent_manager(tm)
        h = "a" * 40
        db = _FakeDB()
        db.pairs = [(9, h)]
        db.torrent_data[h] = (
            "Episode",
            json.dumps(["udp://tracker.example:80/announce"]),
        )
        mgr.set_database_manager(db)
        tm.add.return_value = [{"hash": h, "name": "Episode"}]
        try:
            with patch.object(mgr, "_get_anime_folder", return_value="/tmp/a9"):
                n = mgr._restore_persisted_torrents_once()
            assert n == 1
            tm.add.assert_called_once()
            magnet = tm.add.call_args[0][0][0]
            assert h in magnet
            assert "magnet:?" in magnet
        finally:
            mgr.close()

    def test_restore_once_skips_pairs_already_live(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        h = "b" * 40
        tm = MagicMock()
        tm.name = "LibTorrent"
        tm.list.return_value = [{"hash": h, "name": "x", "state": "seeding"}]
        mgr.set_torrent_manager(tm)
        db = _FakeDB()
        db.pairs = [(1, h)]
        db.torrent_data[h] = ("N", "[]")
        mgr.set_database_manager(db)
        try:
            assert mgr._restore_persisted_torrents_once() == 0
            tm.add.assert_not_called()
        finally:
            mgr.close()

    def test_schedule_restore_is_idempotent(self, DownloadManager):
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        try:
            mgr.schedule_restore_persisted_torrents_after_startup()
            mgr.schedule_restore_persisted_torrents_after_startup()
            assert mgr._restore_persisted_thread_started is True
        finally:
            mgr.close()

    def test_resolve_restore_folder_prefers_heavier_suffix_match(
        self, DownloadManager, tmp_path
    ):
        """When two ``* - <id>`` folders exist, pick the one with more file bytes."""
        mgr = DownloadManager(max_concurrent_downloads=1)
        mgr.log = _silent_logger
        data = tmp_path / "data"
        animes = data / "Animes"
        light = animes / "Old Title - 42"
        heavy = animes / "New Title - 42"
        light.mkdir(parents=True)
        heavy.mkdir(parents=True)
        (light / "a.txt").write_text("x", encoding="utf-8")
        (heavy / "b.bin").write_bytes(b"x" * 5000)
        fm = MagicMock()
        fm.settings = {"dataPath": str(data)}
        mgr.set_file_manager(fm)
        try:
            picked = mgr._resolve_anime_media_folder_for_restore(42)
            assert os.path.normcase(picked) == os.path.normcase(str(heavy))
        finally:
            mgr.close()
