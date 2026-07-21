"""Unit tests for LibTorrent fast-resume persistence (mocked libtorrent)."""

from __future__ import annotations

import os
import stat
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
    # Bit flags used by seed_mode restore path.
    mock.torrent_flags = types.SimpleNamespace(
        seed_mode=1,
        default_flags=2,
    )
    mock.read_resume_data = lambda data: {"resume": data}
    mock.write_resume_data_buf = lambda params: b"serialized-resume"
    mock.bencode = lambda obj: b"bencoded"
    mock.session = MagicMock
    mock.alert = types.SimpleNamespace(
        category_t=types.SimpleNamespace(all_categories=0xFFFFFFFF)
    )
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


def test_restore_from_resume_applies_seed_mode_when_complete(
    libtorrent_manager, mock_lt
):
    data_path = libtorrent_manager._resolve_data_path()
    resume_dir = os.path.join(data_path, ".libtorrent_resume")
    os.makedirs(resume_dir, exist_ok=True)
    info_hash = "a" * 40
    resume_path = os.path.join(resume_dir, f"{info_hash}.resume")
    with open(resume_path, "wb") as fh:
        fh.write(b"x" * 250)

    handle = MagicMock()
    handle.info_hash.return_value = bytes.fromhex(info_hash)
    libtorrent_manager.session.add_torrent.return_value = handle
    libtorrent_manager._torrent_status_callback = (
        lambda h: "complete" if h == info_hash else None
    )

    libtorrent_manager._restore_from_resume_files()

    params = libtorrent_manager.session.add_torrent.call_args[0][0]
    assert isinstance(params, dict)
    assert params["flags"] & mock_lt.torrent_flags.seed_mode


def test_restore_from_resume_skips_seed_mode_when_not_complete(libtorrent_manager):
    data_path = libtorrent_manager._resolve_data_path()
    resume_dir = os.path.join(data_path, ".libtorrent_resume")
    os.makedirs(resume_dir, exist_ok=True)
    info_hash = "a" * 40
    resume_path = os.path.join(resume_dir, f"{info_hash}.resume")
    with open(resume_path, "wb") as fh:
        fh.write(b"x" * 250)

    handle = MagicMock()
    handle.info_hash.return_value = bytes.fromhex(info_hash)
    libtorrent_manager.session.add_torrent.return_value = handle
    libtorrent_manager._torrent_status_callback = lambda _h: None

    libtorrent_manager._restore_from_resume_files()

    params = libtorrent_manager.session.add_torrent.call_args[0][0]
    assert "flags" not in params


def test_db_fallback_applies_seed_mode_when_complete(
    libtorrent_manager, mock_lt, tmp_path
):
    save_path = tmp_path / "anime"
    save_path.mkdir()
    info_hash = "b" * 40
    handle = MagicMock()
    handle.info_hash.return_value = bytes.fromhex(info_hash)
    libtorrent_manager.session.add_torrent.return_value = handle
    libtorrent_manager._restored = False
    libtorrent_manager.handles = {}
    libtorrent_manager._torrent_status_callback = (
        lambda h: "complete" if h == info_hash else None
    )
    libtorrent_manager._restore_callback = lambda: [
        {
            "hash": info_hash,
            "name": "Show",
            "trackers": [],
            "save_path": str(save_path),
        }
    ]

    libtorrent_manager._restore_from_database_fallback()

    params = libtorrent_manager.session.add_torrent.call_args[0][0]
    assert params["flags"] & mock_lt.torrent_flags.seed_mode
    assert info_hash in libtorrent_manager.handles


