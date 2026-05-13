"""Edge case tests for ``domain.dto``.

Confirms shape, slot constraints, and defaults of the request/response DTOs.
"""

from __future__ import annotations

import pytest

from domain.dto import (
    AnimeListRequest,
    AnimeListResponse,
    DownloadRequest,
    SearchRequest,
)
from domain.entities import AnimeEntity


class TestAnimeListRequestDefaults:
    def test_defaults(self):
        req = AnimeListRequest()
        assert req.filter == "DEFAULT"
        assert req.user_id is None
        assert req.list_start == 0
        assert req.list_stop == 50
        assert req.hide_rated is None

    def test_slots_enforced(self):
        req = AnimeListRequest()
        with pytest.raises(AttributeError):
            req.unknown_field = 1  # type: ignore[attr-defined]

    def test_accepts_named_overrides(self):
        req = AnimeListRequest(
            filter="LIKED",
            user_id=12,
            list_start=10,
            list_stop=20,
            hide_rated=False,
        )
        assert req.filter == "LIKED"
        assert req.user_id == 12
        assert req.hide_rated is False


class TestSearchRequestDefaults:
    def test_query_required(self):
        with pytest.raises(TypeError):
            SearchRequest()  # type: ignore[call-arg]

    def test_default_limit(self):
        assert SearchRequest(query="x").limit == 50

    def test_slots_enforced(self):
        req = SearchRequest(query="x")
        with pytest.raises(AttributeError):
            req.foo = 1  # type: ignore[attr-defined]


class TestDownloadRequestDefaults:
    def test_anime_id_required(self):
        with pytest.raises(TypeError):
            DownloadRequest()  # type: ignore[call-arg]

    def test_defaults(self):
        req = DownloadRequest(anime_id=1)
        assert req.url is None
        assert req.hash_value is None
        assert req.user_id is None


class TestAnimeListResponseDefaults:
    def test_defaults(self):
        resp = AnimeListResponse()
        assert resp.items == []
        assert resp.has_next is False

    def test_default_list_is_per_instance(self):
        a = AnimeListResponse()
        b = AnimeListResponse()
        a.items.append(AnimeEntity(id=1, title="t"))
        assert b.items == []
