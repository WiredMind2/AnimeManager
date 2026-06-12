"""Unit tests for LibTorrent fast-resume persistence (mocked libtorrent)."""

from __future__ import annotations

import os
import threading
import types
from unittest.mock import MagicMock, patch

import pytest


def _build_mock_lt():
    class _TorrentStatus:
        queued_for_checking = 0
        checking_files = 1
        downloading_metadata = 2
        downloading = 3
        finished = 4
        seeding = 5
        allocating = 6
        checking_resume_data = 7

    class SaveResumeDataAlert:
        pass

    class SaveResumeDataFailedAlert:
        pass

    class StateUpdateAlert:
        pass

    class TorrentAddedAlert:
        pass

    class TorrentRemovedAlert:
        pass

    class TorrentErrorAlert:
        pass

    mock = types.ModuleType("libtorrent")
    mock.torrent_status = _TorrentStatus
    mock.save_resume_data_alert = SaveResumeDataAlert
    mock.save_resume_data_failed_alert = SaveResumeDataFailedAlert
    mock.state_update_alert = StateUpdateAlert
    mock.torrent_added_alert = TorrentAddedAlert
    mock.torrent_removed_alert = TorrentRemovedAlert
    mock.torrent_error_alert = TorrentErrorAlert
    mock.options_t = types.SimpleNamespace(delete_files=1)
    mock.read_resume_data = lambda data: {"resume": data}
    mock.write_resume_data_buf = lambda params: b"serialized-resume"
    mock.bencode = lambda obj: b"bencoded"
    return mock


@pytest.fixture
def lt_module(mock_lt):
    import adapters.torrent.libtorrent as lt_mod

    return lt_mod


@pytest.fixture
def mock_lt():
    return _build_mock_lt()


@pytest.fixture
def libtorrent_manager(lt_module, mock_lt, tmp_path, monkeypatch):
    monkeypatch.setattr(lt_module, "lt", mock_lt)
    monkeypatch.setattr(lt_module, "LIBTORRENT_AVAILABLE", True)

    data_path = str(tmp_path / "data")
    os.makedirs(data_path, exist_ok=True)
    settings = {
        "dataPath": data_path,
        "download_path": os.path.join(data_path, "Downloads"),
        "listen_port": 6882,
    }
    with patch.object(lt_module.LibTorrent, "initialize", lambda self: None):
        manager = lt_module.LibTorrent(settings)
    manager.settings = settings
    manager.download_path = settings["download_path"]
    manager.session = MagicMock()
    manager.session.pop_alerts.return_value = []
    manager.handles = {}
    manager._running = True
    manager._session_ready.set()
    manager._resume_lock = threading.Lock()
    manager._pending_resume_saves = 0
    manager._last_periodic_save = 0.0
    manager._last_handle_save = {}
    manager._thread = None
    yield manager
    manager._running = False
    manager.session = None


def test_resume_file_written_on_alert(libtorrent_manager, mock_lt):
    data_path = libtorrent_manager._resolve_data_path()
    resume_dir = os.path.join(data_path, ".libtorrent_resume")
    os.makedirs(resume_dir, exist_ok=True)

    handle = MagicMock()
    handle.info_hash.return_value = b"\xaa" * 20
    alert = mock_lt.save_resume_data_alert()
    alert.params = object()
    alert.resume_data = {"deprecated": True}
    alert.handle = handle

    libtorrent_manager._write_resume_alert(alert)

    info_hash = libtorrent_manager._normalise_hash(handle.info_hash.return_value)
    resume_path = libtorrent_manager._resume_file_path(info_hash)
    assert os.path.isfile(resume_path)
    with open(resume_path, "rb") as fh:
        assert fh.read() == b"serialized-resume"


def test_restore_from_resume_files(libtorrent_manager):
    data_path = libtorrent_manager._resolve_data_path()
    resume_dir = os.path.join(data_path, ".libtorrent_resume")
    os.makedirs(resume_dir, exist_ok=True)
    resume_path = os.path.join(resume_dir, "a" * 40 + ".resume")
    with open(resume_path, "wb") as fh:
        fh.write(b"x" * 250)

    handle = MagicMock()
    handle.info_hash.return_value = b"\xaa" * 20
    libtorrent_manager.session.add_torrent.return_value = handle

    libtorrent_manager._restore_from_resume_files()

    libtorrent_manager.session.add_torrent.assert_called_once()
    key = libtorrent_manager._normalise_hash(handle.info_hash())
    assert key in libtorrent_manager.handles


def test_delete_removes_resume_file(libtorrent_manager):
    info_hash = "b" * 40
    libtorrent_manager.handles[info_hash] = MagicMock()
    resume_path = libtorrent_manager._resume_file_path(info_hash)
    os.makedirs(os.path.dirname(resume_path), exist_ok=True)
    with open(resume_path, "wb") as fh:
        fh.write(b"x")

    libtorrent_manager.delete(info_hash)

    assert not os.path.isfile(resume_path)
    assert info_hash not in libtorrent_manager.handles


def test_close_requests_resume_save(libtorrent_manager):
    handle = MagicMock()
    handle.is_valid.return_value = True
    libtorrent_manager.handles["c" * 40] = handle
    libtorrent_manager._running = True

    libtorrent_manager.close()

    handle.save_resume_data.assert_called()


class _FakeDb:
    def __init__(self):
        self.calls: list[tuple] = []
        self._has_save_path = False

    def sql(self, query, params=(), save=False, **kwargs):
        self.calls.append((query.strip(), params, save))
        q = query.strip().upper()
        if "PRAGMA TABLE_INFO" in q:
            if self._has_save_path:
                return [(0, "save_path", "TEXT", 0, None, 0)]
            return [(0, "hash", "TEXT", 0, None, 0)]
        if "ALTER TABLE" in q:
            self._has_save_path = True
        if "FROM TORRENTS" in q and "SAVE_PATH" in q:
            return [("abc123", "Name", "[]", "/tmp/anime", 1)]
        if "EXISTS" in q:
            return [(1,)]
        return [(0,)]

    def save(self):
        pass


def test_list_torrents_for_restore():
    from application.services.database_manager import DatabaseManager

    dm = DatabaseManager()
    fake = _FakeDb()

    with patch.object(dm, "get_connection") as gc:
        gc.return_value.__enter__ = lambda s: fake
        gc.return_value.__exit__ = lambda s, *a: None
        rows = dm.list_torrents_for_restore()

    assert len(rows) == 1
    assert rows[0]["hash"] == "abc123"
    assert rows[0]["save_path"] == "/tmp/anime"
    assert rows[0]["anime_id"] == 1


def test_update_torrent_save_path():
    from application.services.database_manager import DatabaseManager

    dm = DatabaseManager()
    fake = _FakeDb()
    fake._has_save_path = True

    with patch.object(dm, "get_connection") as gc:
        gc.return_value.__enter__ = lambda s: fake
        gc.return_value.__exit__ = lambda s, *a: None
        dm.update_torrent_save_path("deadbeef", "/data/Animes/Show - 1")

    updates = [c for c in fake.calls if "UPDATE" in c[0].upper()]
    assert updates
