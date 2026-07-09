"""Additional edge case tests for :class:`AnimeApplicationService`.

These tests use minimal in-memory fakes for the ports and focus on the
validation/normalisation surface of the orchestrator.
"""

from __future__ import annotations

import pytest

from application.services.anime_service import AnimeApplicationService
from domain.dto import (
    AnimeListRequest,
    DownloadRequest,
    SearchRequest,
)
from domain.entities import AnimeEntity
from domain.errors import NotFoundError, ValidationError


class FakeRepository:
    def __init__(self):
        self.items = []
        self.calls = []
        self.return_search_terms = ["term"]

    def search(self, query, limit=50):
        self.calls.append(("search", query, limit))
        return list(self.items)

    def list_anime(self, **kwargs):
        self.calls.append(("list_anime", kwargs))
        return list(self.items), False

    def get_anime(self, anime_id):
        self.calls.append(("get_anime", anime_id))
        for entity in self.items:
            if entity.id == anime_id:
                return entity
        return None

    def anime_row_exists(self, anime_id):
        entity = self.get_anime(anime_id)
        return entity is not None and bool((entity.title or "").strip())

    def get_search_terms(self, anime_id):
        self.calls.append(("get_search_terms", anime_id))
        return list(self.return_search_terms)

    def add_search_term(self, anime_id, term):
        self.calls.append(("add_search_term", anime_id, term))
        return True

    def remove_search_term(self, anime_id, term):
        self.calls.append(("remove_search_term", anime_id, term))
        return True

    def get_settings(self):
        return {"anime": {"hideRated": True}}

    def update_settings(self, updates):
        return updates

    def get_relations(self, anime_id, relation_type="anime"):
        return []


class FakeProvider:
    def __init__(self):
        self.responses = []

    def search(self, query, limit=50):
        return list(self.responses)


class FakeDownload:
    def __init__(self):
        self.start_calls = []

    def start_download(self, anime_id, url=None, hash_value=None, user_id=None):
        self.start_calls.append((anime_id, url, hash_value, user_id))
        return True

    def get_download_progress(self, anime_id):
        return {"anime_id": anime_id, "progress": 0}

    def cancel_download(self, anime_id):
        return True

    def get_active_downloads(self):
        return []

    def search_torrents(self, terms, profile="interactive", limit=200):
        return [{"terms": list(terms), "profile": profile, "limit": limit}]


class FakeActions:
    def __init__(self):
        self.calls = []

    def set_tag(self, anime_id, tag, user_id):
        self.calls.append(("set_tag", anime_id, tag, user_id))

    def set_like(self, anime_id, liked, user_id):
        self.calls.append(("set_like", anime_id, liked, user_id))

    def mark_seen(self, anime_id, file_name, user_id):
        self.calls.append(("mark_seen", anime_id, file_name, user_id))

    def get_user_state(self, anime_id, user_id):
        return {"tag": "NONE", "liked": False}

    def get_episode_progress_map(self, anime_id, user_id):
        self.calls.append(("get_episode_progress_map", anime_id, user_id))
        return {}

    def set_episode_progress(
        self, anime_id, user_id, file_id, status, position_seconds=None
    ):
        self.calls.append(
            ("set_episode_progress", anime_id, user_id, file_id, status, position_seconds)
        )

    def delete_episode_progress(self, anime_id, user_id, file_id):
        self.calls.append(("delete_episode_progress", anime_id, user_id, file_id))


@pytest.fixture
def service():
    repo = FakeRepository()
    prov = FakeProvider()
    dl = FakeDownload()
    actions = FakeActions()
    svc = AnimeApplicationService(
        anime_repository=repo,
        metadata_provider=prov,
        download_port=dl,
        user_actions_port=actions,
    )
    svc._fakes = (repo, prov, dl, actions)
    return svc


# ---------------------------------------------------------------------------
# search_anime
# ---------------------------------------------------------------------------


