"""Tests for :class:`LibTorrentRemote`."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adapters.torrent.libtorrent_remote import LibTorrentRemote


@pytest.fixture(autouse=True)
def _daemon_env(monkeypatch):
    monkeypatch.setenv("LIBTORRENT_DAEMON_URL", "http://torrent:8090")
    monkeypatch.setenv("LIBTORRENT_DAEMON_TOKEN", "secret")


def _response(payload):
    mock = MagicMock()
    mock.status_code = 200
    mock.content = b"{}"
    mock.json.return_value = payload
    return mock


def test_remote_add_posts_to_daemon():
    responses = [
        _response({"ready": True}),
        _response({"added": [{"hash": "abc"}]}),
        _response({"torrents": [{"hash": "abc"}]}),
    ]

    with patch(
        "adapters.torrent.libtorrent_remote.requests.request",
        side_effect=responses,
    ) as req:
        mgr = LibTorrentRemote({}, update=False)
        added = mgr.add(["magnet:?xt=urn:btih:abc"])

    assert added == [{"hash": "abc"}]
    post_calls = [c for c in req.call_args_list if c.args[0] == "POST"]
    assert post_calls[0].args[1].endswith("/torrents")
    assert post_calls[0].kwargs["headers"]["X-Libtorrent-Token"] == "secret"


def test_remote_ensure_restored_posts_rows():
    calls = []

    def _request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/health"):
            return _response({"ready": True})
        return _response({"ok": True, "torrent_count": 1})

    with patch("adapters.torrent.libtorrent_remote.requests.request", side_effect=_request):
        mgr = LibTorrentRemote({}, update=False)
        mgr.set_restore_callback(lambda: [{"hash": "abc", "save_path": "/data"}])
        mgr.ensure_restored()

    restore = [c for c in calls if c[0] == "POST" and c[1].endswith("/session/ensure-restored")]
    assert restore
    assert restore[0][2]["json"]["rows"][0]["hash"] == "abc"


def test_remote_purge_deleted_filters_by_status():
    def _request(method, url, **kwargs):
        if url.endswith("/health"):
            return _response({"ready": True})
        if url.endswith("/session/resume-hashes"):
            return _response({"hashes": ["dead", "live"]})
        if url.endswith("/torrents") and method == "GET":
            return _response({"torrents": []})
        if url.endswith("/session/purge-deleted"):
            return _response({"purged": 1})
        raise AssertionError((method, url))

    with patch("adapters.torrent.libtorrent_remote.requests.request", side_effect=_request):
        mgr = LibTorrentRemote({}, update=False)
        mgr.set_torrent_status_callback(lambda h: "deleted" if h == "dead" else None)
        purged = mgr.purge_deleted_torrents()

    assert purged == 1
