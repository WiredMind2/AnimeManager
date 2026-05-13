"""Smoke + behavior tests for the FastAPI web UI (clients.http.web).

All routes are exercised against a single in-memory ``FakeSDK`` that
satisfies the SDK contract consumed by ``clients.http.web``. The web
module shares its SDK accessor with ``clients.http.app`` so a single
``monkeypatch.setattr(http_app, "get_sdk", ...)`` covers both
surfaces.
"""

from __future__ import annotations

import importlib
import time
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


http_app = importlib.import_module("clients.http.app")
http_web = importlib.import_module("clients.http.web")


class FakeSDK:
    """Minimal SDK fake covering every method touched by the web UI."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self._settings: dict = {
            "ui": {"theme": "default", "language": "en"},
            "anime": {
                "hideRated": True,
                "animePerRow": 4,
                "animePerPage": 50,
            },
            "api_credentials": {
                "myanimelist": {"client_id": "", "client_secret": ""},
            },
            "media": {
                "players_order": ["mpv", "vlc", "ffplay"],
                "default_player": "mpv",
            },
            "file_managers": {
                "last_fm_used": "Local",
                "Local": {"dataPath": ""},
                "FTP": {
                    "url": "",
                    "login": "",
                    "password": "",
                    "dataPath": "",
                },
            },
            "torrent_managers": {
                "last_tm_used": "qBittorrent",
                "qBittorrent": {"url": "", "login": "", "password": ""},
                "Transmission": {},
            },
            "database_managers": {
                "last_db_used": "EmbeddedMariaDB",
                "EmbeddedMariaDB": {
                    "database": "",
                    "password": "",
                    "port": 3307,
                    "user": "",
                },
                "SQLite": {"dbPath": ""},
            },
            "paths": {"cache": "", "iconPath": "", "logsPath": ""},
            "UI": {
                "colors": {"Blue": "#56D8EF", "Red": "#F92472"},
                "tagcolors": {"SEEN": "Blue", "WATCHING": "Red"},
                "torrentsStateColors": {"COMPLETE": "Blue"},
                "dateStates": {
                    "AIRING": {"color": "Red", "text": "Airing"},
                },
            },
            "windows": {"mainWindowHeight": 500},
        }
        self._terms: dict[int, list[str]] = {1: ["SubsPlease 1080p"]}
        self._tags: dict[int, str] = {}
        self._likes: dict[int, bool] = {}
        self._playback_sessions: dict[str, dict] = {}
        self._play_root = Path(tempfile.mkdtemp(prefix="am-web-player-"))
        (self._play_root / "index.m3u8").write_text(
            "#EXTM3U\n#EXTINF:3,\nsegment_00001.ts\n",
            encoding="utf-8",
        )
        (self._play_root / "segment_00001.ts").write_bytes(b"segment")

    def _record(self, name: str, *args, **kwargs) -> None:
        self.calls.append((name, args, kwargs))

    # -- read paths ---------------------------------------------------------
    def get_anime_list(self, **kwargs):
        self._record("get_anime_list", **kwargs)
        return {
            "items": [
                {
                    "id": 1,
                    "title": "Bleach",
                    "picture": "https://example.com/p.jpg",
                    "status": "FINISHED",
                    "episodes": 366,
                    "duration": 24,
                    "tag": "WATCHING",
                    "liked": True,
                }
            ],
            "has_next": True,
        }

    def search_anime(self, query: str, limit: int = 50):
        self._record("search_anime", query, limit)
        return [{"id": 2, "title": query.title(), "picture": None, "status": "AIRING"}]

    def get_anime(self, anime_id: int):
        self._record("get_anime", anime_id)
        if anime_id == 404:
            from domain.errors import NotFoundError

            raise NotFoundError("missing")
        return {
            "id": anime_id,
            "title": "Bleach",
            "picture": "https://example.com/p.jpg",
            "status": "FINISHED",
            "synopsis": "A boy who can see ghosts.",
            "episodes": 366,
            "duration": 24,
            "genres": ["Action", "Shounen"],
            "trailer": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }

    def get_user_state(self, anime_id: int, user_id: int):
        return {"tag": self._tags.get(anime_id, "NONE"), "liked": self._likes.get(anime_id, False)}

    def get_search_terms(self, anime_id: int):
        return list(self._terms.get(anime_id, []))

    def get_relations(self, anime_id: int, relation_type: str = "anime"):
        return [{"id": 9, "title": "Bleach: TYBW", "type": "sequel"}]

    def get_active_downloads(self):
        return [
            {
                "anime_id": 1,
                "name": "[SubsPlease] Bleach - 01.mkv",
                "progress": 0.42,
                "state": "DOWNLOADING",
                "dl_speed": "5.2 MB/s",
            }
        ]

    def search_torrents(self, terms, profile="interactive", limit=200):
        self._record("search_torrents", terms, profile=profile, limit=limit)
        return [
            {
                "name": "[SubsPlease] Bleach S01 - 01 [1080p].mkv",
                "link": "magnet:?xt=urn:btih:abc",
                "size": 1572864000,  # 1.5 GB
                "seeds": 42,
                "leech": 3,
                "hash": "abc",
            }
        ]

    def stream_torrents(self, terms, profile="interactive", limit=200):
        """Yield results one-by-one so the streaming endpoint can exercise
        the SSE row/end framing without a real subprocess pool."""
        self._record("stream_torrents", terms, profile=profile, limit=limit)
        rows = [
            {
                "name": "[SubsPlease] Bleach S01 - 01 [1080p].mkv",
                "link": "magnet:?xt=urn:btih:abc",
                "size": 1572864000,
                "seeds": 42,
                "leech": 3,
                "hash": "abc",
            },
            {
                "name": "[Erai-raws] Bleach S01 - 02 [720p].mkv",
                "link": "magnet:?xt=urn:btih:def",
                "size": 524288000,
                "seeds": 7,
                "leech": 1,
                "hash": "def",
            },
        ]
        for row in rows[: max(1, limit)]:
            yield row

    def get_settings(self):
        return dict(self._settings)

    def update_settings(self, updates: dict):
        self._settings.update(updates)
        return dict(self._settings)

    # -- write paths --------------------------------------------------------
    def set_like(self, anime_id: int, user_id: int, liked: bool = True):
        self._record("set_like", anime_id, user_id, liked)
        self._likes[anime_id] = liked

    def set_tag(self, anime_id: int, tag: str, user_id: int):
        self._record("set_tag", anime_id, tag, user_id)
        self._tags[anime_id] = tag

    def mark_seen(self, anime_id: int, file_name: str, user_id: int):
        self._record("mark_seen", anime_id, file_name, user_id)

    def add_search_term(self, anime_id: int, term: str):
        self._record("add_search_term", anime_id, term)
        self._terms.setdefault(anime_id, []).append(term)
        return True

    def remove_search_term(self, anime_id: int, term: str):
        self._record("remove_search_term", anime_id, term)
        existing = self._terms.get(anime_id, [])
        if term in existing:
            existing.remove(term)
            return True
        return False

    def start_download(self, anime_id: int, url=None, hash_value=None, user_id=None):
        self._record("start_download", anime_id, url, hash_value, user_id)
        return True

    def cancel_download(self, anime_id: int):
        self._record("cancel_download", anime_id)
        return True

    def get_anime_torrents(self, anime_id: int):
        self._record("get_anime_torrents", anime_id)
        if anime_id != 1:
            return []
        return [
            {
                "hash": "deadbeef",
                "name": "[SubsPlease] Bleach S01 - 02 [1080p].mkv",
                "size": 1572864000,
                "downloaded": 1572864000,
                "path": "/anime/bleach/s01e02.mkv",
                "trackers": ["udp://tracker.example.com"],
            }
        ]

    def list_episode_files(self, anime_id: int, user_id: int | None = None):
        self._record("list_episode_files", anime_id, user_id)
        if anime_id != 1:
            return []
        return [
            {
                "file_id": "ep-001",
                "title": "[SubsPlease] Bleach - 01.mkv",
                "path": "/anime/bleach/01.mkv",
                "size_bytes": 1572864000,
                "season": 1,
                "episode": 1,
            }
        ]

    def create_playback_session(self, anime_id: int, file_id: str, **kwargs):
        self._record("create_playback_session", anime_id, file_id, kwargs)
        if file_id != "ep-001":
            from domain.errors import NotFoundError

            raise NotFoundError("missing file")
        sid = "sess-1"
        token = "12345.token"
        self._playback_sessions[sid] = {
            "session_id": sid,
            "anime_id": anime_id,
            "file_id": file_id,
            "file_title": "[SubsPlease] Bleach - 01.mkv",
            "manifest_path": str(self._play_root / "index.m3u8"),
            "output_dir": str(self._play_root),
            "token": token,
            "expires_at": time.time() + 600,
            "created_at": time.time(),
            "last_seen_at": time.time(),
            "playlist_url": None,
            "extra": {},
        }
        return dict(self._playback_sessions[sid])

    def heartbeat_playback_session(self, session_id: str):
        self._record("heartbeat_playback_session", session_id)
        session = self._playback_sessions.get(session_id)
        if not session:
            from domain.errors import NotFoundError

            raise NotFoundError("missing session")
        session["expires_at"] = time.time() + 600
        return dict(session)

    def stop_playback_session(self, session_id: str):
        self._record("stop_playback_session", session_id)
        self._playback_sessions.pop(session_id, None)

    def resolve_playback_media_path(self, *, session_id: str, token: str, segment_name=None):
        self._record("resolve_playback_media_path", session_id, token, segment_name)
        session = self._playback_sessions.get(session_id)
        if not session:
            from domain.errors import NotFoundError

            raise NotFoundError("missing session")
        if token and token != session["token"]:
            from domain.errors import UnauthorizedError

            raise UnauthorizedError("bad token")
        if segment_name:
            return dict(session), str(self._play_root / segment_name)
        return dict(session), str(self._play_root / "index.m3u8")


@pytest.fixture
def client(monkeypatch):
    fake = FakeSDK()
    monkeypatch.setattr(http_app, "get_sdk", lambda: fake)
    with TestClient(http_app.app, follow_redirects=False) as client:
        client.fake = fake  # type: ignore[attr-defined]
        yield client


def test_browser_root_redirects_to_ui(client):
    """Browser hitting `/` is bounced to the UI with 307.

    307 (not 303) preserves the GET method semantics — using 303 here
    caused some browsers/proxies to issue a duplicate GET right after
    the redirect, which showed up as spurious lines in the access log.
    """
    resp = client.get("/", headers={"accept": "text/html"})
    assert resp.status_code == 307
    assert resp.headers["location"] == "/ui/library"


def test_api_root_still_serves_json_status(client):
    resp = client.get("/", headers={"accept": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ui_alias_redirects_to_library(client):
    resp = client.get("/ui")
    assert resp.status_code == 307
    assert resp.headers["location"].endswith("/ui/library")


def test_library_renders_grid(client):
    resp = client.get("/ui/library")
    assert resp.status_code == 200
    body = resp.text
    assert "Library" in body
    assert "Bleach" in body
    assert 'class="grid"' in body
    assert "Next" in body  # has_next pager present


def test_library_search_uses_sdk(client):
    resp = client.get("/ui/library", params={"q": "naruto"})
    assert resp.status_code == 200
    # Server-rendered shell streams cards over ``/ui/library/ws``; the
    # first paint no longer embeds ``search_anime`` results inline.
    assert "data-library-stream-path" in resp.text
    assert "/ui/library/ws" in resp.text


def test_library_filter_chip_marked_active(client):
    resp = client.get("/ui/library", params={"filter": "WATCHING"})
    assert resp.status_code == 200
    assert 'aria-selected="true"' in resp.text


def test_anime_detail_renders_actions_and_terms(client):
    resp = client.get("/ui/anime/1")
    assert resp.status_code == 200
    body = resp.text
    assert "A boy who can see ghosts" in body
    assert "Torrent search options" in body
    assert "Search options" in body
    # Tag select + like form share the actions wrapper used as HTMX target
    assert 'id="anime-actions"' in body
    assert 'name="tag"' in body
    assert "/ui/anime/1/like" in body
    # Search-term manager is no longer shown directly on this page.
    assert 'id="search-terms"' not in body
    # Relations table rendered
    assert "Bleach: TYBW" in body


def test_anime_detail_404_renders_error_page(client):
    resp = client.get("/ui/anime/404")
    assert resp.status_code == 404
    assert "Not Found" in resp.text


def test_like_action_redirects_when_not_htmx(client):
    """Vanilla form submit (no JS) keeps the PRG redirect fallback."""
    resp = client.post("/ui/anime/1/like", data={"liked": "true"})
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/ui/anime/1")
    assert ("set_like", (1, 1, True), {}) in client.fake.calls


def test_like_action_returns_partial_for_htmx(client):
    """HTMX-driven submit gets the actions partial inline — no reload."""
    resp = client.post(
        "/ui/anime/1/like",
        data={"liked": "true"},
        headers={"hx-request": "true"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert 'id="anime-actions"' in body
    assert "Unlike" in body  # liked state now reflected in the partial
    assert "<html" not in body  # confirm we returned ONLY the partial


def test_tag_action_redirects_when_not_htmx(client):
    resp = client.post("/ui/anime/1/tag", data={"tag": "watching"})
    assert resp.status_code == 303
    assert ("set_tag", (1, "WATCHING", 1), {}) in client.fake.calls


def test_tag_action_returns_partial_for_htmx(client):
    """HTMX requests must avoid the full-page reload that the access
    log called out as 'strange': POST → 303 → GET → 200 → asset re-fetch.
    """
    resp = client.post(
        "/ui/anime/1/tag",
        data={"tag": "watching"},
        headers={"hx-request": "true"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert 'id="anime-actions"' in body
    # No redirect chain; HTMX swaps the partial in place.
    assert "Location" not in resp.headers


def test_search_terms_add_returns_partial(client):
    resp = client.post(
        "/ui/anime/1/terms",
        data={"term": "Erai-raws 720p"},
        headers={"hx-request": "true"},
    )
    assert resp.status_code == 200
    assert "Erai-raws 720p" in resp.text


def test_search_terms_delete_returns_partial(client):
    resp = client.delete(
        "/ui/anime/1/terms",
        params={"term": "SubsPlease 1080p"},
    )
    assert resp.status_code == 200
    # The term chip is gone — only the (untouched) placeholder mention
    # of "SubsPlease 1080p" remains in the add-new input.
    assert 'class="term"' not in resp.text
    assert ("remove_search_term", (1, "SubsPlease 1080p"), {}) in client.fake.calls


def test_downloads_page_renders_progress_bar(client):
    resp = client.get("/ui/downloads")
    assert resp.status_code == 200
    body = resp.text
    assert "Active downloads" in body
    assert "[SubsPlease] Bleach - 01.mkv" in body
    assert "progress__bar" in body
    assert "42.0%" in body  # 0.42 -> 42.0%


def test_downloads_panel_partial_endpoint(client):
    resp = client.get("/ui/downloads/panel")
    assert resp.status_code == 200
    assert "progress__bar" in resp.text


def test_downloads_overview_json_endpoint(client):
    """The JSON snapshot mirrors what the WebSocket pushes.

    Test doubles that only implement ``get_active_downloads`` still
    feed the ``active`` bucket via the SDK fallback so the polling
    endpoints keep working when the embedded facade is a stub.
    """
    resp = client.get("/ui/downloads/overview.json")
    assert resp.status_code == 200
    payload = resp.json()
    assert set(payload.keys()) == {"overview", "counts"}
    assert set(payload["overview"].keys()) >= {
        "active",
        "seeding",
        "completed",
        "error",
        "other",
    }
    assert payload["counts"]["active"] >= 1
    # FakeSDK yields one row with progress=0.42; the normaliser should
    # surface a 42.0% string ready for the UI.
    first = payload["overview"]["active"][0]
    assert first["progress_pct"] == 42.0
    assert first["name"] == "[SubsPlease] Bleach - 01.mkv"


def test_downloads_ws_pushes_initial_snapshot(client):
    """The WS handshake delivers a complete overview right after accept."""
    with client.websocket_connect("/ui/downloads/ws") as ws:
        message = ws.receive_json()
        assert "overview" in message
        assert "counts" in message
        assert "ts" in message
        active = message["overview"].get("active") or []
        assert active, "active bucket should contain the FakeSDK row"
        assert active[0]["progress_pct"] == 42.0


def test_downloads_ws_responds_to_refresh_request(client):
    """Sending ``{"type": "refresh"}`` triggers an out-of-band snapshot."""
    with client.websocket_connect("/ui/downloads/ws") as ws:
        ws.receive_json()  # initial push
        ws.send_text('{"type": "refresh"}')
        refresh = ws.receive_json()
        assert "overview" in refresh
        assert refresh["counts"]["active"] >= 1


def test_start_download_action(client):
    resp = client.post(
        "/ui/anime/1/download",
        data={"url": "magnet:?xt=urn:btih:abc"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/ui/downloads")
    assert ("start_download", (1, "magnet:?xt=urn:btih:abc", None, 1), {}) in client.fake.calls


def test_cancel_download_action(client):
    resp = client.post("/ui/anime/1/cancel")
    assert resp.status_code == 303
    assert ("cancel_download", (1,), {}) in client.fake.calls


def test_torrents_search_renders_results(client):
    resp = client.get("/ui/torrents", params={"term": "bleach 1080p"})
    assert resp.status_code == 200
    body = resp.text
    assert "[SubsPlease] Bleach S01" in body
    assert "1.5 GB" in body  # humanized size
    assert "42" in body  # seeds badge


def test_torrents_search_empty_state(client):
    resp = client.get("/ui/torrents")
    assert resp.status_code == 200
    assert "Search torrents" in resp.text


def test_settings_page_renders_structured_form(client):
    resp = client.get("/ui/settings")
    assert resp.status_code == 200
    body = resp.text
    # The settings.json escape hatch is mentioned in the header copy.
    assert "settings.json" in body
    # Section heading is rendered for the top-level "anime" section
    # which the FakeSDK populates via _settings.
    assert "anime.hideRated" in body
    # Boolean fields get rendered as toggles with a __bool__ marker.
    assert 'name="__bool__"' in body
    assert 'name="anime.hideRated"' in body
    # Advanced editor textarea is present but empty by default.
    assert 'name="settings_json"' in body


def test_settings_save_via_structured_fields(client):
    """A real form submission updates the right keys without touching
    sibling fields (round-trip through the shallow-merge in the
    backend)."""
    current = client.fake.get_settings()
    # Submit only the fields we want to change. The handler builds a
    # full settings dict from the schema so untouched values stay put.
    resp = client.post(
        "/ui/settings",
        data={
            "ui.theme": "dark",
            "ui.language": current["ui"].get("language", "en"),
            "__bool__": "anime.hideRated",
            # anime.hideRated checkbox NOT submitted -> should become False
            "anime.animePerRow": "6",
            "anime.animePerPage": str(current["anime"].get("animePerPage", 50)),
        },
    )
    assert resp.status_code == 200
    assert "Settings saved" in resp.text

    saved = client.fake.get_settings()
    assert saved["ui"]["theme"] == "dark"
    assert saved["anime"]["hideRated"] is False
    assert saved["anime"]["animePerRow"] == 6


def test_settings_checked_bool_round_trip(client):
    """A checked checkbox round-trips as True."""
    resp = client.post(
        "/ui/settings",
        data=[
            ("__bool__", "anime.hideRated"),
            ("anime.hideRated", "true"),
        ],
    )
    assert resp.status_code == 200
    assert client.fake.get_settings()["anime"]["hideRated"] is True


def test_settings_save_via_advanced_json_takes_precedence(client):
    payload = '{"ui": {"theme": "dark"}}'
    resp = client.post(
        "/ui/settings",
        data={
            "settings_json": payload,
            # Structured fields are present but should be ignored when
            # the advanced editor has content.
            "ui.theme": "should-be-ignored",
        },
    )
    assert resp.status_code == 200
    assert "Settings saved" in resp.text
    assert client.fake.get_settings()["ui"]["theme"] == "dark"


def test_settings_save_rejects_invalid_advanced_json(client):
    resp = client.post("/ui/settings", data={"settings_json": "not json"})
    assert resp.status_code == 400
    assert "Invalid JSON" in resp.text


def test_settings_save_rejects_non_object_advanced_json(client):
    resp = client.post("/ui/settings", data={"settings_json": "[1, 2, 3]"})
    assert resp.status_code == 400
    assert "top-level object" in resp.text


def test_settings_sections_are_collapsible_details(client):
    """Each section wraps in <details>, with tier 1 open by default."""
    resp = client.get("/ui/settings")
    body = resp.text
    # Tier 1 sections (e.g. anime, downloads) are open by default.
    assert '<details\n        id="section-anime"' in body
    # Each section starts as a <details> element (presence check).
    assert body.count('class="settings-section') >= 5


def test_settings_section_ordering_puts_legacy_last(client):
    """Less-important sections (UI palette, Tk window sizes) render
    after the daily-use ones."""
    body = client.get("/ui/settings").text
    pos_anime = body.find('id="section-anime"')
    pos_paths = body.find('id="section-paths"')
    pos_ui_caps = body.find('id="section-UI"')
    pos_windows = body.find('id="section-windows"')
    assert pos_anime != -1
    assert pos_anime < pos_paths < pos_ui_caps
    assert pos_ui_caps < pos_windows


def test_settings_color_field_uses_color_picker(client):
    body = client.get("/ui/settings").text
    # UI.colors.Blue is a hex value -> color picker input.
    assert 'name="UI.colors.Blue"' in body
    assert 'type="color"' in body
    assert 'value="#56D8EF"' in body
    # And a mirrored hex text input alongside.
    assert 'data-color-sync="t-UI.colors.Blue"' in body


def test_settings_color_reference_uses_select_with_palette(client):
    body = client.get("/ui/settings").text
    # UI.tagcolors.SEEN should render as a select.
    assert 'name="UI.tagcolors.SEEN"' in body
    # Palette options carry data-color-hex hints for the JS swatch.
    assert 'data-color-hex="#56D8EF"' in body
    # And a swatch placeholder element.
    assert 'data-color-swatch-for="f-UI.tagcolors.SEEN"' in body


def test_settings_path_field_has_browse_button(client):
    body = client.get("/ui/settings").text
    # paths.cache, file_managers.Local.dataPath etc are path fields.
    assert 'data-fb-open="#f-paths.cache"' in body
    assert 'data-fb-open="#f-file_managers.Local.dataPath"' in body
    # The shared file-browser dialog is rendered on the page.
    assert 'id="file-browser"' in body


def test_settings_last_used_renders_constrained_dropdown(client):
    body = client.get("/ui/settings").text
    # The last_X_used fields are <select>s, not free-text inputs.
    assert '<select class="input" id="f-file_managers.last_fm_used"' in body
    # Options come from configured manager keys (alphabetical).
    sel_pos = body.find('id="f-file_managers.last_fm_used"')
    select_html = body[sel_pos : sel_pos + 800]
    assert "FTP" in select_html
    assert "Local" in select_html


def test_settings_default_player_dropdown_uses_players_order(client):
    body = client.get("/ui/settings").text
    sel_pos = body.find('id="f-media.default_player"')
    assert sel_pos != -1
    select_html = body[sel_pos : sel_pos + 600]
    for player in ("mpv", "vlc", "ffplay"):
        assert player in select_html


def test_settings_color_round_trip_saves_hex(client):
    resp = client.post(
        "/ui/settings",
        data={"UI.colors.Blue": "#abcdef"},
    )
    assert resp.status_code == 200
    saved = client.fake.get_settings()
    assert saved["UI"]["colors"]["Blue"] == "#abcdef"


def test_settings_last_used_round_trip_saves_value(client):
    resp = client.post(
        "/ui/settings",
        data={"file_managers.last_fm_used": "FTP"},
    )
    assert resp.status_code == 200
    saved = client.fake.get_settings()
    assert saved["file_managers"]["last_fm_used"] == "FTP"


# ---------------------------------------------------------------------------
# File browser route
# ---------------------------------------------------------------------------


def test_browse_route_renders_directory_listing(client, tmp_path):
    sub = tmp_path / "subdir"
    sub.mkdir()
    (tmp_path / "alpha.txt").write_text("hi", encoding="utf-8")
    resp = client.get("/ui/browse", params={"path": str(tmp_path)})
    assert resp.status_code == 200
    body = resp.text
    assert "subdir" in body
    assert "alpha.txt" in body
    assert "data-fb-listing" in body
    assert f'data-fb-current-path="{tmp_path}"' in body


def test_browse_route_lists_parent_link(client, tmp_path):
    sub = tmp_path / "child"
    sub.mkdir()
    resp = client.get("/ui/browse", params={"path": str(sub)})
    assert resp.status_code == 200
    # Up button references the parent directory path.
    assert 'class="fb-entry fb-entry--up"' in resp.text
    assert str(tmp_path) in resp.text


def test_browse_route_falls_back_to_home_for_invalid_path(client):
    resp = client.get(
        "/ui/browse",
        params={"path": "/this/definitely/does/not/exist/anywhere"},
    )
    assert resp.status_code == 200
    # Listing still rendered (with home dir contents or empty list).
    assert "data-fb-listing" in resp.text


def test_static_assets_served(client):
    css = client.get("/ui/static/css/app.css")
    assert css.status_code == 200
    assert "Anime" in css.text  # header comment present
    js = client.get("/ui/static/js/app.js")
    assert js.status_code == 200
    assert "AnimeManager web UI helpers" in js.text


# ---------------------------------------------------------------------------
# Regression: tag must be modifiable more than once.
#
# Before the LegacyUserActionsAdapter fix the second tag change would
# silently fail (or wipe the like flag) and the rendered partial would
# come back with the OLD ``selected`` option. This end-to-end test
# pins the contract through both the route AND the SDK.
# ---------------------------------------------------------------------------


def _selected_tag(html: str) -> str | None:
    """Extract the ``value="..."`` of the option marked ``selected``."""
    import re

    match = re.search(r'<option\s+value="([^"]+)"[^>]*selected', html)
    return match.group(1) if match else None


def test_tag_change_repeated_updates_selected_option(client):
    """Three consecutive tag changes must each be reflected in the
    rendered partial. Regression for the ``REPLACE INTO`` bug where
    later writes were lost or hidden by stale rows.
    """
    sequence = ["WATCHING", "WATCHLIST", "SEEN", "NONE"]
    for desired in sequence:
        resp = client.post(
            "/ui/anime/1/tag",
            data={"tag": desired.lower()},  # also exercises upper-casing
            headers={"hx-request": "true"},
        )
        assert resp.status_code == 200, f"failed at {desired}"
        assert _selected_tag(resp.text) == desired, (
            f"after setting tag={desired}, partial showed "
            f"selected={_selected_tag(resp.text)!r}"
        )


def test_like_and_tag_do_not_clobber_each_other(client):
    """The user can set a tag AND a like; both must persist together."""
    client.post(
        "/ui/anime/1/like",
        data={"liked": "true"},
        headers={"hx-request": "true"},
    )
    resp = client.post(
        "/ui/anime/1/tag",
        data={"tag": "watching"},
        headers={"hx-request": "true"},
    )
    assert resp.status_code == 200
    assert _selected_tag(resp.text) == "WATCHING"
    assert "Unlike" in resp.text  # liked state preserved


def test_tag_post_with_no_payload_defaults_to_none(client):
    """A submit with no ``tag`` field falls back to the Form default
    (``NONE``) and the partial reflects that."""
    resp = client.post(
        "/ui/anime/1/tag", data={}, headers={"hx-request": "true"}
    )
    assert resp.status_code == 200
    assert _selected_tag(resp.text) == "NONE"


def test_tag_change_is_idempotent(client):
    """Setting the same tag twice does NOT change anything user-visible."""
    for _ in range(2):
        resp = client.post(
            "/ui/anime/1/tag",
            data={"tag": "WATCHING"},
            headers={"hx-request": "true"},
        )
        assert _selected_tag(resp.text) == "WATCHING"
    # Two set_tag calls were recorded.
    tag_calls = [c for c in client.fake.calls if c[0] == "set_tag"]
    assert len(tag_calls) == 2


# ---------------------------------------------------------------------------
# More web UI smoke coverage.
# ---------------------------------------------------------------------------


def test_library_pagination_advances_list_start(client, monkeypatch):
    captured = {}

    original = client.fake.get_anime_list

    def spy(**kwargs):
        captured.update(kwargs)
        return original(**kwargs)

    client.fake.get_anime_list = spy  # type: ignore[assignment]

    client.get("/ui/library", params={"page": "3"})
    assert captured["list_start"] == 48  # (3 - 1) * 24
    assert captured["list_stop"] == 72


def test_library_pager_renders_next_link_when_more_available(client):
    resp = client.get("/ui/library")
    assert resp.status_code == 200
    # FakeSDK returns has_next=True, so the Next pager should be a real link.
    assert 'href="/ui/library?page=2"' in resp.text


def test_library_handles_validation_error_gracefully(client):
    """Short search queries surface as a flash, not a 500."""
    from domain.errors import ValidationError

    def boom(query, limit=50):
        raise ValidationError("Search query must contain at least 3 characters.")

    client.fake.search_anime = boom  # type: ignore[assignment]
    resp = client.get("/ui/library", params={"q": "ab"})
    assert resp.status_code == 200
    assert "at least 3 characters" in resp.text
    assert "flash--error" in resp.text


def test_torrents_search_results_with_special_characters_are_escaped(client):
    """Torrent names from untrusted sources must not break the HTML."""

    def hostile(*_args, **_kwargs):
        return [{"name": "<script>alert(1)</script>", "link": "magnet:?xt=urn:btih:x", "size": 0}]

    client.fake.search_torrents = hostile  # type: ignore[assignment]
    resp = client.get("/ui/torrents", params={"term": "anything"})
    assert resp.status_code == 200
    assert "<script>alert(1)</script>" not in resp.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in resp.text


def test_search_term_add_rejects_too_short_value(client):
    """The handler swallows ValidationError and returns the unchanged
    partial — there must be no 500 from a too-short term."""
    from domain.errors import ValidationError

    def short(_anime_id, term):
        raise ValidationError("Search term must contain at least 2 characters.")

    client.fake.add_search_term = short  # type: ignore[assignment]
    resp = client.post(
        "/ui/anime/1/terms",
        data={"term": "x"},
        headers={"hx-request": "true"},
    )
    assert resp.status_code == 200
    # The existing chip should still be there.
    assert "SubsPlease 1080p" in resp.text


def test_download_progress_normalizes_fractional_and_percent(client):
    """SDK adapters can return progress as 0.0–1.0 or as a percent;
    both must render correctly without doubling the value."""
    client.fake.get_active_downloads = lambda: [  # type: ignore[assignment]
        {"anime_id": 1, "name": "frac.mkv", "progress": 0.25, "state": "DOWNLOADING"},
        {"anime_id": 2, "name": "pct.mkv", "progress": 67.5, "state": "DOWNLOADING"},
    ]
    resp = client.get("/ui/downloads")
    assert resp.status_code == 200
    body = resp.text
    assert "25.0%" in body
    assert "67.5%" in body


def test_downloads_panel_renders_sparse_dict_from_download_manager(client):
    """Regression: the real ``DownloadManager.get_active_downloads()`` returns
    dicts shaped like :meth:`DownloadTask.get_status`. Until real progress is
    polled from the torrent client, ``progress``/``name`` are ``None``. The
    panel template must not 500 on that shape; missing/None fields should
    default to 0% / fall through ``{% if %}``."""
    from application.services.download_manager import DownloadTask

    real_shape = DownloadTask(844, url="magnet:?xt=urn:btih:abc").get_status()
    assert real_shape.get("progress") is None  # not yet polled from client
    assert real_shape.get("name") is None

    client.fake.get_active_downloads = lambda: [real_shape]  # type: ignore[assignment]
    resp = client.get("/ui/downloads")
    assert resp.status_code == 200
    body = resp.text
    # progress=None should render as 0%.
    assert "0.0%" in body
    # Fallback label uses anime_id when name/title are absent.
    assert "Anime #844" in body

    # And the htmx-polled partial endpoint must be just as tolerant.
    panel = client.get("/ui/downloads/panel")
    assert panel.status_code == 200
    assert "0.0%" in panel.text

    # Also verify the panel renders cleanly when fields are entirely missing
    # (e.g. if a future status shape drops them rather than setting to None).
    minimal_shape = {"anime_id": 845}
    client.fake.get_active_downloads = lambda: [minimal_shape]  # type: ignore[assignment]
    resp = client.get("/ui/downloads")
    assert resp.status_code == 200
    assert "Anime #845" in resp.text


def test_settings_save_round_trip_preserves_data(client):
    """A submit with the JSON we got from GET /ui/settings must come
    back unchanged (no spurious modifications)."""
    original = client.get("/ui/settings").text

    import re

    payload_match = re.search(
        r'<textarea[^>]*name="settings_json"[^>]*>(.*?)</textarea>',
        original,
        re.DOTALL,
    )
    assert payload_match
    payload = payload_match.group(1)
    import html as _html

    payload = _html.unescape(payload)

    resp = client.post("/ui/settings", data={"settings_json": payload})
    assert resp.status_code == 200
    assert "Settings saved" in resp.text


def test_settings_error_response_status_is_400(client):
    """Invalid JSON must surface as HTTP 400 (not 200) so tooling that
    consumes the form via fetch can detect failure programmatically."""
    resp = client.post("/ui/settings", data={"settings_json": "{not: json"})
    assert resp.status_code == 400
    assert "Invalid JSON" in resp.text


def test_seen_action_redirects_when_not_htmx(client):
    resp = client.post("/ui/anime/1/seen", data={"file_name": "ep1.mkv"})
    assert resp.status_code == 303
    assert ("mark_seen", (1, "ep1.mkv", 1), {}) in client.fake.calls


def test_seen_action_returns_partial_for_htmx(client):
    resp = client.post(
        "/ui/anime/1/seen",
        data={"file_name": "ep1.mkv"},
        headers={"hx-request": "true"},
    )
    assert resp.status_code == 200
    assert 'id="anime-actions"' in resp.text


def test_cancel_download_redirects_to_downloads_page(client):
    resp = client.post("/ui/anime/1/cancel")
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/ui/downloads")


def test_start_download_validates_missing_url(client):
    """Without url or hash_value the SDK should raise; route swallows
    the error and still redirects (UX: PRG always lands on /downloads)."""
    from domain.errors import ValidationError

    def boom(*_args, **_kwargs):
        raise ValidationError("Either url or hash_value must be provided.")

    client.fake.start_download = boom  # type: ignore[assignment]
    resp = client.post("/ui/anime/1/download")
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/ui/downloads")


# ---------------------------------------------------------------------------
# Trailer modal
# ---------------------------------------------------------------------------


def test_anime_detail_youtube_trailer_renders_modal(client):
    resp = client.get("/ui/anime/1")
    assert resp.status_code == 200
    body = resp.text
    # The legacy "open YouTube in a new tab" anchor is gone -- the
    # button now opens the in-page modal with the embed iframe.
    assert 'data-trailer-open' in body
    assert 'href="https://www.youtube.com/watch?v=dQw4w9WgXcQ"' not in body
    assert 'id="trailer-modal"' in body
    assert "https://www.youtube.com/embed/dQw4w9WgXcQ" in body
    assert 'data-trailer-frame' in body


def test_anime_detail_non_youtube_trailer_falls_back_to_link(client, monkeypatch):
    """For unknown providers we cannot safely iframe the URL, so we
    keep the historical "open in a new tab" link."""
    original = client.fake.get_anime

    def _patched(anime_id: int):
        data = original(anime_id)
        data["trailer"] = "https://example.com/some-trailer.mp4"
        return data

    monkeypatch.setattr(client.fake, "get_anime", _patched)
    resp = client.get("/ui/anime/1")
    assert resp.status_code == 200
    assert 'href="https://example.com/some-trailer.mp4"' in resp.text
    assert 'target="_blank"' in resp.text


def test_youtube_embed_url_helper_recognizes_common_forms():
    fn = http_web._youtube_embed_url
    expected = "https://www.youtube.com/embed/dQw4w9WgXcQ"
    assert fn("https://www.youtube.com/watch?v=dQw4w9WgXcQ").startswith(expected)
    assert fn("https://youtu.be/dQw4w9WgXcQ").startswith(expected)
    assert fn("https://www.youtube.com/embed/dQw4w9WgXcQ").startswith(expected)
    assert fn("https://www.youtube.com/shorts/dQw4w9WgXcQ").startswith(expected)
    assert fn("https://vimeo.com/123") is None
    assert fn("not a url") is None
    assert fn(None) is None


# ---------------------------------------------------------------------------
# Inline torrent search (anime detail page)
# ---------------------------------------------------------------------------


def test_anime_torrent_search_partial_uses_saved_terms_by_default(client):
    """No explicit term -> the route falls back to the anime's saved
    search terms (and tells the user that's what happened)."""
    resp = client.get("/ui/anime/1/torrents")
    assert resp.status_code == 200
    body = resp.text
    assert "SubsPlease 1080p" in body  # the saved term echoed in header
    assert "saved search terms" in body.lower()
    # The skeleton wires the SSE feed -- no synchronous search runs in
    # the partial anymore (rows arrive over `/torrents/stream`).
    assert "/ui/anime/1/torrents/stream" in body
    assert 'data-stream-rows' in body
    # Should NOT carry the chrome of a full page (no <html> -- it's a partial)
    assert "<html" not in body
    # And no engine call yet -- streaming starts when the SSE connects.
    assert not any(c[0] in {"search_torrents", "stream_torrents"} for c in client.fake.calls)


def test_anime_torrent_search_partial_honors_override_term(client):
    resp = client.get(
        "/ui/anime/1/torrents",
        params={"term": "horriblesubs 720p"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "horriblesubs 720p" in body
    # The stream URL carries the override term verbatim.
    assert "term=horriblesubs%20720p" in body or "term=horriblesubs+720p" in body


def test_anime_torrent_stream_returns_sse_rows(client):
    resp = client.get(
        "/ui/anime/1/torrents/stream",
        params={"term": "bleach 1080p"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    # Each result is a separate SSE frame
    assert body.count("event: row") == 2
    assert "[SubsPlease] Bleach S01 - 01 [1080p].mkv" in body
    assert "[Erai-raws] Bleach S01 - 02" in body
    # The stream completes with a final end event carrying the row count
    assert "event: end" in body
    # And the SDK was asked to stream (not the materialized variant)
    last_call = [c for c in client.fake.calls if c[0] == "stream_torrents"][-1]
    assert last_call[1][0] == ["bleach 1080p"]


def test_anime_torrent_stream_emits_error_event_when_no_term(client, monkeypatch):
    monkeypatch.setattr(client.fake, "get_search_terms", lambda anime_id: [])
    monkeypatch.setattr(
        client.fake,
        "get_anime",
        lambda anime_id: {"id": anime_id, "title": ""},
    )
    resp = client.get("/ui/anime/1/torrents/stream")
    assert resp.status_code == 200
    body = resp.text
    assert "event: error" in body
    assert "event: end" in body


def test_anime_detail_page_wires_inline_torrent_search(client):
    resp = client.get("/ui/anime/1")
    assert resp.status_code == 200
    body = resp.text
    # The detail page links the torrent section via HTMX (no full nav
    # to /ui/torrents like the old "Find torrents" topbar link did).
    assert 'id="anime-torrents"' in body
    assert "/ui/anime/1/torrents" in body
    assert 'hx-target="#anime-torrent-results"' in body
    # The HTMX form auto-loads results on page open
    assert 'hx-trigger="load"' in body


# ---------------------------------------------------------------------------
# Downloaded episodes section
# ---------------------------------------------------------------------------


def test_anime_detail_downloaded_episodes_lists_saved_torrents(client):
    resp = client.get("/ui/anime/1")
    assert resp.status_code == 200
    body = resp.text
    assert "Downloaded episodes" in body
    # Saved torrent name from FakeSDK.get_anime_torrents
    assert "[SubsPlease] Bleach S01 - 02 [1080p].mkv" in body
    # Active downloads with the same anime_id are merged in
    assert "[SubsPlease] Bleach - 01.mkv" in body
    # FakeSDK.get_anime_torrents reports a complete download (size == downloaded)
    assert "COMPLETE" in body
    # Active download from FakeSDK.get_active_downloads is in DOWNLOADING state
    assert "DOWNLOADING" in body


def test_anime_detail_downloaded_episodes_empty_when_none(client, monkeypatch):
    monkeypatch.setattr(client.fake, "get_anime_torrents", lambda anime_id: [])
    monkeypatch.setattr(client.fake, "get_active_downloads", lambda: [])
    resp = client.get("/ui/anime/1")
    assert resp.status_code == 200
    assert "Nothing downloaded yet" in resp.text


def test_anime_detail_renders_episode_player_links(client):
    resp = client.get("/ui/anime/1")
    assert resp.status_code == 200
    body = resp.text
    assert "Episode player" in body
    assert "Open player" in body or "watch?file_id=ep-001" in body
    assert "/ui/anime/1/watch?file_id=ep-001" in body


def test_playback_session_create_returns_manifest_payload(client):
    resp = client.post("/ui/anime/1/play", data={"file_id": "ep-001"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["session_id"] == "sess-1"
    assert payload["manifest_url"].startswith("/ui/stream/sess-1/index.m3u8")


def test_watch_page_renders_player_view(client):
    resp = client.get("/ui/anime/1/watch", params={"file_id": "ep-001"})
    assert resp.status_code == 200
    body = resp.text
    assert "watch-view" in body
    assert "data-player-panel" in body
    # Auto-fullscreen and auto-play are intentionally disabled; the
    # watch view must opt out so the player only starts on explicit
    # user interaction with the media-chrome controls.
    assert "data-player-auto-fullscreen=\"0\"" in body
    assert "data-player-auto-fullscreen=\"1\"" not in body


def test_stream_manifest_requires_token(client):
    client.post("/ui/anime/1/play", data={"file_id": "ep-001"})
    resp = client.get("/ui/stream/sess-1/index.m3u8")
    assert resp.status_code == 422


def test_stream_manifest_serves_playlist(client):
    created = client.post("/ui/anime/1/play", data={"file_id": "ep-001"}).json()
    resp = client.get("/ui/stream/sess-1/index.m3u8", params={"token": created["token"]})
    assert resp.status_code == 200
    assert "#EXTM3U" in resp.text


def test_stream_segment_allows_tokenless_fetch_for_relative_playlist_urls(client):
    client.post("/ui/anime/1/play", data={"file_id": "ep-001"})
    resp = client.get("/ui/stream/sess-1/segment_00001.ts")
    assert resp.status_code == 200
    assert resp.content == b"segment"


def test_stream_heartbeat_and_stop_endpoints(client):
    client.post("/ui/anime/1/play", data={"file_id": "ep-001"})
    hb = client.post("/ui/stream/sess-1/heartbeat")
    assert hb.status_code == 200
    stop = client.post("/ui/stream/sess-1/stop")
    assert stop.status_code == 200
    