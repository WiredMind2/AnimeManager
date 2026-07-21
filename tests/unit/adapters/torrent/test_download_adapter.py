"""Tests for :class:`DownloadAdapter`."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adapters.torrent.download_adapter import DownloadAdapter


def _make_adapter(**overrides):
    defaults = dict(
        torrent_manager=MagicMock(name="LibTorrent"),
        file_manager=MagicMock(),
        db_manager=MagicMock(
            list_torrents_for_restore=MagicMock(return_value=[{"hash": "h1"}]),
            get_torrent_status=MagicMock(return_value="complete"),
        ),
        scanner=MagicMock(resolve_anime_folder=MagicMock(return_value="/anime/1")),
        user_actions=MagicMock(
            get_user_state=MagicMock(return_value={"tag": "WATCHLIST"})
        ),
    )
    defaults.update(overrides)
    with patch("adapters.torrent.download_adapter.DownloadManager") as dm_cls:
        dm = MagicMock()
        dm_cls.return_value = dm
        adapter = DownloadAdapter(**defaults)
    return adapter, dm


def test_libtorrent_restore_callbacks_wired():
    tm = MagicMock(name="LibTorrent")
    tm.name = "LibTorrent"
    restore_rows = []
    status_calls = []
    purge_calls = []

    def _set_restore(cb):
        restore_rows.append(cb())

    def _set_status(cb):
        status_calls.append(cb("abc"))

    tm.set_restore_callback = _set_restore
    tm.set_torrent_status_callback = _set_status
    tm.purge_deleted_torrents = lambda: purge_calls.append(True) or 1

    db = MagicMock()
    db.list_torrents_for_restore.return_value = [{"hash": "abc"}]
    db.get_torrent_status.return_value = "complete"

    with patch("adapters.torrent.download_adapter.DownloadManager"):
        DownloadAdapter(
            torrent_manager=tm,
            file_manager=MagicMock(),
            db_manager=db,
            scanner=MagicMock(),
            user_actions=MagicMock(),
        )

    assert restore_rows == [[{"hash": "abc"}]]
    assert status_calls == ["complete"]
    assert purge_calls == [True]


def test_libtorrent_skipped_for_non_libtorrent_manager():
    tm = MagicMock()
    tm.name = "qBittorrent"
    with patch("adapters.torrent.download_adapter.DownloadManager"):
        DownloadAdapter(
            torrent_manager=tm,
            file_manager=MagicMock(),
            db_manager=MagicMock(),
            scanner=MagicMock(),
            user_actions=MagicMock(),
        )
    tm.set_restore_callback.assert_not_called()


def test_promote_watching_on_download_start():
    user_actions = MagicMock(
        get_user_state=MagicMock(return_value={"tag": "WATCHLIST"})
    )
    adapter, _ = _make_adapter(user_actions=user_actions)
    adapter._promote_watching_on_download_start(1, 1)
    user_actions.set_tag.assert_called_once_with(1, "WATCHING", 1)


def test_promote_watching_skips_when_already_watching():
    user_actions = MagicMock(
        get_user_state=MagicMock(return_value={"tag": "WATCHING"})
    )
    adapter, _ = _make_adapter(user_actions=user_actions)
    adapter._promote_watching_on_download_start(1, 1)
    user_actions.set_tag.assert_not_called()


def test_promote_watching_swallows_errors():
    user_actions = MagicMock(get_user_state=MagicMock(side_effect=RuntimeError))
    adapter, _ = _make_adapter(user_actions=user_actions)
    adapter._promote_watching_on_download_start(1, 1)


def test_start_download_returns_true_when_queued():
    adapter, dm = _make_adapter()
    dm.download_file.return_value = object()
    assert adapter.start_download(1, url="magnet:?", user_id=1) is True
    dm.download_file.assert_called_once()


def test_start_download_returns_false_when_not_queued():
    adapter, dm = _make_adapter()
    dm.download_file.return_value = None
    assert adapter.start_download(1) is False


def test_get_download_progress_and_cancel():
    adapter, dm = _make_adapter()
    dm.get_download_status.return_value = {"progress": 50}
    assert adapter.get_download_progress(1) == {"progress": 50}
    dm.cancel_download.return_value = True
    assert adapter.cancel_download(1) is True


def test_pause_and_resume_torrent():
    adapter, dm = _make_adapter()
    dm.pause_torrent.return_value = True
    dm.resume_torrent.return_value = True
    assert adapter.pause_torrent("abc") is True
    assert adapter.resume_torrent("abc") is True
    dm.pause_torrent.assert_called_once_with("abc")
    dm.resume_torrent.assert_called_once_with("abc")


def test_get_active_downloads():
    adapter, dm = _make_adapter()
    dm.get_active_downloads.return_value = [{"anime_id": 1}]
    assert adapter.get_active_downloads() == [{"anime_id": 1}]


def test_get_torrents_overview_fallback():
    adapter, dm = _make_adapter()
    del dm.get_torrents_overview
    overview = adapter.get_torrents_overview()
    assert overview == {
        "active": [],
        "seeding": [],
        "completed": [],
        "error": [],
        "other": [],
    }


def test_reconcile_deleted_torrents():
    adapter, dm = _make_adapter()
    dm.reconcile_deleted_torrents.return_value = 3
    assert adapter.reconcile_deleted_torrents() == 3


def test_apply_max_connections_delegates_to_libtorrent():
    tm = MagicMock()
    tm.name = "LibTorrent"
    tm.set_max_connections.return_value = 55
    adapter, _ = _make_adapter(torrent_manager=tm)
    assert adapter.apply_max_connections(55) == 55
    tm.set_max_connections.assert_called_once_with(55)


def test_apply_max_connections_noop_for_other_clients():
    tm = MagicMock()
    tm.name = "qBittorrent"
    adapter, _ = _make_adapter(torrent_manager=tm)
    assert adapter.apply_max_connections(55) is None
    tm.set_max_connections.assert_not_called()


def test_mark_torrents_deleted_for_seen_anime():
    adapter, dm = _make_adapter()
    dm.mark_torrents_deleted_for_seen_anime.return_value = 2
    assert adapter.mark_torrents_deleted_for_seen_anime(9) == 2
    dm.mark_torrents_deleted_for_seen_anime.assert_called_once()
    args, kwargs = dm.mark_torrents_deleted_for_seen_anime.call_args
    assert args[0] == 9
    assert callable(args[1])
    assert "animes_root" in kwargs


def test_reconcile_seen_anime_torrents():
    user_actions = MagicMock(
        list_anime_ids_with_tag=MagicMock(return_value=[1, 2, 3])
    )
    adapter, dm = _make_adapter(user_actions=user_actions)
    dm.mark_torrents_deleted_for_seen_anime.side_effect = [1, 0, 2]
    assert adapter.reconcile_seen_anime_torrents() == 3
    user_actions.list_anime_ids_with_tag.assert_called_once_with("SEEN")
    assert dm.mark_torrents_deleted_for_seen_anime.call_count == 3


def test_search_torrents_sorts_by_seeds():
    adapter, _ = _make_adapter()
    rows = [
        {"name": "low", "seeds": 1},
        {"name": "high", "seeds": 99},
    ]
    with patch("adapters.torrent.download_adapter.SearchFacade") as facade_cls:
        facade_cls.return_value.search.return_value = rows
        results = adapter.search_torrents(["naruto"])
    assert [r["name"] for r in results] == ["high", "low"]


def test_search_torrents_limit_overrides_per_term_cap():
    adapter, _ = _make_adapter()
    with patch("adapters.torrent.download_adapter.SearchFacade") as facade_cls:
        facade_cls.return_value.search.return_value = []
        adapter.search_torrents(["naruto"], limit=3)
    profile = facade_cls.call_args.kwargs["profile"]
    assert profile.limits.max_results_per_term == 3


def test_stream_torrents_has_no_global_row_cap():
    adapter, _ = _make_adapter()
    rows = [{"name": f"t{i}", "seeds": i} for i in range(5)]
    with patch("adapters.torrent.download_adapter.SearchFacade") as facade_cls:
        facade_cls.return_value.search.return_value = iter(rows)
        streamed = list(adapter.stream_torrents(["x"]))
    assert len(streamed) == 5


def test_close_shuts_down_managers():
    adapter, dm = _make_adapter()
    tm = adapter._torrent_manager
    adapter.close()
    dm.close.assert_called_once()
    tm.close.assert_called_once()


def test_close_tolerates_errors():
    adapter, dm = _make_adapter()
    dm.close.side_effect = RuntimeError("boom")
    adapter._torrent_manager.close.side_effect = RuntimeError("boom")
    adapter.close()