def test_connect_applies_active_checking_and_defers_dht(
    lt_module, mock_lt, tmp_path, monkeypatch
):
    monkeypatch.setattr(lt_module, "lt", mock_lt)
    monkeypatch.setattr(lt_module, "LIBTORRENT_AVAILABLE", True)
    monkeypatch.setattr(lt_module, "_RESTORE_WIRE_TIMEOUT_S", 0.01)

    data_path = str(tmp_path / "data")
    os.makedirs(data_path, exist_ok=True)
    settings = {
        "dataPath": data_path,
        "download_path": os.path.join(data_path, "Downloads"),
        "listen_port": 6882,
        "active_checking": 1,
    }

    session = MagicMock()
    session.pop_alerts.return_value = []
    applied: list[dict] = []

    def capture_settings(payload):
        applied.append(dict(payload))

    session.apply_settings.side_effect = capture_settings
    mock_lt.session = MagicMock(return_value=session)

    with patch.object(lt_module.LibTorrent, "initialize", lambda self: None):
        manager = lt_module.LibTorrent(settings)
    manager.settings = settings
    manager.download_path = settings["download_path"]
    manager.listen_port = 6882
    manager._session_thread = lambda: None

    # Wire callbacks before connect so wait returns immediately.
    manager.set_restore_callback(lambda: [])
    manager.set_torrent_status_callback(lambda _h: None)

    manager.connect(thread=False)

    assert any(s.get("active_checking") == 1 for s in applied)
    first_with_dht = next(s for s in applied if "enable_dht" in s)
    assert first_with_dht["enable_dht"] is False
    assert manager._restored is False
    assert manager._session_ready.is_set()

    manager.ensure_restored()

    assert any(s.get("enable_dht") is True for s in applied)
    assert manager._restored is True


def test_connect_waits_for_callbacks_before_restore(
    lt_module, mock_lt, tmp_path, monkeypatch
):
    monkeypatch.setattr(lt_module, "lt", mock_lt)
    monkeypatch.setattr(lt_module, "LIBTORRENT_AVAILABLE", True)
    monkeypatch.setattr(lt_module, "_RESTORE_WIRE_TIMEOUT_S", 1.0)

    data_path = str(tmp_path / "data")
    os.makedirs(data_path, exist_ok=True)
    settings = {
        "dataPath": data_path,
        "download_path": os.path.join(data_path, "Downloads"),
        "listen_port": 6882,
    }

    session = MagicMock()
    session.pop_alerts.return_value = []
    mock_lt.session = MagicMock(return_value=session)

    with patch.object(lt_module.LibTorrent, "initialize", lambda self: None):
        manager = lt_module.LibTorrent(settings)
    manager.settings = settings
    manager.download_path = settings["download_path"]
    manager.listen_port = 6882
    manager._session_thread = lambda: None

    order: list[str] = []
    original_wait = manager._wait_for_restore_callbacks
    original_restore = manager._run_session_restore

    def wait_and_wire():
        order.append("wait")
        manager.set_restore_callback(lambda: [])
        manager.set_torrent_status_callback(lambda _h: None)
        return original_wait()

    def restore():
        order.append("restore")
        # Callbacks must already be present when restore runs.
        assert manager._restore_callback is not None
        assert manager._torrent_status_callback is not None
        return original_restore()

    monkeypatch.setattr(manager, "_wait_for_restore_callbacks", wait_and_wire)
    monkeypatch.setattr(manager, "_run_session_restore", restore)

    manager.connect(thread=False)
    assert order == ["wait"]
    assert manager._session_ready.is_set()
    assert manager._restored is False

    manager.ensure_restored()
    assert order == ["wait", "restore"]
    assert manager._restored is True


def test_late_restore_callback_reruns_db_fallback(libtorrent_manager, tmp_path):
    save_path = tmp_path / "anime"
    save_path.mkdir()
    info_hash = "c" * 40
    handle = MagicMock()
    handle.info_hash.return_value = bytes.fromhex(info_hash)
    libtorrent_manager.session.add_torrent.return_value = handle
    libtorrent_manager._restored = True
    libtorrent_manager.handles = {}
    libtorrent_manager._torrent_status_callback = lambda _h: None

    libtorrent_manager.set_restore_callback(
        lambda: [
            {
                "hash": info_hash,
                "name": "Show",
                "trackers": [],
                "save_path": str(save_path),
            }
        ]
    )

    assert info_hash in libtorrent_manager.handles
    libtorrent_manager.session.add_torrent.assert_called_once()


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


