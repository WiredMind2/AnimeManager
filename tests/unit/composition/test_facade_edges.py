"""Tests for the transport-agnostic ``composition.facade.EmbeddedClientFacade``.

These tests verify that the facade is a thin pass-through over the
:class:`AnimeApplicationService`, with no extra logic of its own.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from composition.facade import EmbeddedClientFacade
from domain.dto import AnimeListRequest, DownloadRequest, SearchRequest


@pytest.fixture
def service():
    svc = MagicMock()
    return svc


@pytest.fixture
def facade(service):
    return EmbeddedClientFacade(service)


def test_search_anime_forwards_query_and_limit(facade, service):
    service.search_anime.return_value = ["a"]
    out = facade.search_anime("naruto", limit=12)
    service.search_anime.assert_called_once_with(SearchRequest(query="naruto", limit=12))
    assert out == ["a"]


def test_get_anime_list_forwards_dto(facade, service):
    facade.get_anime_list(
        filter_name="LIKED",
        user_id=2,
        list_start=10,
        list_stop=20,
        hide_rated=True,
    )
    service.get_anime_list.assert_called_once_with(
        AnimeListRequest(
            filter="LIKED",
            user_id=2,
            list_start=10,
            list_stop=20,
            hide_rated=True,
        )
    )


def test_get_anime_list_uses_defaults(facade, service):
    facade.get_anime_list()
    service.get_anime_list.assert_called_once_with(
        AnimeListRequest(
            filter="DEFAULT",
            user_id=None,
            list_start=0,
            list_stop=50,
            hide_rated=None,
        )
    )


def test_get_anime_details_forwards_id(facade, service):
    facade.get_anime_details(42)
    service.get_anime_details.assert_called_once_with(42)


def test_start_download_forwards_dto(facade, service):
    facade.start_download(7, url="u", hash_value="h", user_id=3)
    service.start_download.assert_called_once_with(
        DownloadRequest(anime_id=7, url="u", hash_value="h", user_id=3)
    )


def test_start_download_minimal_args(facade, service):
    facade.start_download(7)
    service.start_download.assert_called_once_with(
        DownloadRequest(anime_id=7, url=None, hash_value=None, user_id=None)
    )


def test_get_download_progress_passes_through(facade, service):
    service.get_download_progress.return_value = {"x": 1}
    assert facade.get_download_progress(1) == {"x": 1}
    service.get_download_progress.assert_called_once_with(1)


def test_cancel_download_returns_bool(facade, service):
    service.cancel_download.return_value = True
    assert facade.cancel_download(1) is True


def test_get_active_downloads_returns_list(facade, service):
    service.get_active_downloads.return_value = [{"x": 1}]
    assert facade.get_active_downloads() == [{"x": 1}]


def test_search_torrents_forwards_args(facade, service):
    facade.search_torrents(["a", "b"], profile="strict", limit=50)
    service.search_torrents.assert_called_once_with(
        ["a", "b"], profile="strict", limit=50
    )


def test_set_tag_forwards(facade, service):
    facade.set_tag(1, "LIKED", 4)
    service.set_tag.assert_called_once_with(1, "LIKED", 4)


def test_set_like_forwards(facade, service):
    facade.set_like(1, 4, liked=False)
    service.set_like.assert_called_once_with(1, 4, False)


def test_set_like_default_true(facade, service):
    facade.set_like(1, 4)
    service.set_like.assert_called_once_with(1, 4, True)


def test_mark_seen_forwards(facade, service):
    facade.mark_seen(1, "ep.mkv", 7)
    service.mark_seen.assert_called_once_with(1, "ep.mkv", 7)


def test_get_user_state_forwards(facade, service):
    service.get_user_state.return_value = {"tag": "X"}
    assert facade.get_user_state(1, 2) == {"tag": "X"}
    service.get_user_state.assert_called_once_with(1, 2)


def test_get_search_terms_forwards(facade, service):
    service.get_search_terms.return_value = ["a"]
    assert facade.get_search_terms(1) == ["a"]


def test_add_search_term_forwards(facade, service):
    service.add_search_term.return_value = True
    assert facade.add_search_term(1, "t") is True


def test_remove_search_term_forwards(facade, service):
    service.remove_search_term.return_value = True
    assert facade.remove_search_term(1, "t") is True


def test_get_last_torrent_search_query_forwards(facade, service):
    service.get_last_torrent_search_query.return_value = "a, b"
    assert facade.get_last_torrent_search_query(3) == "a, b"
    service.get_last_torrent_search_query.assert_called_once_with(3)


def test_set_last_torrent_search_query_forwards(facade, service):
    facade.set_last_torrent_search_query(2, "x, y")
    service.set_last_torrent_search_query.assert_called_once_with(2, "x, y")


def test_get_settings_returns_dict(facade, service):
    service.get_settings.return_value = {"x": 1}
    assert facade.get_settings() == {"x": 1}


def test_update_settings_forwards(facade, service):
    facade.update_settings({"a": 1})
    service.update_settings.assert_called_once_with({"a": 1})


def test_get_relations_default_anime_type(facade, service):
    service.get_relations.return_value = []
    facade.get_relations(1)
    service.get_relations.assert_called_once_with(1, "anime")


def test_get_relations_custom_type(facade, service):
    facade.get_relations(1, relation_type="manga")
    service.get_relations.assert_called_once_with(1, "manga")


def test_list_anime_characters_forwards(facade, service):
    service.list_anime_characters.return_value = [{"id": 1, "name": "A"}]
    assert facade.list_anime_characters(5) == [{"id": 1, "name": "A"}]
    service.list_anime_characters.assert_called_once_with(5)


def test_service_errors_propagate(facade, service):
    service.get_anime_details.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        facade.get_anime_details(1)


def test_stream_search_anime_uses_streamer_when_present(facade, service):
    def _stream(req):
        yield f"item-{req.query}"

    service.stream_search_anime = _stream
    assert list(facade.stream_search_anime("abc", limit=3)) == ["item-abc"]
    service.search_anime.assert_not_called()


def test_stream_search_anime_falls_back_to_search(facade, service):
    del service.stream_search_anime
    service.search_anime.return_value = ["x", "y"]
    assert list(facade.stream_search_anime("q", limit=5)) == ["x", "y"]
    service.search_anime.assert_called_once_with(SearchRequest(query="q", limit=5))


def test_startup_jobs_property_and_run(facade, service):
    jobs = MagicMock()
    report = MagicMock()
    jobs.run.return_value = report
    facade_with_jobs = EmbeddedClientFacade(service, startup_jobs=jobs)
    assert facade_with_jobs.startup_jobs is jobs
    assert facade_with_jobs.run_startup_jobs() is report
    jobs.run.assert_called_once()


def test_startup_jobs_absent_returns_none(facade):
    assert facade.startup_jobs is None
    assert facade.run_startup_jobs() is None
    assert facade.kickoff_startup_jobs() is None


def test_kickoff_startup_jobs_returns_thread(facade, service):
    jobs = MagicMock()
    thread = MagicMock()
    jobs.run_in_background.return_value = thread
    out = EmbeddedClientFacade(service, startup_jobs=jobs).kickoff_startup_jobs()
    assert out is thread
    jobs.run_in_background.assert_called_once()


def test_refresh_delete_folder_and_redownload(facade, service):
    facade.refresh_anime_metadata(9)
    service.refresh_anime_metadata.assert_called_once_with(9)
    service.delete_anime.return_value = True
    assert facade.delete_anime(9) is True
    service.get_anime_folder.return_value = "/anime/9"
    assert facade.get_anime_folder(9) == "/anime/9"
    service.redownload.return_value = 2
    assert facade.redownload(9) == 2


def test_torrent_overview_and_stream(facade, service):
    service.get_torrents_overview.return_value = {"active": []}
    assert facade.get_torrents_overview() == {"active": []}
    service.stream_torrents.return_value = iter([{"name": "t"}])
    assert list(facade.stream_torrents(["a"], profile="p", limit=10)) == [{"name": "t"}]
    service.stream_torrents.assert_called_once_with(["a"], profile="p", limit=10)


def test_get_anime_torrents_and_episode_files(facade, service):
    service.get_anime_torrents.return_value = [{"hash": "h"}]
    assert facade.get_anime_torrents(4) == [{"hash": "h"}]
    service.list_episode_files.return_value = [{"file_id": "ep-1"}]
    assert facade.list_episode_files(4, user_id=7) == [{"file_id": "ep-1"}]
    service.list_episode_files.assert_called_once_with(4, user_id=7)


def test_episode_progress_and_deletes(facade, service):
    facade.set_episode_progress(1, 2, "ep-1", "seen", position_seconds=12.5)
    service.set_episode_progress.assert_called_once_with(
        1, 2, "ep-1", "seen", position_seconds=12.5
    )
    service.delete_episode_file.return_value = True
    assert facade.delete_episode_file(1, "ep-1", 2) is True
    service.redownload_episode.return_value = True
    assert facade.redownload_episode(1, "ep-1", 2) is True
    service.redownload_episode.assert_called_once_with(1, "ep-1", 2)
    service.delete_all_files.return_value = 3
    assert facade.delete_all_files(1, 2) == 3
    service.delete_seen_episodes.return_value = 1
    assert facade.delete_seen_episodes(1, 2) == 1


def test_playback_session_methods(facade, service):
    session = {"session_id": "s1"}
    service.create_playback_session.return_value = session
    out = facade.create_playback_session(
        1,
        "ep-1",
        client_host="127.0.0.1",
        ttl_seconds=60,
        audio_track=0,
        subtitle_track=1,
        start_time_seconds=5.0,
    )
    assert out is session
    service.create_playback_session.assert_called_once_with(
        anime_id=1,
        file_id="ep-1",
        client_host="127.0.0.1",
        ttl_seconds=60,
        audio_track=0,
        subtitle_track=1,
        start_time_seconds=5.0,
    )
    service.heartbeat_playback_session.return_value = {"ok": True}
    assert facade.heartbeat_playback_session("s1") == {"ok": True}
    facade.stop_playback_session("s1")
    service.stop_playback_session.assert_called_once_with("s1")
    service.resolve_playback_media_path.return_value = "/tmp/seg.ts"
    assert (
        facade.resolve_playback_media_path(
            session_id="s1", token="tok", segment_name="seg.ts"
        )
        == "/tmp/seg.ts"
    )
    service.resolve_playback_media_path.assert_called_once_with(
        session_id="s1", token="tok", segment_name="seg.ts"
    )