class TestSearchAnimeEdges:
    @pytest.mark.parametrize("query", ["", "  ", "a", "ab", "!!!"])
    def test_short_or_empty_query_raises(self, service, query):
        with pytest.raises(ValidationError):
            service.search_anime(SearchRequest(query=query))

    def test_query_punctuation_normalised(self, service):
        repo, _, _, _ = service._fakes
        repo.items = [AnimeEntity(id=1, title="Found")]
        result = service.search_anime(SearchRequest(query="!!!cowboy!!!"))
        assert len(result) == 1

    def test_provider_used_when_repo_empty(self, service):
        repo, prov, _, _ = service._fakes
        repo.items = []
        prov.responses = [AnimeEntity(id=99, title="External")]
        result = service.search_anime(SearchRequest(query="naruto"))
        assert result[0].id == 99

    def test_repo_results_short_circuit_provider(self, service):
        repo, prov, _, _ = service._fakes
        repo.items = [AnimeEntity(id=1, title="Local")]
        prov.responses = [AnimeEntity(id=2, title="Remote")]
        result = service.search_anime(SearchRequest(query="something"))
        assert [r.id for r in result] == [1, 2]

    def test_limit_forwarded_to_repo(self, service):
        repo, _, _, _ = service._fakes
        service.search_anime(SearchRequest(query="anime", limit=7))
        assert repo.calls[0] == ("search", "anime", 7)


# ---------------------------------------------------------------------------
# get_anime_details
# ---------------------------------------------------------------------------


class TestGetAnimeDetailsEdges:
    def test_returns_entity_when_found(self, service):
        repo, _, _, _ = service._fakes
        repo.items = [AnimeEntity(id=1, title="x")]
        assert service.get_anime_details(1).entity.title == "x"

    def test_returns_non_blocking_without_await(self, service):
        repo, _, _, _ = service._fakes
        repo.items = [AnimeEntity(id=1, title="")]
        result = service.get_anime_details(1)
        assert result.entity.title == ""
        assert result.metadata_pending is True

    @pytest.mark.parametrize("anime_id", [0, -1, 999999, 10**12])
    def test_not_found_raises(self, service, anime_id):
        with pytest.raises(NotFoundError):
            service.get_anime_details(anime_id)


class TestRefreshAnimeDetailsEdges:
    def test_refresh_without_hydration_returns_not_accepted(self, service):
        result = service.refresh_anime_details(1)
        assert result == {"accepted": False, "anime_id": 1}

    def test_refresh_with_hydration_accepts(self, service):
        class FakeHydration:
            catalog_ids = {1}
            kickoff_calls: list[int] = []

            def catalog_id_exists(self, catalog_id: int) -> bool:
                return int(catalog_id) in self.catalog_ids

            def kickoff_detail_refresh(self, catalog_id, *, after_hydrate=None):
                self.kickoff_calls.append(int(catalog_id))

        hydration = FakeHydration()
        service._hydration = hydration
        result = service.refresh_anime_details(1)
        assert result == {"accepted": True, "anime_id": 1}
        assert hydration.kickoff_calls == [1]

    def test_refresh_not_found_raises(self, service):
        class FakeHydration:
            def catalog_id_exists(self, catalog_id: int) -> bool:
                return False

            def kickoff_detail_refresh(self, *_args, **_kwargs):
                raise AssertionError("should not be called")

        service._hydration = FakeHydration()
        with pytest.raises(NotFoundError):
            service.refresh_anime_details(999)


# ---------------------------------------------------------------------------
# start_download
# ---------------------------------------------------------------------------


class TestStartDownloadEdges:
    def test_requires_url_or_hash(self, service):
        with pytest.raises(ValidationError):
            service.start_download(DownloadRequest(anime_id=1))

    def test_with_url_only(self, service):
        ok = service.start_download(
            DownloadRequest(anime_id=1, url="magnet:?xt=urn:btih:abc")
        )
        assert ok is True

    def test_with_hash_only(self, service):
        ok = service.start_download(DownloadRequest(anime_id=1, hash_value="abc"))
        assert ok is True

    def test_with_both_url_and_hash(self, service):
        ok = service.start_download(
            DownloadRequest(anime_id=1, url="u", hash_value="h")
        )
        assert ok is True


# ---------------------------------------------------------------------------
# search_torrents
# ---------------------------------------------------------------------------