def test_restore_from_resume_skips_deleted_status(libtorrent_manager, tmp_path, monkeypatch):
    manager = libtorrent_manager
    resume_dir = tmp_path / ".libtorrent_resume"
    resume_dir.mkdir()
    deleted_hash = "a" * 40
    resume_path = resume_dir / f"{deleted_hash}.resume"
    resume_path.write_bytes(b"x" * 250)

    monkeypatch.setattr(manager, "_resume_dir", lambda: str(resume_dir))
    manager._torrent_status_callback = lambda h: "deleted" if h == deleted_hash else None
    manager.session = MagicMock()
    manager.handles = {}

    manager._restore_from_resume_files()

    assert deleted_hash not in manager.handles
    assert not resume_path.exists()
    manager.session.add_torrent.assert_not_called()


def test_purge_deleted_torrents_removes_resume_and_handles(
    libtorrent_manager, tmp_path, monkeypatch
):
    manager = libtorrent_manager
    resume_dir = tmp_path / ".libtorrent_resume"
    resume_dir.mkdir()
    deleted_hash = "b" * 40
    active_hash = "c" * 40
    deleted_resume = resume_dir / f"{deleted_hash}.resume"
    active_resume = resume_dir / f"{active_hash}.resume"
    deleted_resume.write_bytes(b"x" * 250)
    active_resume.write_bytes(b"x" * 250)

    monkeypatch.setattr(manager, "_resume_dir", lambda: str(resume_dir))
    manager._torrent_status_callback = (
        lambda h: "deleted" if h == deleted_hash else None
    )
    manager.session = MagicMock()
    deleted_handle = MagicMock()
    manager.handles = {deleted_hash: deleted_handle}

    count = manager.purge_deleted_torrents()

    assert count >= 1
    assert not deleted_resume.exists()
    assert active_resume.exists()
    assert deleted_hash not in manager.handles


def test_resume_write_uses_unique_temp_and_succeeds(libtorrent_manager):
    path = libtorrent_manager._resume_file_path("f" * 40)
    libtorrent_manager._atomic_write_bytes(path, b"unique-temp-test")

    assert os.path.isfile(path)
    assert not os.path.exists(f"{path}.tmp")
    dirname = os.path.dirname(path)
    leftovers = [name for name in os.listdir(dirname) if name.endswith(".tmp")]
    assert not leftovers
    with open(path, "rb") as fh:
        assert fh.read() == b"unique-temp-test"


def test_resume_write_retries_on_windows_access_denied(libtorrent_manager, monkeypatch):
    path = libtorrent_manager._resume_file_path("d" * 40)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    calls = {"count": 0}
    real_replace = os.replace

    def flaky_replace(src, dst):
        calls["count"] += 1
        if calls["count"] == 1:
            exc = OSError("[WinError 5] Access is denied")
            exc.winerror = 5
            raise exc
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", flaky_replace)
    libtorrent_manager._atomic_write_bytes(path, b"payload")

    assert os.path.isfile(path)
    with open(path, "rb") as fh:
        assert fh.read() == b"payload"
    assert calls["count"] >= 2


def test_resume_write_serializes_concurrent_same_hash(libtorrent_manager, mock_lt):
    handle = MagicMock()
    handle.info_hash.return_value = b"\xcc" * 20
    alert = mock_lt.save_resume_data_alert()
    alert.params = object()
    alert.resume_data = {"deprecated": True}
    alert.handle = handle

    errors: list[Exception] = []

    def worker() -> None:
        try:
            libtorrent_manager._write_resume_alert(alert)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    info_hash = libtorrent_manager._normalise_hash(handle.info_hash.return_value)
    resume_path = libtorrent_manager._resume_file_path(info_hash)
    assert os.path.isfile(resume_path)
    with open(resume_path, "rb") as fh:
        assert fh.read() == b"serialized-resume"


def test_resume_write_clears_readonly_target(libtorrent_manager):
    path = libtorrent_manager._resume_file_path("e" * 40)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"old")
    os.chmod(path, stat.S_IREAD)

    libtorrent_manager._atomic_write_bytes(path, b"new-data")

    with open(path, "rb") as fh:
        assert fh.read() == b"new-data"


