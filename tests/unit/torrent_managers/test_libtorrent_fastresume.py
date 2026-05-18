"""Fastresume persistence tests for the LibTorrent adapter.

These tests exercise the on-disk ``.fastresume`` checkpoint pipeline
without spinning a real libtorrent session: the alert types and the
write/read helpers are stubbed on the adapter's module-level ``lt``
reference so the logic stays deterministic on CI machines that ship
without ``python-libtorrent`` installed.

The behaviour under test is the one the user-facing complaint is
about: starting the app after a clean shutdown must not lose the
torrents that were active or completed/seeding in the previous
session. The application restores from two complementary sources:

* :class:`DownloadManager` walks the persisted ``torrentsIndex`` and
  re-adds via magnet (tested in ``test_download_manager_edges``).
* :class:`LibTorrent` walks ``<dataPath>/.libtorrent_resume/*.fastresume``
  and re-adds with partial-state metadata, which is what allows a
  half-finished download to keep its progress instead of force-
  rechecking from scratch.

Both paths are idempotent: if a torrent has already been re-added by
one path, the other one's ``add_torrent`` call returns the existing
handle.
"""

from __future__ import annotations

import os
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


pytest.importorskip(
    "adapters.torrent.libtorrent",
    reason="LibTorrent adapter module is not importable",
)


def _make_libtorrent_adapter(tmp_path, monkeypatch):
    """Construct a LibTorrent instance with a stubbed ``lt`` module.

    Bypasses :meth:`BaseTorrentManager.__init__` so the test doesn't
    pay the cost of spinning a real libtorrent session; we exercise the
    fastresume helpers directly against an isolated tempdir.
    """
    from adapters.torrent import libtorrent as lt_module

    # Mark libtorrent as available so the constructor doesn't bail.
    monkeypatch.setattr(lt_module, "LIBTORRENT_AVAILABLE", True)
    # Stub out the libtorrent alert classes the adapter introspects.
    fake_lt = SimpleNamespace(
        save_resume_data_alert=type("save_resume_data_alert", (), {}),
        save_resume_data_failed_alert=type(
            "save_resume_data_failed_alert", (), {}
        ),
        metadata_received_alert=type("metadata_received_alert", (), {}),
        torrent_added_alert=type("torrent_added_alert", (), {}),
        torrent_removed_alert=type("torrent_removed_alert", (), {}),
        torrent_error_alert=type("torrent_error_alert", (), {}),
        bencode=lambda v: b"BENC|" + str(v).encode("utf-8"),
        write_resume_data_buf=lambda params: bytes(params),
        read_resume_data=lambda blob: SimpleNamespace(
            save_path="", resume_data=blob
        ),
    )
    monkeypatch.setattr(lt_module, "lt", fake_lt)

    adapter = lt_module.LibTorrent.__new__(lt_module.LibTorrent)
    adapter.session = MagicMock()
    adapter.handles = {}
    adapter._running = False
    adapter._thread = None
    adapter.download_path = str(tmp_path / "downloads")
    os.makedirs(adapter.download_path, exist_ok=True)
    adapter._resume_data_dir = str(tmp_path / ".libtorrent_resume")
    os.makedirs(adapter._resume_data_dir, exist_ok=True)
    adapter._last_resume_save = 0.0
    return adapter, fake_lt, lt_module


