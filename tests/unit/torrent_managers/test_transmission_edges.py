"""Edge-case unit tests for the Transmission torrent adapter."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def Transmission():
    from adapters.torrent.transmission import Transmission as _T

    return _T


@pytest.fixture
def TorrentException():
    from adapters.torrent.base import TorrentException as _te

    return _te


@pytest.fixture
def TorrentListFilter():
    from adapters.torrent.base import TorrentListFilter as _f

    return _f


def _make_mgr(Transmission, client=None, settings=None):
    inst = object.__new__(Transmission)
    inst.settings = settings or {"url": "http://h:9091"}
    inst.url = "h"
    inst.port = 9091
    inst.login = None
    inst.password = None
    inst.client = client
    inst.name = "Transmission"
    # No-op logger so we don't depend on the full logger init.
    inst.log = lambda *a, **kw: None
    return inst


# ---------------------------------------------------------------------------
# add()
# ---------------------------------------------------------------------------


class TestAdd:
    def test_string_wrapped_in_list(self, Transmission):
        client = MagicMock()
        fake_t = SimpleNamespace(
            hashString="abc",
            get=lambda k, default=None: {
                "name": "n",
                "trackers": [],
                "total_size": 0,
                "percent_done": 0.0,
                "download_dir": "/x",
            }.get(k, default),
        )
        client.add_torrent.return_value = fake_t
        mgr = _make_mgr(Transmission, client=client)
        out = mgr.add("magnet:?xt=urn:btih:abc")
        assert len(out) == 1
        client.add_torrent.assert_called_once()

    def test_iterable_passed_through(self, Transmission):
        client = MagicMock()
        fake_t = SimpleNamespace(
            hashString="abc",
            get=lambda k, default=None: {
                "name": "n",
                "trackers": [],
                "total_size": 0,
                "percent_done": 0.0,
                "download_dir": "/x",
            }.get(k, default),
        )
        client.add_torrent.return_value = fake_t
        mgr = _make_mgr(Transmission, client=client)
        out = mgr.add(["m1", "m2"])
        assert len(out) == 2
        assert client.add_torrent.call_count == 2

    def test_none_yields_empty_list(self, Transmission):
        client = MagicMock()
        mgr = _make_mgr(Transmission, client=client)
        assert mgr.add(None) == []
        client.add_torrent.assert_not_called()

    def test_no_client_raises(self, Transmission, TorrentException):
        mgr = _make_mgr(Transmission, client=None)
        with pytest.raises(TorrentException):
            mgr.add(["m"])

    def test_client_exception_wrapped(self, Transmission, TorrentException):
        client = MagicMock()
        client.add_torrent.side_effect = RuntimeError("net err")
        mgr = _make_mgr(Transmission, client=client)
        with pytest.raises(TorrentException):
            mgr.add(["m"])


# ---------------------------------------------------------------------------
# list()
# ---------------------------------------------------------------------------


class TestList:
    def test_filter_all_resets_to_none(self, Transmission, TorrentListFilter):
        client = MagicMock()
        client.get_torrents.return_value = []
        mgr = _make_mgr(Transmission, client=client)
        result = mgr.list(filter=TorrentListFilter.ALL)
        assert result == []

    def test_filter_completed_uses_seeding(self, Transmission, TorrentListFilter):
        client = MagicMock()
        t1 = SimpleNamespace(
            seeding=True, seed_pending=False, downloading=False, download_pending=False,
            hashString="h1",
            get=lambda k, default=None: {"name": "x", "trackers": [], "total_size": 1, "percent_done": 0.0, "download_dir": ""}.get(k, default),
        )
        t2 = SimpleNamespace(
            seeding=False, seed_pending=False, downloading=True, download_pending=False,
            hashString="h2",
            get=lambda k, default=None: {"name": "y", "trackers": [], "total_size": 1, "percent_done": 0.0, "download_dir": ""}.get(k, default),
        )
        client.get_torrents.return_value = [t1, t2]
        mgr = _make_mgr(Transmission, client=client)
        out = mgr.list(filter=TorrentListFilter.COMPLETED)
        assert len(out) == 1

    def test_filter_downloading(self, Transmission, TorrentListFilter):
        client = MagicMock()
        t1 = SimpleNamespace(
            seeding=False, seed_pending=False, downloading=True, download_pending=False,
            hashString="h1",
            get=lambda k, default=None: {"name": "x", "trackers": [], "total_size": 1, "percent_done": 0.0, "download_dir": ""}.get(k, default),
        )
        client.get_torrents.return_value = [t1]
        mgr = _make_mgr(Transmission, client=client)
        out = mgr.list(filter=TorrentListFilter.DOWNLOADING)
        assert len(out) == 1

    def test_filter_unknown_treated_as_none(self, Transmission):
        client = MagicMock()
        client.get_torrents.return_value = []
        mgr = _make_mgr(Transmission, client=client)
        assert mgr.list(filter="NOPE") == []

    def test_invalid_hashes_filtered(self, Transmission):
        client = MagicMock()
        client.get_torrents.return_value = []
        mgr = _make_mgr(Transmission, client=client)
        good_hash = "a" * 40
        bad_short = "abc"
        bad_chars = "g" * 39 + "!"
        mgr.list(hashes=[good_hash, bad_short, bad_chars])
        client.get_torrents.assert_called_once_with([good_hash])

    def test_no_client_raises(self, Transmission, TorrentException):
        mgr = _make_mgr(Transmission, client=None)
        with pytest.raises(TorrentException):
            mgr.list()


# ---------------------------------------------------------------------------
# move()
# ---------------------------------------------------------------------------


class TestMove:
    def test_move_single_id(self, Transmission):
        client = MagicMock()
        mgr = _make_mgr(Transmission, client=client)
        mgr.move(["h1"], "/tmp")
        client.move_torrent_data.assert_called_once()
        kwargs = client.move_torrent_data.call_args.kwargs
        assert kwargs["ids"] == "h1"
        assert kwargs["location"] == "/tmp"

    def test_move_multiple_ids_loops(self, Transmission):
        client = MagicMock()
        mgr = _make_mgr(Transmission, client=client)
        mgr.move(["h1", "h2", "h3"], "/tmp")
        assert client.move_torrent_data.call_count == 3

    def test_move_string_hash_normalized(self, Transmission):
        client = MagicMock()
        mgr = _make_mgr(Transmission, client=client)
        mgr.move("h1", ["/a", "/b"])
        kwargs = client.move_torrent_data.call_args.kwargs
        # First path used.
        assert kwargs["location"] == "/a"

    def test_move_no_client_raises(self, Transmission, TorrentException):
        mgr = _make_mgr(Transmission, client=None)
        with pytest.raises(TorrentException):
            mgr.move(["h"], "/tmp")


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


class TestDelete:
    def test_delete_iterates(self, Transmission):
        client = MagicMock()
        mgr = _make_mgr(Transmission, client=client)
        mgr.delete(["h1", "h2"])
        assert client.remove_torrent.call_count == 2

    def test_delete_string_hash_wrapped(self, Transmission):
        client = MagicMock()
        mgr = _make_mgr(Transmission, client=client)
        mgr.delete("h1")
        client.remove_torrent.assert_called_once_with("h1", delete_data=True)

    def test_delete_no_client_raises(self, Transmission, TorrentException):
        mgr = _make_mgr(Transmission, client=None)
        with pytest.raises(TorrentException):
            mgr.delete(["h"])


# ---------------------------------------------------------------------------
# convert()
# ---------------------------------------------------------------------------


class TestConvert:
    def test_convert_extracts_fields(self, Transmission):
        mgr = _make_mgr(Transmission, client=MagicMock())
        data = SimpleNamespace(
            hashString="abc",
            get=lambda k, default=None: {
                "name": "Some Anime",
                "trackers": ["udp://t1"],
                "total_size": 1024,
                "percent_done": 0.5,
                "download_dir": "/data",
            }.get(k, default),
        )
        t = mgr.convert(data)
        assert t.hash == "abc"
        assert t.name == "Some Anime"
        assert t.trackers == ["udp://t1"]
        assert t.size == 1024
        # 50% of 1024 = 512
        assert t.downloaded == 512
        assert t.path == "/data"

    def test_convert_with_zero_size(self, Transmission):
        mgr = _make_mgr(Transmission, client=MagicMock())
        data = SimpleNamespace(
            hashString="abc",
            get=lambda k, default=None: {
                "name": "x",
                "trackers": [],
                "total_size": 0,
                "percent_done": 0.0,
                "download_dir": "",
            }.get(k, default),
        )
        t = mgr.convert(data)
        assert t.size == 0
        assert t.downloaded == 0