def test_list_files_returns_absolute_paths(libtorrent_manager):
    info_hash = "c" * 40
    handle = MagicMock()
    handle.has_metadata.return_value = True
    status = MagicMock()
    status.save_path = r"C:\Anime\Show - 7"
    handle.status.return_value = status
    torrent_info = MagicMock()
    file_storage = MagicMock()
    file_storage.num_files.return_value = 2
    file_storage.file_path.side_effect = lambda idx: {
        0: "[ANi] Example - 01.mp4",
        1: "readme.txt",
    }[idx]
    handle.get_torrent_info.return_value = torrent_info
    torrent_info.files.return_value = file_storage
    libtorrent_manager.handles[info_hash] = handle

    paths = libtorrent_manager.list_files(info_hash)

    assert paths == [
        r"C:\Anime\Show - 7\[ANi] Example - 01.mp4",
        r"C:\Anime\Show - 7\readme.txt",
    ]


def test_connect_applies_connections_limit_from_settings(
    lt_module, mock_lt, tmp_path, monkeypatch
):
    monkeypatch.setattr(lt_module, "lt", mock_lt)
    monkeypatch.setattr(lt_module, "LIBTORRENT_AVAILABLE", True)

    data_path = str(tmp_path / "data")
    os.makedirs(data_path, exist_ok=True)
    settings = {
        "dataPath": data_path,
        "download_path": os.path.join(data_path, "Downloads"),
        "listen_port": 6882,
        "max_connections": 50,
    }
    with patch.object(lt_module.LibTorrent, "initialize", lambda self: None):
        manager = lt_module.LibTorrent(settings)
    manager.settings = settings
    manager.listen_port = 6882
    manager.max_connections = 50

    session = MagicMock()
    mock_lt.session = MagicMock(return_value=session)

    with (
        patch.object(manager, "_wait_for_restore_callbacks"),
        patch.object(manager, "_run_session_restore"),
        patch.object(manager, "_session_thread"),
    ):
        manager.connect(thread=False)

    applied = [
        call.args[0]
        for call in session.apply_settings.call_args_list
        if call.args and isinstance(call.args[0], dict)
    ]
    assert any(d.get("connections_limit") == 50 for d in applied)
    first = next(d for d in applied if "connections_limit" in d)
    assert first["listen_interfaces"] == "0.0.0.0:6882"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (50, 50),
        ("100", 100),
        (0, 1),
        (100000, 65535),
        ("bad", 200),
        (None, 200),
    ],
)
def test_resolve_max_connections_clamps(
    lt_module, mock_lt, tmp_path, monkeypatch, raw, expected
):
    monkeypatch.setattr(lt_module, "lt", mock_lt)
    monkeypatch.setattr(lt_module, "LIBTORRENT_AVAILABLE", True)

    data_path = str(tmp_path / "data")
    os.makedirs(data_path, exist_ok=True)
    settings = {
        "dataPath": data_path,
        "download_path": os.path.join(data_path, "Downloads"),
        "max_connections": raw,
    }
    with patch.object(lt_module.LibTorrent, "initialize", lambda self: None):
        manager = lt_module.LibTorrent(settings)
    manager.settings = settings

    assert manager._resolve_max_connections() == expected


def test_set_max_connections_applies_to_live_session(
    lt_module, mock_lt, tmp_path, monkeypatch
):
    monkeypatch.setattr(lt_module, "lt", mock_lt)
    monkeypatch.setattr(lt_module, "LIBTORRENT_AVAILABLE", True)

    data_path = str(tmp_path / "data")
    os.makedirs(data_path, exist_ok=True)
    settings = {
        "dataPath": data_path,
        "download_path": os.path.join(data_path, "Downloads"),
        "max_connections": 200,
    }
    with patch.object(lt_module.LibTorrent, "initialize", lambda self: None):
        manager = lt_module.LibTorrent(settings)
    manager.settings = settings
    manager.session = MagicMock()

    resolved = manager.set_max_connections(42)

    assert resolved == 42
    assert manager.max_connections == 42
    assert manager.settings["max_connections"] == 42
    manager.session.apply_settings.assert_called_with({"connections_limit": 42})
