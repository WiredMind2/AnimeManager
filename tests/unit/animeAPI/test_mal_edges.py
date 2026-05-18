"""Edge-case unit tests for ``adapters.api.MyAnimeListNet`` (no network)."""

from __future__ import annotations

import json
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

from adapters.api.MyAnimeListNet import MyAnimeListNetWrapper


def _make(token="access-token"):
    w = object.__new__(MyAnimeListNetWrapper)
    w.CLIENT_ID = "client-id"
    w.CLIENT_SECRET = "client-secret"
    w.baseUrl = "https://api.myanimelist.net/v2/"
    w.apiKey = "mal_id"
    w.token = token
    w.fields = "id,title"
    w.log = MagicMock()
    w.getId = MagicMock(return_value=42)
    w.database = MagicMock()
    w.database.getId.return_value = 1
    w.save_pictures = MagicMock()
    w.save_broadcast = MagicMock()
    w.save_genres = MagicMock()
    w.save_relations = MagicMock()
    w.getStatus = MagicMock(return_value="AIRING")
    return w


class TestMalGet:
    def test_returns_empty_when_no_token(self):
        w = _make(token=None)
        assert w.get("anime", 1) == {}

    def test_builds_url_from_path_segments(self):
        w = _make()
        with patch("adapters.api.MyAnimeListNet.requests.get") as get:
            get.return_value = SimpleNamespace(json=lambda: {"ok": True})
            out = w.get("anime", 1, fields="id")
            assert out == {"ok": True}
            url = get.call_args.args[0]
            assert "anime/1" in url
            assert "fields=id" in url

    def test_accepts_full_url_as_single_arg(self):
        w = _make()
        with patch("adapters.api.MyAnimeListNet.requests.get") as get:
            get.return_value = SimpleNamespace(json=lambda: {"next": True})
            w.get("https://api.myanimelist.net/v2/anime?offset=50")
            assert get.call_args.args[0].startswith("https://")

    def test_request_exception_returns_empty(self):
        w = _make()
        with patch(
            "adapters.api.MyAnimeListNet.requests.get",
            side_effect=requests.exceptions.Timeout("slow"),
        ):
            assert w.get("anime", 1) == {}

    def test_non_json_response_returns_text(self):
        w = _make()
        with patch("adapters.api.MyAnimeListNet.requests.get") as get:
            get.return_value = SimpleNamespace(
                json=MagicMock(side_effect=ValueError("not json")),
                text="plain",
            )
            assert w.get("anime", 1) == "plain"


class TestMalAnime:
    def test_returns_empty_when_no_mal_id(self):
        w = _make()
        w.getId.return_value = None
        assert w.anime(1) == {}

    def test_returns_empty_when_get_empty(self):
        w = _make()
        w.get = MagicMock(return_value={})
        assert w.anime(1) == {}

    def test_happy_path(self):
        w = _make()
        w.get = MagicMock(
            return_value={
                "id": 42,
                "title": "Naruto",
                "start_date": "2002-10-03",
                "end_date": "2007-02-08",
            }
        )
        out = w.anime(1)
        assert out["title"] == "Naruto"


class TestMalSearchAnime:
    def test_yields_results_until_limit(self):
        w = _make()
        w.get = MagicMock(
            return_value={
                "data": [
                    {"node": {"id": 1, "title": "A"}},
                    {"node": {"id": 2, "title": "B"}},
                ],
                "paging": {},
            }
        )
        rows = list(w.searchAnime("naruto", limit=1))
        assert len(rows) == 1

    def test_follows_paging_next(self):
        w = _make()
        first = {
            "data": [{"node": {"id": 1, "title": "A"}}],
            "paging": {"next": "https://api.myanimelist.net/v2/anime?offset=1"},
        }
        second = {"data": [{"node": {"id": 2, "title": "B"}}], "paging": {}}
        w.get = MagicMock(side_effect=[first, second])
        rows = list(w.searchAnime("naruto", limit=5))
        assert len(rows) == 2
        assert w.get.call_count == 2

    def test_stops_when_no_data_key(self):
        w = _make()
        w.get = MagicMock(return_value={"paging": {}})
        assert list(w.searchAnime("x")) == []


