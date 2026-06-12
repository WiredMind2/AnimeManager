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


def test_get_disabled_search_titles_forwards(facade, service):
    service.get_disabled_search_titles.return_value = ["a"]
    assert facade.get_disabled_search_titles(1) == ["a"]


def test_disable_search_title_forwards(facade, service):
    service.disable_search_title.return_value = True
    assert facade.disable_search_title(1, "t") is True


def test_enable_search_title_forwards(facade, service):
    service.enable_search_title.return_value = True
    assert facade.enable_search_title(1, "t") is True


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


def test_service_errors_propagate(facade, service):
    service.get_anime_details.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        facade.get_anime_details(1)
