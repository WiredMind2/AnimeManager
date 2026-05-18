"""Unit tests for pure helpers in :mod:`clients.http.web`."""

from __future__ import annotations

import importlib
import time
import types
from unittest.mock import MagicMock

import pytest

from domain.errors import NotFoundError, UnauthorizedError, ValidationError

http_web = importlib.import_module("clients.http.web")


@pytest.fixture(autouse=True)
def _reset_metadata_refresh_cache():
    yield
    http_web._METADATA_REFRESH_TS.clear()


class TestSafeIntAndDates:
    def test_safe_int_defaults_on_bad_input(self):
        assert http_web._safe_int("nope", 3) == 3
        assert http_web._safe_int("12", 0) == 12

    def test_format_unix_date(self):
        assert http_web._format_unix_date(0) is None
        assert http_web._format_unix_date(1_600_000_000) == "2020-09-13"

    def test_string_list_dedupes_case_insensitive(self):
        assert http_web._string_list(["Foo", "foo", "bar"]) == ["Foo", "bar"]


class TestHumanizeHelpers:
    def test_humanize_size(self):
        assert http_web._humanize_size(0) is None
        assert http_web._humanize_size(1536) == "1.5 KB"

    def test_format_speed_and_eta(self):
        assert http_web._format_speed(0) is None
        assert http_web._format_speed(2048) == "2.0 KB/s"
        assert http_web._format_eta(45) == "45s"
        assert http_web._format_eta(3661) == "1h 1m"


class TestMapError:
    def test_validation_not_found_unauthorized(self):
        assert http_web._map_error(ValidationError("bad")) == (400, "bad")
        assert http_web._map_error(NotFoundError("missing")) == (404, "missing")
        assert http_web._map_error(UnauthorizedError("nope")) == (401, "nope")

    def test_unknown_error_message(self):
        code, msg = http_web._map_error(RuntimeError("boom"))
        assert code == 500
        assert msg == "Unexpected error"


class TestSseAndTorrentNormalization:
    def test_sse_event_multiline_data(self):
        frame = http_web._sse_event("html", "line1\nline2").decode("utf-8")
        assert "event: html" in frame
        assert "data: line1" in frame
        assert "data: line2" in frame

    def test_normalize_torrents_adds_size_human(self):
        rows = http_web._normalize_torrents([{"name": "x", "size": 1024, "seeds": 1}])
        assert rows[0]["size_human"] == "1.0 KB"

    def test_normalize_overview_row_progress_fraction(self):
        row = http_web._normalize_overview_row(
            {"name": "t", "progress": 0.5, "dl_speed": 1024, "eta": 90}
        )
        assert row["progress_pct"] == 50.0
        assert row["dl_speed_human"] == "1.0 KB/s"
        assert row["eta_human"] == "1m 30s"


class TestStreamingClientAllowlist:
    def _request(self, *, host: str = "127.0.0.1", forwarded: str | None = None):
        headers: list[tuple[bytes, bytes]] = []
        if forwarded:
            headers.append((b"x-forwarded-for", forwarded.encode()))
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "client": (host, 0),
        }
        return http_web.Request(scope)

    def test_client_host_prefers_forwarded(self):
        req = self._request(host="10.0.0.1", forwarded="203.0.113.5, 10.0.0.1")
        assert http_web._client_host(req) == "203.0.113.5"

    def test_host_in_allowlist_cidr(self):
        assert http_web._host_in_allowlist("192.168.1.10", ["192.168.0.0/16"])

    def test_loopback_always_allowed(self):
        sdk = MagicMock()
        sdk.get_settings.return_value = {"web": {"player_allow_public": False}}
        req = self._request(host="127.0.0.1")
        assert http_web._is_client_allowed_for_streaming(req, sdk) is True

    def test_public_flag_allows_remote(self):
        sdk = MagicMock()
        sdk.get_settings.return_value = {"web": {"player_allow_public": True}}
        req = self._request(host="203.0.113.9")
        assert http_web._is_client_allowed_for_streaming(req, sdk) is True


class TestCollectAnimeTorrents:
    def test_merges_saved_and_active_by_hash(self):
        sdk = MagicMock()
        sdk.get_anime_torrents.return_value = [
            {"hash": "abc", "name": "saved", "size": 100, "downloaded": 0}
        ]
        sdk.get_active_downloads.return_value = [
            {
                "anime_id": 7,
                "hash": "abc",
                "name": "active",
                "size": 100,
                "downloaded": 50,
                "progress": 0.5,
            },
            {"anime_id": 99, "hash": "other", "name": "skip"},
        ]
        rows = http_web._collect_anime_torrents(sdk, 7)
        assert len(rows) == 1
        assert rows[0]["downloaded"] == 50
        assert rows[0]["state"] == "DOWNLOADING"


