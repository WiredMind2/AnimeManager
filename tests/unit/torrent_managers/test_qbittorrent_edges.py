"""Edge-case unit tests for the qBittorrent torrent adapter.

The adapter wraps the `qbittorrentapi` package. All network interaction is
patched so the tests never reach a real qBittorrent instance.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def qBittorrent():
    from adapters.torrent.qbittorrent import qBittorrent as _qb

    return _qb


@pytest.fixture
def TorrentException():
    from adapters.torrent.base import TorrentException as _te

    return _te


@pytest.fixture
def TorrentListFilter():
    from adapters.torrent.base import TorrentListFilter as _f

    return _f


def _make_mgr(qBittorrent, qb_client=None, settings=None):
    """Construct a `qBittorrent` adapter without invoking its network init."""
    inst = object.__new__(qBittorrent)
    inst.qb = qb_client
    inst.settings = settings or {"url": "http://localhost:8081"}
    inst.url = inst.settings.get("url", "")
    inst.login = inst.settings.get("user", "")
    inst.password = inst.settings.get("password", "")
    inst.timeout = 0.05  # very short so tests don't hang
    inst.login_event = threading.Event()
    if qb_client is not None:
        inst.login_event.set()
    return inst


# ---------------------------------------------------------------------------
# add()
# ---------------------------------------------------------------------------


class TestAdd:
    def test_add_string_wraps_in_list(self, qBittorrent):
        qb_client = MagicMock()
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        mgr.add("magnet:?xt=urn:btih:abc")
        qb_client.torrents_add.assert_called_once()
        called_kwargs = qb_client.torrents_add.call_args.kwargs
        assert called_kwargs["urls"] == ["magnet:?xt=urn:btih:abc"]

    def test_add_list_passes_through(self, qBittorrent):
        qb_client = MagicMock()
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        mgr.add(["m1", "m2"])
        called_kwargs = qb_client.torrents_add.call_args.kwargs
        assert called_kwargs["urls"] == ["m1", "m2"]

    def test_add_none_becomes_empty_list(self, qBittorrent):
        qb_client = MagicMock()
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        mgr.add(None)
        called_kwargs = qb_client.torrents_add.call_args.kwargs
        assert called_kwargs["urls"] == []

    def test_add_no_client_raises(self, qBittorrent, TorrentException):
        mgr = _make_mgr(qBittorrent, qb_client=None)
        # No client + login_event not set in the wait_connection path raises.
        mgr.login_event = None
        with pytest.raises(TorrentException):
            mgr.add(["m"])

    def test_add_remote_exception_wraps(self, qBittorrent, TorrentException):
        qb_client = MagicMock()
        qb_client.torrents_add.side_effect = RuntimeError("network down")
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        with pytest.raises(TorrentException):
            mgr.add(["m"])


# ---------------------------------------------------------------------------
# list()
# ---------------------------------------------------------------------------


class TestList:
    def test_list_all_filter_mapped(self, qBittorrent, TorrentListFilter):
        qb_client = MagicMock()
        qb_client.torrents_info.return_value = SimpleNamespace(data=[])
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        mgr.list(filter=TorrentListFilter.ALL)
        assert qb_client.torrents_info.call_args.kwargs["status_filter"] == "all"

    def test_list_completed_filter_mapped(self, qBittorrent, TorrentListFilter):
        qb_client = MagicMock()
        qb_client.torrents_info.return_value = SimpleNamespace(data=[])
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        mgr.list(filter=TorrentListFilter.COMPLETED)
        assert qb_client.torrents_info.call_args.kwargs["status_filter"] == "completed"

    def test_list_downloading_filter_mapped(self, qBittorrent, TorrentListFilter):
        qb_client = MagicMock()
        qb_client.torrents_info.return_value = SimpleNamespace(data=[])
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        mgr.list(filter=TorrentListFilter.DOWNLOADING)
        assert qb_client.torrents_info.call_args.kwargs["status_filter"] == "downloading"

    def test_list_unknown_filter_becomes_none(self, qBittorrent):
        qb_client = MagicMock()
        qb_client.torrents_info.return_value = SimpleNamespace(data=[])
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        mgr.list(filter="UNKNOWN_OPTION")
        assert qb_client.torrents_info.call_args.kwargs["status_filter"] is None

    def test_list_empty_hashes_become_none(self, qBittorrent):
        qb_client = MagicMock()
        qb_client.torrents_info.return_value = SimpleNamespace(data=[])
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        mgr.list(hashes=[])
        assert qb_client.torrents_info.call_args.kwargs["torrent_hashes"] is None

    def test_list_returns_converted_items(self, qBittorrent):
        qb_client = MagicMock()
        items = [SimpleNamespace(hash="abc", name="One", magnet_uri=""),
                 SimpleNamespace(hash="def", name="Two", magnet_uri="")]
        qb_client.torrents_info.return_value = SimpleNamespace(data=items)
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        out = mgr.list()
        assert len(out) == 2

    def test_list_no_client_raises(self, qBittorrent, TorrentException):
        mgr = _make_mgr(qBittorrent, qb_client=None)
        mgr.login_event = None
        with pytest.raises(TorrentException):
            mgr.list()


# ---------------------------------------------------------------------------
# move()
# ---------------------------------------------------------------------------


class TestMove:
    def test_move_empty_hashes_no_op(self, qBittorrent):
        qb_client = MagicMock()
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        mgr.move([], "/tmp")
        qb_client.torrents_set_location.assert_not_called()

    def test_move_with_list_paths_uses_first(self, qBittorrent):
        qb_client = MagicMock()
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        mgr.move(["h1"], ["/a", "/b"])
        kwargs = qb_client.torrents_set_location.call_args.kwargs
        assert kwargs["location"] == "/a"
        assert kwargs["torrent_hashes"] == ["h1"]

    def test_move_with_empty_paths_list_raises(self, qBittorrent, TorrentException):
        qb_client = MagicMock()
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        with pytest.raises(TorrentException):
            mgr.move(["h1"], [])

    def test_move_with_string_path(self, qBittorrent):
        qb_client = MagicMock()
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        mgr.move(["h"], "/tmp")
        assert qb_client.torrents_set_location.call_args.kwargs["location"] == "/tmp"

    def test_move_with_none_path_raises(self, qBittorrent, TorrentException):
        qb_client = MagicMock()
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        with pytest.raises(TorrentException):
            mgr.move(["h"], None)


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


class TestDelete:
    def test_delete_passes_hashes(self, qBittorrent):
        qb_client = MagicMock()
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        mgr.delete(["h1", "h2"])
        kwargs = qb_client.torrents_delete.call_args.kwargs
        assert kwargs["torrent_hashes"] == ["h1", "h2"]
        assert kwargs["delete_files"] is True

    def test_delete_no_client_raises(self, qBittorrent, TorrentException):
        mgr = _make_mgr(qBittorrent, qb_client=None)
        mgr.login_event = None
        with pytest.raises(TorrentException):
            mgr.delete(["h"])


# ---------------------------------------------------------------------------
# convert()
# ---------------------------------------------------------------------------


class TestConvert:
    def test_convert_with_magnet_uri(self, qBittorrent):
        mgr = _make_mgr(qBittorrent, qb_client=MagicMock())
        with patch("adapters.persistence.models.Torrent.from_magnet") as fm:
            fake_torrent = SimpleNamespace(size=None, downloaded=None, path=None)
            fm.return_value = fake_torrent
            data = SimpleNamespace(
                magnet_uri="magnet:?xt=urn:btih:abc",
                size=100,
                completed=50,
                save_path="/tmp",
            )
            t = mgr.convert(data)
            assert t is fake_torrent
            assert t.size == 100
            assert t.downloaded == 50
            assert t.path == "/tmp"

    def test_convert_without_magnet(self, qBittorrent):
        mgr = _make_mgr(qBittorrent, qb_client=MagicMock())
        data = SimpleNamespace(
            magnet_uri="",
            hash="abc",
            name="Foo",
            size=10,
            completed=5,
            save_path="/x",
        )
        t = mgr.convert(data)
        assert t.size == 10
        assert t.downloaded == 5
        assert t.path == "/x"

    def test_convert_magnet_failed_uses_fallback(self, qBittorrent):
        mgr = _make_mgr(qBittorrent, qb_client=MagicMock())
        with patch("adapters.persistence.models.Torrent.from_magnet", return_value=False):
            data = SimpleNamespace(
                magnet_uri="magnet:?xt=urn:btih:abc",
                hash="abc",
                name="Foo",
                size=10,
                completed=5,
                save_path="/x",
            )
            t = mgr.convert(data)
            # Falls back to Torrent(hash, name); convert still applies extras.
            assert t.size == 10
            assert t.downloaded == 5

    def test_convert_handles_missing_attrs_safely(self, qBittorrent):
        mgr = _make_mgr(qBittorrent, qb_client=MagicMock())
        # Object that throws on .size to exercise the try/except branches.

        class _Bad:
            magnet_uri = ""
            hash = "h"
            name = "n"

            @property
            def size(self):
                raise RuntimeError("bad")

            @property
            def completed(self):
                raise RuntimeError("bad")

            @property
            def save_path(self):
                raise RuntimeError("bad")

        t = mgr.convert(_Bad())
        assert t.size is None
        assert t.downloaded is None
        assert t.path is None


# ---------------------------------------------------------------------------
# wait_connection decorator
# ---------------------------------------------------------------------------


class TestWaitConnection:
    def test_wait_connection_raises_when_login_event_is_none(
        self, qBittorrent, TorrentException
    ):
        mgr = _make_mgr(qBittorrent, qb_client=None)
        mgr.login_event = None
        with pytest.raises(TorrentException):
            mgr.add(["m"])

    def test_wait_connection_succeeds_when_set(self, qBittorrent):
        qb_client = MagicMock()
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        # event was set in fixture
        mgr.add("magnet:?xt=urn:btih:abc")
        qb_client.torrents_add.assert_called_once()

    def test_wait_connection_times_out(self, qBittorrent, TorrentException):
        mgr = _make_mgr(qBittorrent, qb_client=None)
        mgr.login_event = threading.Event()  # never set
        mgr.timeout = 0.01
        with pytest.raises(TorrentException):
            mgr.add(["m"])


# ---------------------------------------------------------------------------
# list_files()
# ---------------------------------------------------------------------------


class TestListFiles:
    def test_list_files_joins_save_path(self, qBittorrent):
        qb_client = MagicMock()
        qb_client.torrents_files.return_value = [
            SimpleNamespace(name="[ANi] Example - 01.mp4"),
            SimpleNamespace(name="readme.txt"),
        ]
        qb_client.torrents_info.return_value = [
            SimpleNamespace(save_path=r"C:\Anime\Show - 7"),
        ]
        mgr = _make_mgr(qBittorrent, qb_client=qb_client)
        paths = mgr.list_files("abc123")
        assert paths == [
            r"C:\Anime\Show - 7\[ANi] Example - 01.mp4",
            r"C:\Anime\Show - 7\readme.txt",
        ]
        qb_client.torrents_files.assert_called_once_with(torrent_hash="abc123")

    def test_list_files_raises_without_client(self, qBittorrent, TorrentException):
        mgr = _make_mgr(qBittorrent, qb_client=None)
        with pytest.raises(TorrentException):
            mgr.list_files("abc123")