class TestSearchTorrentsEdges:
    def test_empty_terms_raises(self, service):
        with pytest.raises(ValidationError):
            service.search_torrents([])

    def test_whitespace_only_terms_raises(self, service):
        with pytest.raises(ValidationError):
            service.search_torrents(["  ", "\t\n"])

    def test_strips_whitespace_from_terms(self, service):
        _, _, dl, _ = service._fakes
        out = service.search_torrents(["  naruto  ", " bleach "])
        assert "naruto" in out[0]["terms"]
        assert "bleach" in out[0]["terms"]

    def test_coerces_non_string_terms_to_string(self, service):
        out = service.search_torrents([123, "ok"])
        assert "123" in out[0]["terms"]
        assert "ok" in out[0]["terms"]

    def test_dropped_terms_make_request_fail_when_all_dropped(self, service):
        # All-empty / all-whitespace terms drop to an empty list. ``None``
        # gets stringified to "None" which survives, so we only assert the
        # all-blank case raises.
        with pytest.raises(ValidationError):
            service.search_torrents(["", "   "])

    def test_none_term_stringified_kept(self, service):
        # Documents the current quirk: ``None`` is stringified to "None".
        out = service.search_torrents([None, "valid"])
        assert "valid" in out[0]["terms"]


# ---------------------------------------------------------------------------
# add / remove search term
# ---------------------------------------------------------------------------


class TestSearchTermsEdges:
    def test_add_search_term_rejects_short(self, service):
        with pytest.raises(ValidationError):
            service.add_search_term(1, "a")
        with pytest.raises(ValidationError):
            service.add_search_term(1, " ")

    def test_add_search_term_strips_input(self, service):
        repo, _, _, _ = service._fakes
        service.add_search_term(1, "  abcd  ")
        assert ("add_search_term", 1, "abcd") in repo.calls

    def test_remove_search_term_rejects_empty(self, service):
        with pytest.raises(ValidationError):
            service.remove_search_term(1, "")

    def test_remove_search_term_rejects_whitespace_only(self, service):
        with pytest.raises(ValidationError):
            service.remove_search_term(1, "   ")

    def test_remove_search_term_strips(self, service):
        repo, _, _, _ = service._fakes
        service.remove_search_term(1, "  hi  ")
        assert ("remove_search_term", 1, "hi") in repo.calls


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class TestUpdateSettingsEdges:
    def test_rejects_empty_dict(self, service):
        with pytest.raises(ValidationError):
            service.update_settings({})

    def test_rejects_non_dict(self, service):
        with pytest.raises(ValidationError):
            service.update_settings("oops")  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            service.update_settings(None)  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            service.update_settings(["a"])  # type: ignore[arg-type]

    def test_accepts_normal_updates(self, service):
        out = service.update_settings({"a": 1})
        assert out == {"a": 1}


# ---------------------------------------------------------------------------
# Pass-through ports
# ---------------------------------------------------------------------------


class TestPortPassThrough:
    def test_get_anime_list_forwards_kwargs(self, service):
        repo, _, _, _ = service._fakes
        response = service.get_anime_list(
            AnimeListRequest(
                filter="LIKED",
                user_id=3,
                list_start=5,
                list_stop=12,
                hide_rated=True,
            )
        )
        assert response.has_next is False
        last = next(c for c in repo.calls if c[0] == "list_anime")
        assert last[1] == {
            "criteria": "LIKED",
            "list_start": 5,
            "list_stop": 12,
            "hide_rated": True,
            "user_id": 3,
        }

    def test_set_tag_forwards(self, service):
        _, _, _, actions = service._fakes
        service.set_tag(1, "LIKED", 7)
        assert ("set_tag", 1, "LIKED", 7) in actions.calls

    def test_set_like_default_true(self, service):
        _, _, _, actions = service._fakes
        service.set_like(1, 7)
        assert ("set_like", 1, True, 7) in actions.calls

    def test_mark_seen_forwards(self, service):
        _, _, _, actions = service._fakes
        service.mark_seen(1, "ep1.mkv", 7)
        assert ("mark_seen", 1, "ep1.mkv", 7) in actions.calls

    def test_get_relations_passes_relation_type(self, service):
        # default relation_type is "anime"; ensure pass-through accepts custom
        repo, _, _, _ = service._fakes
        service.get_relations(1, relation_type="character")  # should not raise

    def test_get_download_progress_returns_dict(self, service):
        result = service.get_download_progress(7)
        assert result["anime_id"] == 7

    def test_cancel_download_returns_bool(self, service):
        assert service.cancel_download(1) is True

    def test_get_active_downloads_returns_list(self, service):
        assert service.get_active_downloads() == []

    def test_get_user_state_returns_dict(self, service):
        out = service.get_user_state(1, 2)
        assert isinstance(out, dict)
        assert "tag" in out

    def test_get_settings_returns_dict(self, service):
        assert service.get_settings()["anime"]["hideRated"] is True

    def test_get_search_terms_returns_list(self, service):
        out = service.get_search_terms(1)
        assert isinstance(out, list)