class TestMetadataRefreshThrottle:
    def test_maybe_refresh_skips_within_interval(self, monkeypatch):
        http_web._METADATA_REFRESH_TS.clear()
        sdk = MagicMock()
        http_web._maybe_refresh_anime_metadata(sdk, 42)
        http_web._maybe_refresh_anime_metadata(sdk, 42)
        assert sdk.refresh_anime_metadata.call_count == 1

    def test_maybe_refresh_calls_after_interval(self, monkeypatch):
        http_web._METADATA_REFRESH_TS.clear()
        sdk = MagicMock()
        monkeypatch.setattr(http_web, "_METADATA_REFRESH_INTERVAL_S", 0.0)
        http_web._maybe_refresh_anime_metadata(sdk, 1)
        time.sleep(0.01)
        http_web._maybe_refresh_anime_metadata(sdk, 1)
        assert sdk.refresh_anime_metadata.call_count == 2


class TestAnimeInfoRows:
    def test_builds_tags_and_date_rows(self):
        anime = {
            "title": "Bleach",
            "title_synonyms": ["bleach", "BLEACH"],
            "genres": ["Action"],
            "date_from": 1_600_000_000,
            "date_to": 1_700_000_000,
        }
        tags, alts, rows = http_web._anime_info_rows(
            anime, user_state={}, terms=["1080p"]
        )
        assert tags == ["Action"]
        assert alts == []
        labels = [label for label, _ in rows]
        assert "Start date" in labels
        assert "Saved search terms" in labels


class TestResolveGenreTags:
    def test_resolves_numeric_ids_via_database(self, monkeypatch):
        db = MagicMock()
        db._fetch_genre_metadata_for_id.return_value = ["Romance", "Comedy"]
        monkeypatch.setattr(http_web.Getters, "getDatabase", lambda _self=None: db)

        assert http_web._resolve_genre_tags(10, ["5", "2"]) == ["Romance", "Comedy"]

    def test_falls_back_to_genres_index_lookup(self, monkeypatch):
        db = MagicMock()
        db._fetch_genre_metadata_for_id.return_value = []
        db.sql.return_value = [(5, "Romance"), (2, "Comedy")]
        monkeypatch.setattr(http_web.Getters, "getDatabase", lambda _self=None: db)

        assert http_web._resolve_genre_tags(10, ["5", "2"]) == ["Romance", "Comedy"]

    def test_unknown_numeric_genre_uses_fallback(self, monkeypatch):
        db = MagicMock()
        db._fetch_genre_metadata_for_id.return_value = []
        db.sql.return_value = []
        monkeypatch.setattr(http_web.Getters, "getDatabase", lambda _self=None: db)

        assert http_web._resolve_genre_tags(10, ["99"]) == [http_web._UNKNOWN_GENRE]


class TestBuildAnimeDetailView:
    def test_groups_airing_and_metadata_fields(self):
        anime = {
            "id": 7,
            "title": "Sample",
            "genres": ["Action"],
            "date_from": 1_600_000_000,
            "broadcast": "Tue 09:30",
            "last_seen": "Episode 3",
        }
        view = http_web._build_anime_detail_view(
            anime,
            anime_id=7,
            terms=["1080p"],
            computed_status_text="Airing",
            schedule_lines=[
                "Since 07 Apr 2026 (41 days)",
                "Next episode on Tue 19 at 09:30",
                "Latest episode: 6 days ago",
            ],
        )

        airing_labels = [field["label"] for field in view["airing_fields"]]
        assert airing_labels[0] == "Status"
        assert "Airs" in airing_labels
        assert "Next episode" in airing_labels
        assert "Latest episode" in airing_labels

        airs = next(f for f in view["airing_fields"] if f["label"] == "Airs")
        assert airs["value"] == "07 Apr 2026"
        assert airs["hint"] == "41 days"

        meta_labels = [field["label"] for field in view["metadata_fields"]]
        assert "Start date" in meta_labels
        assert "Broadcast" in meta_labels
        assert "Saved search terms" in meta_labels
        assert view["genre_tags"] == ["Action"]

    def test_parse_schedule_line_labels(self):
        row = http_web._parse_schedule_line("Next episode on Tue 19 at 09:30")
        assert row["label"] == "Next episode"
        assert "Tue 19" in row["value"]