class TestFastResumeChecking:
    def test_persist_resume_alert_writes_atomic_file(
        self, tmp_path, monkeypatch
    ):
        adapter, fake_lt, _ = _make_libtorrent_adapter(tmp_path, monkeypatch)
        handle = SimpleNamespace(info_hash=lambda: "a" * 40)
        params = b"resume-data-blob"
        alert = SimpleNamespace(handle=handle, params=params, resume_data=None)
        adapter._persist_resume_alert(alert)

        out = os.path.join(adapter._resume_data_dir, ("a" * 40) + ".fastresume")
        assert os.path.isfile(out)
        with open(out, "rb") as f:
            assert f.read() == params

    def test_persist_resume_alert_falls_back_to_bencode(
        self, tmp_path, monkeypatch
    ):
        """Old libtorrent builds expose ``alert.resume_data`` + bencode
        instead of ``alert.params`` + ``write_resume_data_buf``."""
        adapter, fake_lt, _ = _make_libtorrent_adapter(tmp_path, monkeypatch)
        # Strip the modern API to force the fallback path.
        del fake_lt.write_resume_data_buf

        handle = SimpleNamespace(info_hash=lambda: "b" * 40)
        alert = SimpleNamespace(
            handle=handle, params=None, resume_data={"libtorrent": "entry"}
        )
        adapter._persist_resume_alert(alert)

        out = os.path.join(adapter._resume_data_dir, ("b" * 40) + ".fastresume")
        assert os.path.isfile(out)
        with open(out, "rb") as f:
            assert f.read().startswith(b"BENC|")

    def test_persist_resume_alert_skips_when_no_dir(
        self, tmp_path, monkeypatch
    ):
        adapter, fake_lt, _ = _make_libtorrent_adapter(tmp_path, monkeypatch)
        adapter._resume_data_dir = None
        handle = SimpleNamespace(info_hash=lambda: "c" * 40)
        alert = SimpleNamespace(handle=handle, params=b"x", resume_data=None)
        # Must not raise; just silently no-op.
        adapter._persist_resume_alert(alert)

    def test_delete_resume_file_idempotent(self, tmp_path, monkeypatch):
        adapter, *_ = _make_libtorrent_adapter(tmp_path, monkeypatch)
        path = os.path.join(adapter._resume_data_dir, ("d" * 40) + ".fastresume")
        with open(path, "wb") as f:
            f.write(b"x")
        adapter._delete_resume_file("d" * 40)
        assert not os.path.exists(path)
        # Calling again is a no-op rather than an error.
        adapter._delete_resume_file("d" * 40)

    def test_load_resume_data_dir_readds_each_blob(
        self, tmp_path, monkeypatch
    ):
        adapter, fake_lt, _ = _make_libtorrent_adapter(tmp_path, monkeypatch)
        # Two valid resume files plus a junk filename that must be skipped.
        good_a = "1" * 40
        good_b = "2" * 40
        for name, payload in (
            (good_a + ".fastresume", b"AAA"),
            (good_b + ".fastresume", b"BBB"),
            ("not-a-hash.fastresume", b"ignored"),
        ):
            with open(os.path.join(adapter._resume_data_dir, name), "wb") as f:
                f.write(payload)

        # The session's add_torrent must return a handle whose info_hash
        # reflects the blob so the adapter can map it back.
        added: list[bytes] = []

        class _Handle:
            def __init__(self, payload):
                self._payload = payload

            def info_hash(self):
                if self._payload == b"AAA":
                    return good_a
                if self._payload == b"BBB":
                    return good_b
                return "x" * 40

        def fake_add_torrent(params):
            added.append(params.resume_data)
            return _Handle(params.resume_data)

        adapter.session.add_torrent.side_effect = fake_add_torrent
        adapter._load_resume_data_dir()
        # Only the two well-named files should have been re-added.
        assert sorted(added) == [b"AAA", b"BBB"]
        # And both handles registered for live polling.
        assert good_a in adapter.handles
        assert good_b in adapter.handles

    def test_load_resume_data_dir_swallows_io_errors(
        self, tmp_path, monkeypatch
    ):
        adapter, fake_lt, _ = _make_libtorrent_adapter(tmp_path, monkeypatch)
        bad = "3" * 40 + ".fastresume"
        with open(os.path.join(adapter._resume_data_dir, bad), "wb") as f:
            f.write(b"GARBAGE")

        # First call works (we get a handle); the second blob raises.
        def boom(blob):
            raise RuntimeError("corrupt fastresume")

        fake_lt.read_resume_data = boom
        # Must not propagate.
        adapter._load_resume_data_dir()

    def test_periodic_save_throttles_to_interval(
        self, tmp_path, monkeypatch
    ):
        adapter, *_ = _make_libtorrent_adapter(tmp_path, monkeypatch)
        handle = MagicMock()
        handle.is_valid.return_value = True
        handle.has_metadata.return_value = True
        adapter.handles = {"h": handle}

        # First call requests resume data; second call (immediately
        # after) is throttled so we don't flood the alert queue.
        adapter._maybe_request_periodic_resume_save()
        adapter._maybe_request_periodic_resume_save()
        assert handle.save_resume_data.call_count == 1


class TestResumeDataBlob:
    def test_blob_prefers_modern_api(self, tmp_path, monkeypatch):
        adapter, fake_lt, _ = _make_libtorrent_adapter(tmp_path, monkeypatch)
        alert = SimpleNamespace(params=b"PAYLOAD", resume_data=None)
        assert adapter._resume_data_blob(alert) == b"PAYLOAD"

    def test_blob_returns_none_when_no_api_available(
        self, tmp_path, monkeypatch
    ):
        adapter, fake_lt, _ = _make_libtorrent_adapter(tmp_path, monkeypatch)
        del fake_lt.write_resume_data_buf
        del fake_lt.bencode
        alert = SimpleNamespace(params=None, resume_data=None)
        assert adapter._resume_data_blob(alert) is None