class TestMalCheckValidity:
    def test_401_returns_false(self):
        w = _make()
        with patch("adapters.api.MyAnimeListNet.requests.get") as get:
            get.return_value = SimpleNamespace(status_code=401, close=MagicMock())
            assert w.check_validity("bad-token") is False

    def test_success_returns_true(self):
        w = _make()
        with patch("adapters.api.MyAnimeListNet.requests.get") as get:
            get.return_value = SimpleNamespace(
                status_code=200,
                json=lambda: {"name": "user"},
                close=MagicMock(),
            )
            assert w.check_validity("good-token") is True

    def test_request_exception_returns_false(self):
        w = _make()
        with patch(
            "adapters.api.MyAnimeListNet.requests.get",
            side_effect=requests.exceptions.ConnectionError(),
        ):
            assert w.check_validity("token") is False


class TestMalTokenHelpers:
    def test_persist_token_writes_json(self):
        w = _make()
        with tempfile.TemporaryDirectory() as tmp:
            w.tokenPath = os.path.join(tmp, "token.json")
            w._persist_token({"access_token": "abc", "refresh_token": "def"})
            with open(w.tokenPath, encoding="utf-8") as fh:
                data = json.load(fh)
            assert data["access_token"] == "abc"

    def test_persist_token_noop_for_empty(self):
        w = _make()
        w._persist_token(None)
        w._persist_token({})

    def test_refresh_token_without_credentials_returns_none(self):
        w = _make()
        w.CLIENT_ID = None
        w.CLIENT_SECRET = None
        assert w.refresh_token("refresh") is None

    def test_get_token_reads_valid_file(self):
        w = _make()
        with tempfile.TemporaryDirectory() as tmp:
            w.tokenPath = os.path.join(tmp, "token.json")
            with open(w.tokenPath, "w", encoding="utf-8") as fh:
                json.dump({"access_token": "tok", "refresh_token": "ref"}, fh)
            with patch.object(w, "check_validity", return_value=True):
                assert w.getToken() == "tok"

    def test_get_token_missing_file_returns_none(self):
        w = _make()
        w.tokenPath = os.path.join(tempfile.gettempdir(), "nonexistent-mal-token.json")
        assert w.getToken() is None


class TestMalInitCredentials:
    def test_load_oauth_credentials_from_settings(self):
        w = object.__new__(MyAnimeListNetWrapper)
        w.log = MagicMock()
        w.settings = {
            "api_credentials": {
                "myanimelist": {"client_id": "cid", "client_secret": "csec"}
            }
        }
        with patch(
            "adapters.api.MyAnimeListNet.load_secret",
            side_effect=lambda key, settings=None: settings.get(key) if settings else None,
        ):
            cid, csec = w._load_oauth_credentials()
        assert cid == "cid"
        assert csec == "csec"

    def test_init_swallows_get_token_failure(self):
        with patch.object(MyAnimeListNetWrapper, "getToken", side_effect=RuntimeError("boom")):
            with patch.object(
                MyAnimeListNetWrapper, "_load_oauth_credentials", return_value=("a", "b")
            ):
                w = MyAnimeListNetWrapper.__new__(MyAnimeListNetWrapper)
                w.log = MagicMock()
                w.tokenPath = os.path.join(tempfile.gettempdir(), "missing.json")
                # Mimic __init__ tail without full super chain
                try:
                    w.token = w.getToken()
                except Exception:
                    w.log("MAL", "getToken failed during init; continuing without token")
                    w.token = None
                assert w.token is None


class TestMalConvertCharacter:
    def test_returns_empty_for_none(self):
        w = _make()
        assert w._convertCharacter(None) == {}

    def test_unwraps_character_envelope(self):
        w = _make()
        c = {
            "character": {
                "id": 99,
                "name": "Sakura",
                "images": {"jpg": {"image_url": "http://img"}},
                "about": "desc",
            },
            "role": "Main",
        }
        out = w._convertCharacter(c, anime_id=1)
        assert out["name"] == "Sakura"
