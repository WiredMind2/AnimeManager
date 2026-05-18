"""Server-rendered web UI for the AnimeManager HTTP client adapter.

This module is the canonical web frontend for AnimeManager. It is part
of the ``clients/http`` peer adapter (see ``docs/adr/0001-embedded-runtime-model.md``)
and may only consume the embedded backend through
:class:`clients.sdk.ClientSDK` -- it never reaches into adapters or
backend internals directly.

The UI is intentionally server-rendered with Jinja2 + a small CSS
design system + HTMX for partial swaps. Every route degrades to a
plain HTML form so the app works without JavaScript.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import ipaddress
import logging
import os
import queue
import re
import threading
import time
import types
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

from fastapi import (
    APIRouter,
    Form,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

try:  # pragma: no cover - import path differs depending on launch mode
    from ...shared.config.getters import Getters
    from ...domain.entities import title_variants_for_torrent_search
    from ...domain.errors import (
        AnimeManagerError,
        NotFoundError,
        UnauthorizedError,
        ValidationError,
    )
    from ..sdk import ClientSDK
    from . import log_buffer, settings_form
except ImportError:  # pragma: no cover
    from shared.config.getters import Getters  # type: ignore  # noqa: F401
    from clients.sdk import ClientSDK
    from clients.http import log_buffer, settings_form  # type: ignore  # noqa: F401
    from domain.entities import title_variants_for_torrent_search  # type: ignore  # noqa: F401
    from domain.errors import (  # type: ignore  # noqa: F401
        AnimeManagerError,
        NotFoundError,
        UnauthorizedError,
        ValidationError,
    )

_LOG = logging.getLogger(__name__)

# Per-anime metadata refresh throttle (max once per hour).
_METADATA_REFRESH_TS: dict[int, float] = {}
_METADATA_REFRESH_INTERVAL_S = 3600.0


def _maybe_refresh_anime_metadata(sdk: ClientSDK, anime_id: int) -> None:
    """Best-effort metadata refresh when opening anime detail (rate limited)."""
    now = time.monotonic()
    last = _METADATA_REFRESH_TS.get(int(anime_id))
    if last is not None and (now - last) < _METADATA_REFRESH_INTERVAL_S:
        return
    _METADATA_REFRESH_TS[int(anime_id)] = now
    try:
        getattr(sdk, "refresh_anime_metadata", lambda _id: None)(anime_id)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("auto refresh_anime_metadata failed: %s", exc)


# ---------------------------------------------------------------------------
# Resource paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
TEMPLATES_DIR = HERE / "templates"
STATIC_DIR = HERE / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _jinja_youtube_embed(value: Any) -> str | None:
    """Jinja filter alias for :func:`_youtube_embed_url`."""
    return _youtube_embed_url(value if isinstance(value, str) else None)


templates.env.filters["youtube_embed"] = _jinja_youtube_embed

router = APIRouter(default_response_class=HTMLResponse)

# ---------------------------------------------------------------------------
# Defaults / config
# ---------------------------------------------------------------------------
PAGE_SIZE = 24
DEFAULT_USER_ID = 1
# Cap rows returned to the torrents page and anime-detail SSE stream.
# Must stay <= profile ``max_results`` (750 interactive); aligns with
# ``ClientSDK.search_torrents`` / REST default limit (200).
TORRENT_RESULT_LIMIT = 200
PLAYBACK_SESSION_TTL_SECONDS = 900

# Maps to the historical Tk filter list (settings.json filter parity).
FILTER_OPTIONS: list[dict[str, Any]] = [
    {"value": "DEFAULT", "label": "All", "dot": None},
    {"value": "WATCHING", "label": "Watching", "dot": "#E79622"},
    {"value": "WATCHLIST", "label": "Watchlist", "dot": "#56D8EF"},
    {"value": "SEEN", "label": "Seen", "dot": "#98E22B"},
    {"value": "LIKED", "label": "Liked", "dot": "#F92472"},
    {"value": "FINISHED", "label": "Finished", "dot": "#98E22B"},
    {"value": "AIRING", "label": "Airing", "dot": "#E79622"},
    {"value": "UPCOMING", "label": "Upcoming", "dot": "#56D8EF"},
    {"value": "RATED", "label": "Rated", "dot": None},
    {"value": "NO_TAGS", "label": "No tags", "dot": None},
    {"value": "RANDOM", "label": "Random", "dot": None},
]


def get_sdk() -> ClientSDK:
    """SDK accessor.

    Lazily delegates to :func:`clients.http.app.get_sdk` at call time
    so a single ``monkeypatch.setattr(http_app, "get_sdk", ...)``
    covers both the JSON API and the web UI in tests. The import is
    deferred (and uses :func:`importlib.import_module` to bypass the
    ``clients.http.__init__`` re-export shadowing) to avoid a circular
    import during module load.
    """
    import importlib

    app_module = importlib.import_module("clients.http.app")
    return app_module.get_sdk()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flash(kind: str, message: str) -> dict[str, str]:
    return {"kind": kind, "message": message}


def _render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
) -> HTMLResponse:
    ctx = {"request": request, "filter_options": FILTER_OPTIONS}
    if context:
        ctx.update(context)
    return templates.TemplateResponse(template, ctx, status_code=status_code)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _format_unix_date(value: Any) -> str | None:
    """Best-effort ``YYYY-MM-DD`` formatter for Unix timestamps."""
    try:
        stamp = int(float(value))
    except (TypeError, ValueError):
        return None
    if stamp <= 0:
        return None
    try:
        return dt.datetime.fromtimestamp(
            stamp, tz=dt.timezone.utc
        ).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        source = value
    else:
        source = [value]
    out: list[str] = []
    seen: set[str] = set()
    for raw in source:
        text = str(raw or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


_UNKNOWN_GENRE = "Unknown genre"


def _detail_field(label: str, value: Any, *, hint: str | None = None) -> dict[str, str] | None:
    text = str(value or "").strip()
    if not text:
        return None
    row: dict[str, str] = {"label": label, "value": text}
    hint_text = str(hint or "").strip()
    if hint_text:
        row["hint"] = hint_text
    return row


def _split_value_hint(text: str) -> tuple[str, str | None]:
    """Split ``Since 07 Apr 2026 (41 days)`` into value + parenthetical hint."""
    cleaned = str(text or "").strip()
    match = re.match(r"^(.*?)(?:\s*\(([^)]+)\))?\s*$", cleaned)
    if not match:
        return cleaned, None
    value = str(match.group(1) or "").strip()
    hint = str(match.group(2) or "").strip() or None
    return value, hint


def _parse_schedule_line(line: str) -> dict[str, str]:
    """Map legacy schedule strings to user-facing labels."""
    text = str(line or "").strip()
    lower = text.casefold()
    if lower.startswith("since "):
        value, hint = _split_value_hint(text[6:])
        return _detail_field("Airs", value, hint=hint) or {"label": "Airs", "value": text}
    if lower.startswith("from "):
        value, hint = _split_value_hint(text[5:])
        return _detail_field("Started", value, hint=hint) or {"label": "Started", "value": text}
    if lower.startswith("to "):
        value, hint = _split_value_hint(text[3:])
        return _detail_field("Ended", value, hint=hint) or {"label": "Ended", "value": text}
    if lower.startswith("next episode"):
        if lower.startswith("next episode on "):
            value = text[16:].strip()
        elif lower.startswith("next episode: "):
            value = text[14:].strip()
        else:
            value = text[14:].strip()
        return _detail_field("Next episode", value) or {"label": "Next episode", "value": text}
    if lower.startswith("latest episode"):
        value = text.split(":", 1)[-1].strip() if ":" in text else text[15:].strip()
        return _detail_field("Latest episode", value) or {"label": "Latest episode", "value": text}
    if "days left" in lower:
        value, hint = _split_value_hint(text)
        return _detail_field("Premieres", value, hint=hint) or {"label": "Premieres", "value": text}
    return {"label": "Timeline", "value": text}


def _lookup_genre_index_names(index_ids: list[str]) -> dict[str, str]:
    """Resolve ``genresIndex`` ids to display names."""
    numeric: list[int] = []
    for raw in index_ids:
        try:
            numeric.append(int(str(raw).strip()))
        except (TypeError, ValueError):
            continue
    if not numeric:
        return {}
    try:
        db = Getters.getDatabase(None)
        placeholders = ",".join("?" for _ in numeric)
        sql = f"SELECT id, value FROM genresIndex WHERE id IN ({placeholders})"
        rows = db.sql(sql, tuple(numeric))
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, str] = {}
    for row in rows or []:
        if not row or len(row) < 2:
            continue
        key = str(row[0]).strip()
        name = str(row[1] or "").strip()
        if key and name:
            out[key] = name
    return out


def _resolve_genre_tags(anime_id: int | None, raw_genres: Any) -> list[str]:
    """Return human-readable genre names, never raw index ids."""
    if anime_id is not None:
        try:
            db = Getters.getDatabase(None)
            fetcher = getattr(db, "_fetch_genre_metadata_for_id", None)
            if callable(fetcher):
                resolved = _string_list(fetcher(anime_id))
                if resolved:
                    return resolved
        except Exception:  # noqa: BLE001
            pass

    raw_values = _string_list(raw_genres)
    if not raw_values:
        return []

    numeric_ids = [value for value in raw_values if value.isdigit()]
    index_names = _lookup_genre_index_names(numeric_ids)
    out: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        if value.isdigit():
            name = index_names.get(value)
            label = name or _UNKNOWN_GENRE
        else:
            label = value
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(label)
    return out


def _build_anime_detail_view(
    anime: dict[str, Any],
    *,
    anime_id: int | None,
    terms: list[str],
    computed_status_text: str,
    schedule_lines: list[str],
) -> dict[str, Any]:
    """Grouped, display-safe fields for the anime detail template."""
    title = str(anime.get("title") or "").strip()
    alt_titles = [
        value
        for value in _string_list(anime.get("title_synonyms"))
        if value.casefold() != title.casefold()
    ]
    genre_tags = _resolve_genre_tags(anime_id, anime.get("genres"))

    airing_fields: list[dict[str, str]] = []
    status_field = _detail_field("Status", computed_status_text)
    if status_field:
        airing_fields.append(status_field)
    for line in schedule_lines:
        airing_fields.append(_parse_schedule_line(line))

    metadata_fields: list[dict[str, str]] = []
    for label, value in (
        ("Start date", _format_unix_date(anime.get("date_from"))),
        ("End date", _format_unix_date(anime.get("date_to"))),
        ("Broadcast", anime.get("broadcast")),
        ("Last seen", anime.get("last_seen")),
    ):
        field = _detail_field(label, value)
        if field:
            metadata_fields.append(field)
    if terms:
        field = _detail_field("Saved search terms", ", ".join(_string_list(terms)))
        if field:
            metadata_fields.append(field)

    return {
        "alt_titles": alt_titles,
        "genre_tags": genre_tags,
        "airing_fields": airing_fields,
        "metadata_fields": metadata_fields,
    }


def anime_detail_display_for_api(
    sdk: ClientSDK,
    anime_id: int,
    *,
    anime: dict[str, Any] | None = None,
    terms: list[str] | None = None,
) -> dict[str, Any]:
    """JSON display extras for :func:`clients.http.app.ui_api_anime_bundle`."""
    resolved = anime if isinstance(anime, dict) else sdk.get_anime(anime_id) or {}
    terms_list = list(terms if terms is not None else sdk.get_search_terms(anime_id) or [])
    settings: dict[str, Any] = {}
    try:
        settings = sdk.get_settings() or {}
    except Exception:  # noqa: BLE001
        settings = {}

    trailer_embed: str | None = None
    computed_status = "UNKNOWN"
    computed_status_text = "Unknown"
    computed_status_color = ""
    schedule_lines: list[str] = []
    alt_titles: list[str] = []
    detail_genre_tags: list[str] = []
    detail_airing_fields: list[dict[str, str]] = []
    detail_metadata_fields: list[dict[str, str]] = []

    if isinstance(resolved, dict):
        trailer_embed = _youtube_embed_url(resolved.get("trailer"))
        computed_status, schedule_lines = _legacy_status_lines(resolved)
        computed_status_text, computed_status_color = _status_theme_meta(
            settings, computed_status
        )
        detail_view = _build_anime_detail_view(
            resolved,
            anime_id=anime_id,
            terms=terms_list,
            computed_status_text=computed_status_text,
            schedule_lines=schedule_lines,
        )
        alt_titles = detail_view["alt_titles"]
        detail_genre_tags = detail_view["genre_tags"]
        detail_airing_fields = detail_view["airing_fields"]
        detail_metadata_fields = detail_view["metadata_fields"]

    relations: list[dict[str, Any]] = []
    try:
        relations = _enrich_relations_with_user_tag(
            sdk, list(sdk.get_relations(anime_id) or [])
        )
    except Exception:  # noqa: BLE001
        relations = []

    return {
        "trailer_embed": trailer_embed,
        "alt_titles": alt_titles,
        "detail_genre_tags": detail_genre_tags,
        "detail_airing_fields": detail_airing_fields,
        "detail_metadata_fields": detail_metadata_fields,
        "computed_status": computed_status,
        "computed_status_text": computed_status_text,
        "computed_status_color": computed_status_color,
        "relations": relations,
    }


def watch_context_for_api(
    sdk: ClientSDK,
    anime_id: int,
    *,
    file_id: str = "",
    user_id: int = DEFAULT_USER_ID,
) -> dict[str, Any]:
    """Watch-page player context for Next.js (mirrors ``web_anime_watch``)."""
    anime = sdk.get_anime(anime_id)
    try:
        episode_files = list(sdk.list_episode_files(anime_id, user_id=user_id) or [])
    except Exception:  # noqa: BLE001
        episode_files = []

    selected_file_id = str(file_id or "").strip()
    if not selected_file_id and episode_files:
        selected_file_id = str(episode_files[0].get("file_id") or "")
    selected_title = ""
    selected_audio_tracks: list[dict[str, Any]] = []
    selected_subtitle_tracks: list[dict[str, Any]] = []
    for item in episode_files:
        if str(item.get("file_id") or "") == selected_file_id:
            selected_title = str(item.get("title") or "")
            selected_audio_tracks = list(item.get("audio_tracks") or [])
            selected_subtitle_tracks = list(item.get("subtitle_tracks") or [])
            break

    track_map: dict[str, dict[str, list[dict[str, Any]]]] = {}
    episode_resume_map: dict[str, float] = {}
    for item in episode_files:
        fid = str(item.get("file_id") or "")
        if not fid:
            continue
        track_map[fid] = {
            "audio": list(item.get("audio_tracks") or []),
            "subtitles": list(item.get("subtitle_tracks") or []),
        }
        pos_raw = item.get("position_seconds")
        try:
            pos = float(pos_raw) if pos_raw is not None else 0.0
        except (TypeError, ValueError):
            pos = 0.0
        if pos >= 10.0:
            episode_resume_map[fid] = pos

    return {
        "anime": anime,
        "episode_files": episode_files,
        "selected_file_id": selected_file_id,
        "selected_file_title": selected_title,
        "selected_audio_tracks": selected_audio_tracks,
        "selected_subtitle_tracks": selected_subtitle_tracks,
        "track_map": track_map,
        "episode_resume_map": episode_resume_map,
        "play_endpoint": f"/ui/anime/{anime_id}/play",
        "progress_endpoint": f"/ui/anime/{anime_id}/episode-progress",
    }


def _anime_info_rows(
    anime: dict[str, Any],
    *,
    user_state: dict[str, Any],
    terms: list[str],
) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    """Legacy tuple API; prefer :func:`_build_anime_detail_view`."""
    anime_id_raw = anime.get("id")
    anime_id: int | None
    try:
        anime_id = int(anime_id_raw) if anime_id_raw is not None else None
    except (TypeError, ValueError):
        anime_id = None
    view = _build_anime_detail_view(
        anime,
        anime_id=anime_id,
        terms=terms,
        computed_status_text="",
        schedule_lines=[],
    )
    rows = [
        (field["label"], field["value"])
        for field in view["metadata_fields"]
    ]
    return view["genre_tags"], view["alt_titles"], rows


def _legacy_status_lines(anime: dict[str, Any]) -> tuple[str, list[str]]:
    """Reuse legacy status/date text policy from ``shared.config.getters``."""
    obj = types.SimpleNamespace(
        status=anime.get("status"),
        date_from=anime.get("date_from"),
        date_to=anime.get("date_to"),
        episodes=anime.get("episodes"),
        broadcast=anime.get("broadcast"),
    )
    status = str(Getters.getStatus(obj) or "UNKNOWN").upper()

    class _LegacyShim:
        @staticmethod
        def getStatus(anime_obj):
            return Getters.getStatus(anime_obj)

    try:
        lines = list(Getters.getDateText(_LegacyShim(), obj) or [])
    except Exception:  # noqa: BLE001
        lines = []
    return status, [str(line).strip() for line in lines if str(line).strip()]


def _status_theme_meta(
    settings: dict[str, Any], status: str
) -> tuple[str, str]:
    ui = settings.get("UI", {}) if isinstance(settings, dict) else {}
    date_states = ui.get("dateStates", {}) if isinstance(ui, dict) else {}
    state_meta = date_states.get(status, {}) if isinstance(date_states, dict) else {}
    text = str(state_meta.get("text") or status.title()).strip()
    color_key = str(state_meta.get("color") or "White").strip()
    colors = ui.get("colors", {}) if isinstance(ui, dict) else {}
    color = str(colors.get(color_key) or "").strip()
    return text, color


def _enrich_relations_with_user_tag(
    sdk: ClientSDK, relations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rel in relations:
        row = dict(rel or {})
        rel_id = row.get("id")
        rel_tag = "NONE"
        try:
            if rel_id is not None:
                state = sdk.get_user_state(int(rel_id), DEFAULT_USER_ID) or {}
                rel_tag = str(state.get("tag") or "NONE").upper()
        except Exception:  # noqa: BLE001
            rel_tag = "NONE"
        row["rel_tag"] = rel_tag
        out.append(row)
    return out


_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def _youtube_embed_url(url: str | None) -> str | None:
    """Return an ``/embed/<id>`` form for a YouTube URL, otherwise ``None``.

    Used to render trailers in an inline modal iframe instead of bouncing
    the user to a new tab. Any non-YouTube trailer URL is rejected so the
    caller can keep the legacy "open in new tab" affordance for unknown
    providers (frame-ancestor restrictions make a generic iframe unsafe).
    """
    if not url or not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        return None

    video_id: str | None = None
    if host == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/", 1)[0] or None
    elif parsed.path == "/watch":
        params = parse_qs(parsed.query)
        candidates = params.get("v") or []
        video_id = candidates[0] if candidates else None
    elif parsed.path.startswith("/embed/"):
        video_id = parsed.path[len("/embed/"):].split("/", 1)[0] or None
    elif parsed.path.startswith("/shorts/"):
        video_id = parsed.path[len("/shorts/"):].split("/", 1)[0] or None
    elif parsed.path.startswith("/v/"):
        video_id = parsed.path[len("/v/"):].split("/", 1)[0] or None

    if not video_id or not re.fullmatch(r"[A-Za-z0-9_-]{6,32}", video_id):
        return None
    return f"https://www.youtube.com/embed/{video_id}?rel=0&modestbranding=1"


def _humanize_size(num: Any) -> str | None:
    try:
        size = float(num)
    except (TypeError, ValueError):
        return None
    if size <= 0:
        return None
    units = ("B", "KB", "MB", "GB", "TB")
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    return f"{size:.1f} {units[idx]}"


def _collect_anime_torrents(sdk: ClientSDK, anime_id: int) -> list[dict[str, Any]]:
    """Return the union of saved + in-flight torrents for ``anime_id``.

    The anime detail "Episodes & downloads" section shows persisted
    torrent metadata together with any in-memory task for the same
    anime so the list stays accurate.
    Missing SDK methods or backend errors degrade to an empty list --
    every other section on the page is independent.
    """
    saved: list[dict[str, Any]] = []
    getter = getattr(sdk, "get_anime_torrents", None)
    if callable(getter):
        try:
            raw = list(getter(anime_id) or [])
        except Exception:  # noqa: BLE001
            _LOG.debug("get_anime_torrents failed", exc_info=True)
            raw = []
        for row in raw:
            saved.append(_normalize_anime_torrent_row(row))

    actives: list[dict[str, Any]] = []
    try:
        all_active = list(sdk.get_active_downloads() or [])
    except Exception:  # noqa: BLE001
        _LOG.debug("get_active_downloads failed during detail render", exc_info=True)
        all_active = []
    for dl in all_active:
        if not isinstance(dl, dict):
            continue
        try:
            if int(dl.get("anime_id") or 0) != int(anime_id):
                continue
        except (TypeError, ValueError):
            continue
        actives.append(_normalize_active_download(dl))

    seen_hashes = {row["hash"] for row in saved if row.get("hash")}
    for active in actives:
        if active.get("hash") and active["hash"] in seen_hashes:
            for row in saved:
                if row.get("hash") == active["hash"]:
                    row.update({k: v for k, v in active.items() if v is not None})
                    break
            continue
        saved.insert(0, active)

    return saved


def _normalize_anime_torrent_row(row: Any) -> dict[str, Any]:
    if hasattr(row, "__dataclass_fields__"):
        data = {field: getattr(row, field) for field in row.__dataclass_fields__}
    elif isinstance(row, dict):
        data = dict(row)
    else:
        data = {
            "hash": getattr(row, "hash", None),
            "name": getattr(row, "name", None),
            "size": getattr(row, "size", None),
            "downloaded": getattr(row, "downloaded", None),
            "path": getattr(row, "path", None),
        }
    data["size_human"] = _humanize_size(data.get("size"))
    state = (data.get("state") or "").upper() or None
    size = data.get("size") or 0
    downloaded = data.get("downloaded") or 0
    if state is None:
        if size and downloaded and downloaded >= size:
            state = "COMPLETE"
        elif downloaded:
            state = "DOWNLOADING"
        else:
            state = "SAVED"
    data["state"] = state
    try:
        progress = float(downloaded) / float(size) if size else None
    except (TypeError, ValueError, ZeroDivisionError):
        progress = None
    if progress is not None:
        data["progress"] = max(0.0, min(1.0, progress))
    return data


def _normalize_active_download(dl: dict[str, Any]) -> dict[str, Any]:
    return {
        "hash": dl.get("hash"),
        "name": dl.get("name") or dl.get("title") or f"Anime #{dl.get('anime_id') or '?'}",
        "size": dl.get("size"),
        "size_human": _humanize_size(dl.get("size")),
        "downloaded": dl.get("downloaded"),
        "progress": (
            float(dl["progress"])
            if isinstance(dl.get("progress"), (int, float))
            else None
        ),
        "state": (dl.get("state") or "DOWNLOADING").upper(),
        "dl_speed": dl.get("dl_speed"),
        "eta": dl.get("eta"),
        "path": dl.get("path"),
        "anime_id": dl.get("anime_id"),
    }


def _normalize_torrents(rows: Iterable[Any]) -> list[dict[str, Any]]:
    """Coerce SDK torrent search results into a homogeneous shape.

    Adapters may yield :class:`TorrentEntity` dataclasses, dicts, or
    plain mappings; the template wants a uniform dictionary with seeds
    / size / link / hash. We also surface the structured ``parsed``
    sub-object produced by :mod:`adapters.search.title_parser` so the
    template can render a metadata strip and the client-side filter
    chips can group results by publisher / quality / season.
    """
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if hasattr(row, "__dataclass_fields__"):
            data = {f: getattr(row, f) for f in row.__dataclass_fields__}
        elif isinstance(row, dict):
            data = dict(row)
        else:
            data = {
                "name": getattr(row, "name", str(row)),
                "link": getattr(row, "link", None),
                "size": getattr(row, "size", None),
                "seeds": getattr(row, "seeds", None),
                "leech": getattr(row, "leech", None),
                "hash": getattr(row, "hash", None),
            }
        data["size_human"] = _humanize_size(data.get("size"))
        # ``parsed`` may be either a ParsedTitle dataclass (when the
        # SDK returned a TorrentResult that wrapped one) or a plain
        # dict (when the row was already serialised over the wire).
        # Normalise to a dict so Jinja templates only have to handle
        # one shape.
        parsed = data.get("parsed")
        if parsed is not None and hasattr(parsed, "as_dict"):
            data["parsed"] = parsed.as_dict()
        elif parsed is None:
            # Last-chance fallback: parse the raw name here so legacy
            # SDK paths (that predate the wired-in parser) still get a
            # metadata strip in the UI.
            try:
                from adapters.search.title_parser import parse_title

                data["parsed"] = parse_title(data.get("name", "")).as_dict()
            except Exception:  # noqa: BLE001
                data["parsed"] = None
        out.append(data)
    return out


def _sse_event(event: str, data: str) -> bytes:
    """Encode one Server-Sent Events frame.

    Every ``\\n`` in ``data`` is rewritten as a separate ``data:`` field
    (per the SSE spec) so multi-line HTML snippets are reassembled
    correctly on the client. Output is UTF-8 bytes ready to be yielded
    from a :class:`StreamingResponse` body.
    """
    lines: list[str] = [f"event: {event}"]
    for chunk in data.splitlines() or [""]:
        lines.append(f"data: {chunk}")
    lines.append("")  # blank line terminates the frame
    lines.append("")
    return ("\n".join(lines)).encode("utf-8")


def _redirect(path: str) -> RedirectResponse:
    """303 redirect for POST handlers (Post/Redirect/Get pattern)."""
    return RedirectResponse(path, status_code=status.HTTP_303_SEE_OTHER)


def _redirect_get(path: str) -> RedirectResponse:
    """307 redirect for GET handlers (preserves method, no method coercion)."""
    return RedirectResponse(path, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


def _post_download_redirect_path(request: Request, anime_id: int) -> str:
    """Pick a safe 303 target after download start/cancel so users stay on the page they used.

    When the browser sends a same-origin ``Referer`` under ``/ui/``, return
    that path (and query); otherwise fall back to the anime detail URL.
    """
    fallback = f"/ui/anime/{anime_id}"
    raw = (request.headers.get("referer") or "").strip()
    if not raw:
        return fallback
    try:
        ref = urlparse(raw)
    except ValueError:
        return fallback
    if ref.scheme not in ("http", "https"):
        return fallback
    if (ref.netloc or "").lower() != request.url.netloc.lower():
        return fallback
    path = ref.path or ""
    if not path.startswith("/ui/") or ".." in PurePosixPath(path).parts:
        return fallback
    if ref.query:
        return f"{path}?{ref.query}"
    return path


def _is_htmx(request: Request) -> bool:
    """Return True when the request was issued by HTMX.

    HTMX sets ``HX-Request: true`` on every XHR it makes. We use it to
    decide between returning a partial fragment (no full reload) and
    the classic 303 PRG redirect that vanilla form submissions need.
    """
    return request.headers.get("hx-request", "").lower() == "true"


def _anime_actions_response(
    request: Request,
    anime_id: int,
    fallback_path: str | None = None,
) -> Response:
    """Render the anime-actions partial for HTMX or fall back to a 303.

    Used by the like/tag/seen handlers so a single change updates only
    the actions block (no full-page reload, no static-asset re-fetch)
    while non-JS clients still get a clean PRG redirect.
    """
    if not _is_htmx(request):
        return _redirect(fallback_path or f"/ui/anime/{anime_id}")

    sdk = get_sdk()
    try:
        anime = sdk.get_anime(anime_id)
    except Exception:  # noqa: BLE001 - already-loaded page; tolerate
        anime = {"id": anime_id, "title": "", "trailer": None}
    try:
        user_state = sdk.get_user_state(anime_id, DEFAULT_USER_ID) or {}
    except Exception:  # noqa: BLE001
        user_state = {}

    return _render(
        request,
        "partials/anime_actions.html",
        {
            "anime": anime,
            "user_state": user_state,
        },
    )


def _anime_episodes_panel_context(sdk: ClientSDK, anime_id: int) -> dict[str, Any]:
    """Build template context for the merged episode + torrent tables."""
    try:
        anime = sdk.get_anime(anime_id)
    except Exception:  # noqa: BLE001
        anime = {"id": anime_id, "title": ""}
    try:
        episode_files = list(
            sdk.list_episode_files(anime_id, user_id=DEFAULT_USER_ID) or []
        )
    except Exception:  # noqa: BLE001
        _LOG.debug("episode file lookup failed (panel)", exc_info=True)
        episode_files = []
    anime_torrents = _collect_anime_torrents(sdk, anime_id)
    return {
        "anime": anime,
        "episode_files": episode_files,
        "anime_torrents": anime_torrents,
    }


def _episode_player_response(request: Request, anime_id: int) -> Response:
    """Swap the episode table after HTMX mutations; silent 204 for in-player
    ``fetch`` (avoids 303 + full-page GET during streaming); redirect otherwise.
    """
    if request.headers.get("x-am-player-background", "").lower() == "true":
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if not _is_htmx(request):
        return _redirect(f"/ui/anime/{anime_id}")
    sdk = get_sdk()
    return _render(
        request,
        "partials/anime_episode_player.html",
        _anime_episodes_panel_context(sdk, anime_id),
    )


def _map_error(exc: Exception) -> tuple[int, str]:
    if isinstance(exc, ValidationError):
        return 400, str(exc)
    if isinstance(exc, NotFoundError):
        return 404, str(exc)
    if isinstance(exc, UnauthorizedError):
        return 401, str(exc)
    if isinstance(exc, AnimeManagerError):
        return 500, str(exc)
    return 500, "Unexpected error"


def _client_host(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return str(request.client.host).strip()
    return ""


def _host_in_allowlist(host: str, rules: list[str]) -> bool:
    if not host:
        return False
    for rule in rules:
        entry = str(rule or "").strip()
        if not entry:
            continue
        if host == entry:
            return True
        try:
            network = ipaddress.ip_network(entry, strict=False)
            if ipaddress.ip_address(host) in network:
                return True
        except ValueError:
            continue
    return False


def _is_client_allowed_for_streaming(request: Request, sdk: ClientSDK) -> bool:
    host = _client_host(request)
    if not host:
        return False
    if host in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return True

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False

    settings = {}
    try:
        settings = sdk.get_settings() or {}
    except Exception:  # noqa: BLE001
        settings = {}
    web_cfg = settings.get("web", {}) if isinstance(settings, dict) else {}
    allow_public = bool(web_cfg.get("player_allow_public", False))
    allowlist = web_cfg.get("player_allowlist", [])
    if isinstance(allowlist, str):
        allowlist = [allowlist]
    if isinstance(allowlist, list) and allowlist and _host_in_allowlist(host, allowlist):
        return True
    if allow_public:
        return True
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local)


def _next_ui_base_url() -> str:
    """Return configured Next.js UI origin or empty string when disabled."""
    return str(os.getenv("ANIMEMANAGER_NEXT_UI_URL", "")).strip().rstrip("/")


def _next_ui_redirect_for_request(request: Request) -> RedirectResponse | None:
    """Redirect `/ui/*` page requests to Next.js when cutover is enabled."""
    base = _next_ui_base_url()
    if not base:
        return None
    path = request.url.path or "/ui/library"
    if path.startswith("/ui"):
        path = path[3:] or "/"
    query = str(request.url.query or "").strip()
    target = f"{base}{path}"
    if query:
        target = f"{target}?{query}"
    return RedirectResponse(target, status_code=307)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/ui", include_in_schema=False)
def web_ui_root(request: Request) -> RedirectResponse:
    maybe = _next_ui_redirect_for_request(request)
    if maybe is not None:
        return maybe
    return _redirect_get("/ui/library")


@router.get("/ui/library", name="web_library")
def web_library(
    request: Request,
    filter: str = "DEFAULT",
    q: str | None = None,
    page: int = 1,
) -> HTMLResponse:
    maybe = _next_ui_redirect_for_request(request)
    if maybe is not None:
        return maybe
    sdk = get_sdk()
    page = max(1, _safe_int(page, 1))
    list_start = (page - 1) * PAGE_SIZE
    list_stop = list_start + PAGE_SIZE
    active_filter = (filter or "DEFAULT").upper()
    q_clean = (q or "").strip()

    items: list[dict[str, Any]] = []
    has_next = False
    flash = None
    # Search results land via the streaming WebSocket below (see
    # ``web_library_search_ws``) so the initial render is empty and
    # near-instant -- the slow API providers no longer block the
    # first paint. Validation errors are still surfaced server-side
    # so a search shorter than the minimum query length doesn't even
    # try to open a socket.
    streaming_search = False
    if q_clean:
        try:
            from domain.policies import normalize_search_query

            normalized = normalize_search_query(q_clean)
            if len(normalized) < 3:
                raise ValidationError(
                    "Search query must contain at least 3 characters."
                )
            streaming_search = True
        except ValidationError as exc:
            flash = _flash("error", str(exc))
        except Exception as exc:  # noqa: BLE001 - never crash the page
            _LOG.exception("library search validation failed")
            flash = _flash("error", f"Library load failed: {exc}")
    else:
        try:
            response = sdk.get_anime_list(
                filter_name=active_filter,
                user_id=DEFAULT_USER_ID,
                list_start=list_start,
                list_stop=list_stop,
                hide_rated=None,
            )
            items = list(response.get("items", []))
            has_next = bool(response.get("has_next"))
        except ValidationError as exc:
            flash = _flash("error", str(exc))
        except Exception as exc:  # noqa: BLE001 - surface to UI
            _LOG.exception("library load failed")
            flash = _flash("error", f"Library load failed: {exc}")

    def page_url(page_num: int) -> str:
        parts = [f"page={page_num}"]
        if active_filter and active_filter != "DEFAULT":
            parts.append(f"filter={active_filter}")
        if q_clean:
            parts.append(f"q={q_clean}")
        return "/ui/library?" + "&".join(parts)

    prev_url = page_url(page - 1) if page > 1 else None
    next_url = page_url(page + 1) if has_next else None

    page_title = "Search results" if q_clean else "Library"

    return _render(
        request,
        "library.html",
        {
            "items": items,
            "has_next": has_next,
            "page": page,
            "list_start": list_start,
            "prev_url": prev_url,
            "next_url": next_url,
            "filter": active_filter if active_filter != "DEFAULT" else None,
            "active_filter": active_filter,
            "active_nav": "library",
            "q": q_clean,
            "page_title": page_title,
            "flash": flash,
            "streaming_search": streaming_search,
            "search_ws_path": "/ui/library/ws" if streaming_search else "",
        },
    )


def _render_anime_card(request: Request | WebSocket, item: dict[str, Any]) -> str:
    """Render one ``partials/anime_card.html`` to a string.

    The library WebSocket pushes pre-rendered HTML fragments rather
    than JSON so the streamed cards stay perfectly visually consistent
    with the cards the synchronous (filter / non-search) render path
    produces -- no second template, no JS-side card builder to keep in
    sync.

    Jinja2Templates wires up ``url_for`` as a context-passed global
    that pulls the request out of the render context, so any object
    that exposes ``url_for(name, **params)`` (both ``Request`` and
    ``WebSocket`` do) works here.
    """
    template = templates.env.get_template("partials/anime_card.html")
    return template.render({"request": request, "item": item})


# Cap on streamed cards per WS session. Mirrors the page-size we used
# to materialize server-side so the user experience is identical, just
# progressively rendered.
_LIBRARY_STREAM_MAX_RESULTS: int = 50


@router.websocket("/ui/library/ws", name="web_library_search_ws")
async def web_library_search_ws(websocket: WebSocket) -> None:
    """Stream search results card-by-card for ``/ui/library?q=...``.

    Connection lifecycle:
    1. Client connects with ``?q=...`` in the query string.
    2. Server validates the query, then iterates the SDK's
       ``stream_search_anime`` generator on a worker thread (so the
       blocking provider HTTP calls don't pin the FastAPI event loop).
    3. Each yielded anime becomes a ``{"type": "card", "html": "..."}``
       message; the client appends ``html`` to the results grid.
    4. The server closes with ``{"type": "done", "count": N}`` once
       the generator is exhausted, or ``{"type": "error", ...}`` on
       failure.

    Errors during streaming are surfaced as a final ``error`` message
    instead of crashing the socket, so the UI can render a friendly
    fallback link to the synchronous page.
    """
    await websocket.accept()
    query = (websocket.query_params.get("q") or "").strip()
    limit = _safe_int(
        websocket.query_params.get("limit"), _LIBRARY_STREAM_MAX_RESULTS
    )
    if limit <= 0 or limit > 200:
        limit = _LIBRARY_STREAM_MAX_RESULTS

    if not query:
        await websocket.send_json(
            {"type": "error", "message": "Missing search query"}
        )
        await websocket.close()
        return

    sdk = get_sdk()
    try:
        from domain.policies import normalize_search_query  # noqa: WPS433

        normalized = normalize_search_query(query)
        if len(normalized) < 3:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "Search query must contain at least 3 characters.",
                }
            )
            await websocket.close()
            return
    except Exception:  # noqa: BLE001 - never block on validation
        pass

    # Bridge blocking ``stream_search_anime`` to the event loop without
    # ``run_coroutine_threadsafe(...).result()`` — that pattern deadlocks
    # during uvicorn shutdown (the loop stops servicing callbacks while the
    # worker thread blocks forever waiting for ``queue.put`` to complete).
    thread_q: queue.Queue = queue.Queue(maxsize=64)
    stop = threading.Event()
    _SENTINEL = object()

    def producer() -> None:
        try:
            for item in sdk.stream_search_anime(query, limit=limit):
                if stop.is_set():
                    break
                try:
                    thread_q.put(item, timeout=2.0)
                except queue.Full:
                    if stop.is_set():
                        break
        except Exception as exc:  # noqa: BLE001 - delivered to client
            if not stop.is_set():
                try:
                    thread_q.put({"__error__": str(exc)}, timeout=2.0)
                except queue.Full:
                    pass
        finally:
            for _ in range(4):
                try:
                    thread_q.put(_SENTINEL, timeout=0.5)
                    break
                except queue.Full:
                    try:
                        thread_q.get_nowait()
                    except queue.Empty:
                        pass

    producer_thread = threading.Thread(
        target=producer,
        name="AM-library-search-ws",
        daemon=True,
    )
    producer_thread.start()
    seen_ids: set[Any] = set()
    emitted = 0
    try:
        while True:
            try:
                item = await asyncio.to_thread(thread_q.get, True, 0.5)
            except queue.Empty:
                await asyncio.sleep(0)
                continue
            if item is _SENTINEL:
                break
            if isinstance(item, dict) and "__error__" in item:
                await websocket.send_json(
                    {"type": "error", "message": item["__error__"]}
                )
                continue
            anime_id = item.get("id") if isinstance(item, dict) else None
            if anime_id is not None and anime_id in seen_ids:
                continue
            if anime_id is not None:
                seen_ids.add(anime_id)
            try:
                html = _render_anime_card(websocket, item)
            except Exception as exc:  # noqa: BLE001 - log + skip card
                _LOG.warning("card render failed: %s", exc)
                continue
            try:
                await websocket.send_json(
                    {"type": "card", "id": anime_id, "html": html}
                )
            except WebSocketDisconnect:
                return
            emitted += 1
            if emitted >= limit:
                break
        try:
            await websocket.send_json({"type": "done", "count": emitted})
        except WebSocketDisconnect:
            return
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001 - last-ditch surfacing
        _LOG.exception("library search ws failed")
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:  # noqa: BLE001
            pass
    finally:
        stop.set()
        producer_thread.join(timeout=2.0)
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass


@router.get("/ui/anime/{anime_id}", name="web_anime_detail")
def web_anime_detail(request: Request, anime_id: int) -> HTMLResponse:
    maybe = _next_ui_redirect_for_request(request)
    if maybe is not None:
        return maybe
    sdk = get_sdk()
    try:
        anime = sdk.get_anime(anime_id)
    except NotFoundError:
        return _render(
            request,
            "error.html",
            {
                "status_code": 404,
                "status_text": "Not Found",
                "detail": f"No anime with id {anime_id}.",
                "active_nav": "library",
            },
            status_code=404,
        )

    _maybe_refresh_anime_metadata(sdk, anime_id)
    try:
        anime = sdk.get_anime(anime_id)
    except Exception:  # noqa: BLE001
        pass

    user_state: dict[str, Any] = {}
    terms: list[str] = []
    relations: list[dict[str, Any]] = []
    try:
        user_state = sdk.get_user_state(anime_id, DEFAULT_USER_ID) or {}
    except Exception:  # noqa: BLE001
        _LOG.debug("user_state lookup failed", exc_info=True)
    try:
        terms = list(sdk.get_search_terms(anime_id) or [])
    except Exception:  # noqa: BLE001
        _LOG.debug("search_terms lookup failed", exc_info=True)
    last_torrent_search_query: str | None = None
    try:
        last_torrent_search_query = sdk.get_last_torrent_search_query(anime_id)
    except Exception:  # noqa: BLE001
        _LOG.debug("last_torrent_search_query lookup failed", exc_info=True)
    try:
        relations = list(sdk.get_relations(anime_id) or [])
    except Exception:  # noqa: BLE001
        _LOG.debug("relations lookup failed", exc_info=True)
    relations = _enrich_relations_with_user_tag(sdk, relations)

    settings: dict[str, Any] = {}
    try:
        settings = sdk.get_settings() or {}
    except Exception:  # noqa: BLE001
        settings = {}

    trailer_embed: str | None = None
    alt_titles: list[str] = []
    detail_genre_tags: list[str] = []
    detail_airing_fields: list[dict[str, str]] = []
    detail_metadata_fields: list[dict[str, str]] = []
    computed_status = "UNKNOWN"
    computed_status_text = "Unknown"
    computed_status_color = ""
    schedule_lines: list[str] = []
    if isinstance(anime, dict):
        trailer_embed = _youtube_embed_url(anime.get("trailer"))
        computed_status, schedule_lines = _legacy_status_lines(anime)
        computed_status_text, computed_status_color = _status_theme_meta(
            settings, computed_status
        )
        detail_view = _build_anime_detail_view(
            anime,
            anime_id=anime_id,
            terms=terms,
            computed_status_text=computed_status_text,
            schedule_lines=schedule_lines,
        )
        alt_titles = detail_view["alt_titles"]
        detail_genre_tags = detail_view["genre_tags"]
        detail_airing_fields = detail_view["airing_fields"]
        detail_metadata_fields = detail_view["metadata_fields"]

    return _render(
        request,
        "anime_detail.html",
        {
            "anime": anime,
            "user_state": user_state,
            "terms": terms,
            "last_torrent_search_query": last_torrent_search_query,
            "relations": relations,
            "active_nav": "library",
            "page_title": anime.get("title") if isinstance(anime, dict) else None,
            "trailer_embed": trailer_embed,
            "alt_titles": alt_titles,
            "detail_genre_tags": detail_genre_tags,
            "detail_airing_fields": detail_airing_fields,
            "detail_metadata_fields": detail_metadata_fields,
            "computed_status": computed_status,
            "computed_status_text": computed_status_text,
            "computed_status_color": computed_status_color,
        },
    )


@router.get("/ui/anime/{anime_id}/characters", name="web_anime_characters")
def web_anime_characters(request: Request, anime_id: int) -> HTMLResponse:
    """Cast list from ``characterRelations`` + ``characters`` tables."""
    maybe = _next_ui_redirect_for_request(request)
    if maybe is not None:
        return maybe
    sdk = get_sdk()
    try:
        anime = sdk.get_anime(anime_id)
    except NotFoundError:
        return _render(
            request,
            "error.html",
            {
                "status_code": 404,
                "status_text": "Not Found",
                "detail": f"No anime with id {anime_id}.",
                "active_nav": "library",
            },
            status_code=404,
        )

    characters: list[dict[str, Any]] = []
    try:
        characters = list(sdk.list_anime_characters(anime_id) or [])
    except Exception:  # noqa: BLE001
        _LOG.debug("list_anime_characters failed", exc_info=True)

    page_title = None
    if isinstance(anime, dict):
        title = anime.get("title")
        if title:
            page_title = f"Characters · {title}"

    return _render(
        request,
        "anime_characters.html",
        {
            "anime": anime,
            "characters": characters,
            "active_nav": "library",
            "page_title": page_title,
        },
    )


@router.get("/ui/anime/{anime_id}/episodes-panel", name="web_anime_episodes_panel")
def web_anime_episodes_panel(request: Request, anime_id: int) -> HTMLResponse:
    """HTMX lazy fragment: episode files + torrent rows (heavy ffprobe work)."""
    sdk = get_sdk()
    try:
        sdk.get_anime(anime_id)
    except NotFoundError:
        return HTMLResponse(
            '<p class="meta">Anime not found.</p>',
            status_code=404,
        )
    return _render(
        request,
        "partials/anime_episode_player.html",
        _anime_episodes_panel_context(sdk, anime_id),
    )


@router.get("/ui/anime/{anime_id}/watch", name="web_anime_watch")
def web_anime_watch(
    request: Request,
    anime_id: int,
    file_id: str = "",
) -> HTMLResponse:
    maybe = _next_ui_redirect_for_request(request)
    if maybe is not None:
        return maybe
    sdk = get_sdk()
    try:
        anime = sdk.get_anime(anime_id)
    except NotFoundError:
        return _render(
            request,
            "error.html",
            {
                "status_code": 404,
                "status_text": "Not Found",
                "detail": f"No anime with id {anime_id}.",
                "active_nav": "library",
            },
            status_code=404,
        )

    try:
        episode_files = list(
            sdk.list_episode_files(anime_id, user_id=DEFAULT_USER_ID) or []
        )
    except Exception:  # noqa: BLE001
        episode_files = []

    selected_file_id = str(file_id or "").strip()
    if not selected_file_id and episode_files:
        selected_file_id = str(episode_files[0].get("file_id") or "")
    selected_title = ""
    selected_audio_tracks: list[dict[str, Any]] = []
    selected_subtitle_tracks: list[dict[str, Any]] = []
    for item in episode_files:
        if str(item.get("file_id") or "") == selected_file_id:
            selected_title = str(item.get("title") or "")
            selected_audio_tracks = list(item.get("audio_tracks") or [])
            selected_subtitle_tracks = list(item.get("subtitle_tracks") or [])
            break

    track_map: dict[str, dict[str, list[dict[str, Any]]]] = {}
    episode_resume_map: dict[str, float] = {}
    for item in episode_files:
        fid = str(item.get("file_id") or "")
        if not fid:
            continue
        track_map[fid] = {
            "audio": list(item.get("audio_tracks") or []),
            "subtitles": list(item.get("subtitle_tracks") or []),
        }
        pos_raw = item.get("position_seconds")
        try:
            pos = float(pos_raw) if pos_raw is not None else 0.0
        except (TypeError, ValueError):
            pos = 0.0
        if pos >= 10.0:
            episode_resume_map[fid] = pos

    return _render(
        request,
        "watch_episode.html",
        {
            "anime": anime,
            "episode_files": episode_files,
            "selected_file_id": selected_file_id,
            "selected_file_title": selected_title,
            "selected_audio_tracks": selected_audio_tracks,
            "selected_subtitle_tracks": selected_subtitle_tracks,
            "track_map": track_map,
            "episode_resume_map": episode_resume_map,
            "active_nav": "library",
            "page_title": f"Watch · {anime.get('title')}" if isinstance(anime, dict) else "Watch",
        },
    )


@router.post("/ui/anime/{anime_id}/like", name="web_action_like")
def web_action_like(
    request: Request,
    anime_id: int,
    liked: str = Form("true"),
) -> Response:
    sdk = get_sdk()
    truthy = liked.strip().lower() in {"1", "true", "yes", "on"}
    try:
        sdk.set_like(anime_id, user_id=DEFAULT_USER_ID, liked=truthy)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("set_like failed: %s", exc)
    return _anime_actions_response(request, anime_id)


@router.post("/ui/anime/{anime_id}/tag", name="web_action_tag")
def web_action_tag(
    request: Request,
    anime_id: int,
    tag: str = Form("NONE"),
) -> Response:
    sdk = get_sdk()
    try:
        sdk.set_tag(anime_id, tag=tag.upper(), user_id=DEFAULT_USER_ID)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("set_tag failed: %s", exc)
    return _anime_actions_response(request, anime_id)


@router.post("/ui/anime/{anime_id}/seen", name="web_action_seen")
def web_action_seen(
    request: Request,
    anime_id: int,
    file_name: str = Form(""),
) -> Response:
    sdk = get_sdk()
    try:
        sdk.mark_seen(anime_id, file_name=file_name, user_id=DEFAULT_USER_ID)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("mark_seen failed: %s", exc)
    return _anime_actions_response(request, anime_id)


@router.post("/ui/anime/{anime_id}/refresh", name="web_action_refresh_anime")
def web_action_refresh_anime(request: Request, anime_id: int) -> Response:
    sdk = get_sdk()
    try:
        getattr(sdk, "refresh_anime_metadata", lambda _id: None)(anime_id)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("refresh_anime_metadata failed: %s", exc)
    return _redirect(f"/ui/anime/{anime_id}")


@router.post("/ui/anime/{anime_id}/redownload", name="web_action_redownload")
def web_action_redownload(request: Request, anime_id: int) -> Response:
    sdk = get_sdk()
    try:
        getattr(sdk, "redownload", lambda _id: 0)(anime_id)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("redownload failed: %s", exc)
    return _redirect(f"/ui/anime/{anime_id}")


@router.post("/ui/anime/{anime_id}/delete-seen", name="web_action_delete_seen_episodes")
def web_action_delete_seen_episodes(request: Request, anime_id: int) -> Response:
    sdk = get_sdk()
    try:
        getattr(sdk, "delete_seen_episodes", lambda _id, _uid: 0)(
            anime_id, DEFAULT_USER_ID
        )
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("delete_seen_episodes failed: %s", exc)
    return _redirect(f"/ui/anime/{anime_id}")


@router.post("/ui/anime/{anime_id}/delete-files", name="web_action_delete_all_files")
def web_action_delete_all_files(request: Request, anime_id: int) -> Response:
    sdk = get_sdk()
    try:
        getattr(sdk, "delete_all_files", lambda _id, _uid: 0)(anime_id, DEFAULT_USER_ID)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("delete_all_files failed: %s", exc)
    return _redirect(f"/ui/anime/{anime_id}")


@router.post("/ui/anime/{anime_id}/remove", name="web_action_remove_anime")
def web_action_remove_anime(request: Request, anime_id: int) -> Response:
    sdk = get_sdk()
    try:
        getattr(sdk, "delete_anime", lambda _id: False)(anime_id)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("delete_anime failed: %s", exc)
    return _redirect("/ui/library")


@router.post("/ui/anime/{anime_id}/episode-progress", name="web_action_episode_progress")
def web_action_episode_progress(
    request: Request,
    anime_id: int,
    file_id: str = Form(""),
    status: str = Form("UNSEEN"),
    position_seconds: str = Form(""),
) -> Response:
    sdk = get_sdk()
    pos: float | None = None
    raw_pos = str(position_seconds or "").strip()
    if raw_pos:
        try:
            pos = float(raw_pos)
        except ValueError:
            pos = None
    try:
        sdk.set_episode_progress(
            anime_id,
            user_id=DEFAULT_USER_ID,
            file_id=file_id,
            status=status.strip().upper() or "UNSEEN",
            position_seconds=pos,
        )
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("set_episode_progress failed: %s", exc)
    return _episode_player_response(request, anime_id)


@router.post("/ui/anime/{anime_id}/episode-delete", name="web_action_episode_delete")
def web_action_episode_delete(
    request: Request,
    anime_id: int,
    file_id: str = Form(""),
) -> Response:
    sdk = get_sdk()
    try:
        sdk.delete_episode_file(anime_id, file_id=file_id, user_id=DEFAULT_USER_ID)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("delete_episode_file failed: %s", exc)
    return _episode_player_response(request, anime_id)


@router.post("/ui/anime/{anime_id}/episode-mark-seen", name="web_action_episode_mark_seen")
def web_action_episode_mark_seen(
    request: Request,
    anime_id: int,
    file_id: str = Form(""),
) -> Response:
    sdk = get_sdk()
    fid = str(file_id or "").strip()
    if fid:
        try:
            sdk.set_episode_progress(
                anime_id,
                user_id=DEFAULT_USER_ID,
                file_id=fid,
                status="SEEN",
                position_seconds=None,
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("episode mark seen failed: %s", exc)
    return _episode_player_response(request, anime_id)


@router.post("/ui/anime/{anime_id}/episode-mark-unseen", name="web_action_episode_mark_unseen")
def web_action_episode_mark_unseen(
    request: Request,
    anime_id: int,
    file_id: str = Form(""),
) -> Response:
    sdk = get_sdk()
    fid = str(file_id or "").strip()
    if fid:
        try:
            sdk.set_episode_progress(
                anime_id,
                user_id=DEFAULT_USER_ID,
                file_id=fid,
                status="UNSEEN",
                position_seconds=0.0,
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("episode mark unseen failed: %s", exc)
    return _episode_player_response(request, anime_id)


@router.post("/ui/anime/{anime_id}/episode-redownload", name="web_action_episode_redownload")
def web_action_episode_redownload(
    request: Request,
    anime_id: int,
    file_id: str = Form(""),
) -> Response:
    sdk = get_sdk()
    fid = str(file_id or "").strip()
    if fid:
        try:
            getattr(sdk, "redownload_episode", lambda *_a, **_k: False)(
                anime_id, fid, DEFAULT_USER_ID
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("episode redownload failed: %s", exc)
    return _episode_player_response(request, anime_id)


@router.post("/ui/anime/{anime_id}/terms", name="web_action_add_term")
def web_action_add_term(
    request: Request,
    anime_id: int,
    term: str = Form(""),
) -> HTMLResponse:
    sdk = get_sdk()
    try:
        sdk.add_search_term(anime_id, term)
    except ValidationError as exc:
        _LOG.info("add_search_term validation: %s", exc)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("add_search_term failed: %s", exc)
    return _render(
        request,
        "partials/search_terms.html",
        {
            "anime": {"id": anime_id},
            "terms": list(sdk.get_search_terms(anime_id) or []),
        },
    )


@router.delete("/ui/anime/{anime_id}/terms", name="web_action_remove_term")
def web_action_remove_term(
    request: Request,
    anime_id: int,
    term: str = "",
) -> HTMLResponse:
    sdk = get_sdk()
    try:
        sdk.remove_search_term(anime_id, term)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("remove_search_term failed: %s", exc)
    return _render(
        request,
        "partials/search_terms.html",
        {
            "anime": {"id": anime_id},
            "terms": list(sdk.get_search_terms(anime_id) or []),
        },
    )


# ---------------------------------------------------------------------------
# Media playback
# ---------------------------------------------------------------------------


@router.post("/ui/anime/{anime_id}/play", name="web_action_play")
def web_action_play(
    request: Request,
    anime_id: int,
    file_id: str = Form(""),
    audio_track: str = Form(""),
    subtitle_track: str = Form(""),
    start_time: str = Form(""),
) -> JSONResponse:
    sdk = get_sdk()
    if not _is_client_allowed_for_streaming(request, sdk):
        raise HTTPException(status_code=403, detail="Playback is limited to trusted LAN clients.")
    audio_idx: int | None = None
    subtitle_idx: int | None = None
    start_time_seconds: float | None = None
    if str(audio_track).strip() != "":
        try:
            audio_idx = max(0, int(audio_track))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid audio track selection.")
    if str(subtitle_track).strip() != "":
        try:
            subtitle_idx = max(0, int(subtitle_track))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid subtitle track selection.")
    if str(start_time).strip() != "":
        try:
            parsed_start = float(start_time)
        except ValueError:
            # Don't fail the whole request over a malformed hint —
            # just ignore it and start from the beginning.
            parsed_start = 0.0
        if parsed_start > 0 and parsed_start == parsed_start:  # NaN guard
            start_time_seconds = parsed_start
    _LOG.info(
        "play_request anime_id=%s file_id=%s audio_track=%s subtitle_track=%s start_time=%s",
        anime_id,
        file_id.strip(),
        audio_idx,
        subtitle_idx,
        start_time_seconds,
    )
    try:
        session = sdk.create_playback_session(
            anime_id,
            file_id=file_id.strip(),
            client_host=_client_host(request),
            ttl_seconds=PLAYBACK_SESSION_TTL_SECONDS,
            audio_track=audio_idx,
            subtitle_track=subtitle_idx,
            start_time_seconds=start_time_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        code, msg = _map_error(exc)
        raise HTTPException(status_code=code, detail=msg) from exc

    session_id = session.get("session_id")
    token = session.get("token")
    manifest_url = f"/ui/stream/{session_id}/index.m3u8?token={token}"
    subtitle_tracks_payload: list[dict[str, Any]] = []
    for track in session.get("subtitle_tracks") or []:
        if not isinstance(track, dict):
            continue
        try:
            track_id = max(0, int(track.get("id")))
        except (TypeError, ValueError):
            continue
        item: dict[str, Any] = {
            "id": track_id,
            "label": str(track.get("label") or f"Subtitle {track_id}"),
            "url": f"/ui/stream/{session_id}/subtitle_{track_id:03d}.vtt?token={token}",
        }
        codec = str(track.get("codec") or "").strip()
        if codec:
            item["codec"] = codec
        ass_fn = str(track.get("ass_filename") or "").strip()
        if ass_fn:
            item["ass_url"] = f"/ui/stream/{session_id}/{ass_fn}?token={token}"
        subtitle_tracks_payload.append(item)
    return JSONResponse(
        {
            "session_id": session_id,
            "token": token,
            "manifest_url": manifest_url,
            "heartbeat_url": f"/ui/stream/{session_id}/heartbeat",
            "stop_url": f"/ui/stream/{session_id}/stop",
            "expires_at": session.get("expires_at"),
            "file_title": session.get("file_title"),
            "subtitle_requested": subtitle_idx,
            "subtitle_applied": session.get("subtitle_track"),
            "subtitle_tracks": subtitle_tracks_payload,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/ui/stream/{session_id}/index.m3u8", name="web_stream_manifest")
def web_stream_manifest(
    request: Request,
    session_id: str,
    token: str,
) -> Response:
    sdk = get_sdk()
    if not _is_client_allowed_for_streaming(request, sdk):
        raise HTTPException(status_code=403, detail="Playback is limited to trusted LAN clients.")
    try:
        _session, path = sdk.resolve_playback_media_path(
            session_id=session_id,
            token=token,
            segment_name=None,
        )
    except Exception as exc:  # noqa: BLE001
        code, msg = _map_error(exc)
        raise HTTPException(status_code=code, detail=msg) from exc
    return FileResponse(
        path=path,
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/ui/stream/{session_id}/{segment_name}", name="web_stream_segment")
def web_stream_segment(
    request: Request,
    session_id: str,
    segment_name: str,
    token: str = "",
) -> Response:
    sdk = get_sdk()
    if not _is_client_allowed_for_streaming(request, sdk):
        raise HTTPException(status_code=403, detail="Playback is limited to trusted LAN clients.")
    try:
        _session, path = sdk.resolve_playback_media_path(
            session_id=session_id,
            token=token,
            segment_name=segment_name,
        )
    except Exception as exc:  # noqa: BLE001
        code, msg = _map_error(exc)
        raise HTTPException(status_code=code, detail=msg) from exc
    media_type = "video/mp2t"
    if segment_name.endswith(".m4s"):
        media_type = "video/iso.segment"
    elif segment_name.endswith(".mp4"):
        media_type = "video/mp4"
    elif segment_name.endswith(".vtt"):
        media_type = "text/vtt"
    elif segment_name.endswith(".ass"):
        media_type = "text/x-ssa"
    return FileResponse(
        path=path,
        media_type=media_type,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/ui/stream/{session_id}/heartbeat", name="web_stream_heartbeat")
def web_stream_heartbeat(request: Request, session_id: str) -> JSONResponse:
    sdk = get_sdk()
    if not _is_client_allowed_for_streaming(request, sdk):
        raise HTTPException(status_code=403, detail="Playback is limited to trusted LAN clients.")
    try:
        payload = sdk.heartbeat_playback_session(session_id)
    except Exception as exc:  # noqa: BLE001
        code, msg = _map_error(exc)
        raise HTTPException(status_code=code, detail=msg) from exc
    return JSONResponse(
        {
            "session_id": payload.get("session_id"),
            "token": payload.get("token"),
            "expires_at": payload.get("expires_at"),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/ui/stream/{session_id}/stop", name="web_stream_stop")
def web_stream_stop(request: Request, session_id: str) -> JSONResponse:
    sdk = get_sdk()
    if not _is_client_allowed_for_streaming(request, sdk):
        raise HTTPException(status_code=403, detail="Playback is limited to trusted LAN clients.")
    try:
        sdk.stop_playback_session(session_id)
    except Exception as exc:  # noqa: BLE001
        code, msg = _map_error(exc)
        raise HTTPException(status_code=code, detail=msg) from exc
    return JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

# Canonical bucket order for the downloads UI. ``other`` is folded
# under ``active`` on the frontend because the rare states that land
# there (e.g. "queued") still represent in-flight transfers from the
# user's point of view.
_DOWNLOAD_BUCKETS: tuple[str, ...] = (
    "active",
    "seeding",
    "completed",
    "error",
    "other",
)


def _format_speed(num: Any) -> str | None:
    """Pretty-print a bytes-per-second number.

    Returns ``None`` when ``num`` is missing or non-positive so the
    template can skip the row instead of rendering a misleading
    ``0 B/s`` for paused torrents.
    """
    try:
        value = float(num)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    units = ("B/s", "KB/s", "MB/s", "GB/s")
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    return f"{value:.1f} {units[idx]}"


def _format_eta(num: Any) -> str | None:
    """Render an ETA expressed in seconds as ``Hh Mm`` / ``Mm Ss`` etc."""
    try:
        value = int(num)
    except (TypeError, ValueError):
        return None
    if value <= 0 or value >= 60 * 60 * 24 * 30:
        return None
    if value < 60:
        return f"{value}s"
    minutes, seconds = divmod(value, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s" if seconds else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h" if hours else f"{days}d"


def _normalize_overview_row(row: Any) -> dict[str, Any]:
    """Coerce one overview row into a stable, JSON-friendly dict.

    The downloads UI and the WebSocket payload both consume this shape
    so the template never has to special-case missing fields. We also
    pre-compute the human-readable speed / size / eta strings so the
    JS rendering path doesn't have to mirror the Jinja filters.
    """
    if hasattr(row, "__dataclass_fields__"):
        data = {f: getattr(row, f) for f in row.__dataclass_fields__}
    elif isinstance(row, dict):
        data = dict(row)
    else:
        data = {
            "hash": getattr(row, "hash", None),
            "name": getattr(row, "name", None),
            "anime_id": getattr(row, "anime_id", None),
        }

    # ``progress`` may arrive either as a 0..1 fraction (the canonical
    # libtorrent shape) or as an already-percentage value such as 67.5
    # (some adapters emit human-friendly numbers). We accept both and
    # normalise to a 0..100 float for the UI.
    progress = data.get("progress")
    if isinstance(progress, (int, float)):
        raw = float(progress)
        if raw <= 1.0:
            progress_pct = round(max(0.0, raw) * 100, 1)
        else:
            progress_pct = round(min(100.0, raw), 1)
    else:
        progress_pct = None

    name = data.get("name") or data.get("title")
    if not name and data.get("anime_id"):
        name = f"Anime #{data['anime_id']}"
    if not name:
        name = data.get("hash") or "Unknown torrent"

    return {
        "hash": data.get("hash"),
        "name": str(name),
        "anime_id": data.get("anime_id"),
        "anime_title": data.get("anime_title"),
        "state": data.get("state"),
        "category": data.get("category"),
        "progress": progress,
        "progress_pct": progress_pct,
        "size": data.get("size"),
        "size_human": _humanize_size(data.get("size")),
        "downloaded": data.get("downloaded"),
        "downloaded_human": _humanize_size(data.get("downloaded")),
        "dl_speed": data.get("dl_speed"),
        "dl_speed_human": _format_speed(data.get("dl_speed")),
        "up_speed": data.get("up_speed"),
        "up_speed_human": _format_speed(data.get("up_speed")),
        "eta": data.get("eta"),
        "eta_human": _format_eta(data.get("eta")),
        "path": data.get("path"),
    }


def _load_torrents_overview(sdk: ClientSDK) -> dict[str, list[dict[str, Any]]]:
    """Pull the overview from the SDK and normalise every row.

    Older SDKs / test doubles may not implement
    :meth:`ClientSDK.get_torrents_overview`; in that case we degrade
    to a single ``active`` bucket fed by :meth:`get_active_downloads`
    so the page keeps rendering the in-flight torrents (and the WS
    push loop keeps emitting non-empty snapshots).
    Empty buckets are kept in the result so the template / JS can
    always iterate the same keys without ``in`` checks.
    """
    raw: dict[str, Any] | None = None
    getter = getattr(sdk, "get_torrents_overview", None)
    if callable(getter):
        try:
            result = getter()
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("torrents overview fetch failed: %s", exc)
            result = None
        if isinstance(result, dict):
            raw = result
    if raw is None:
        try:
            active = list(sdk.get_active_downloads() or [])
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("active downloads fetch failed: %s", exc)
            active = []
        raw = {"active": active}
    out: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in _DOWNLOAD_BUCKETS}
    for bucket in _DOWNLOAD_BUCKETS:
        for row in raw.get(bucket) or []:
            out[bucket].append(_normalize_overview_row(row))
    return out


def _overview_counts(overview: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    return {bucket: len(overview.get(bucket) or []) for bucket in _DOWNLOAD_BUCKETS}


@router.get("/ui/downloads", name="web_downloads")
def web_downloads(request: Request) -> HTMLResponse:
    maybe = _next_ui_redirect_for_request(request)
    if maybe is not None:
        return maybe
    sdk = get_sdk()
    overview = _load_torrents_overview(sdk)
    return _render(
        request,
        "downloads.html",
        {
            "overview": overview,
            "counts": _overview_counts(overview),
            "active_nav": "downloads",
        },
    )


@router.get("/ui/downloads/panel", name="web_downloads_panel")
def web_downloads_panel(request: Request) -> HTMLResponse:
    """No-JS / HTMX fallback that ships the same panel as the WS view.

    The route is still wired so users behind proxies that disallow
    WebSocket upgrades keep a working polling path; ``downloads.html``
    only swaps to ``hx-trigger`` when the JS client decides the WS
    connection is unrecoverable.
    """
    sdk = get_sdk()
    overview = _load_torrents_overview(sdk)
    return _render(
        request,
        "partials/downloads_panel.html",
        {
            "overview": overview,
            "counts": _overview_counts(overview),
        },
    )


@router.get(
    "/ui/downloads/overview.json",
    name="web_downloads_overview_json",
    response_class=JSONResponse,
)
def web_downloads_overview_json() -> JSONResponse:
    """JSON snapshot used by the WebSocket fallback and external tools."""
    sdk = get_sdk()
    overview = _load_torrents_overview(sdk)
    return JSONResponse(
        {"overview": overview, "counts": _overview_counts(overview)},
        headers={"Cache-Control": "no-store"},
    )


# Push cadence for the downloads WebSocket. Picked to feel "live" on
# the UI without hammering the torrent client when several tabs are
# subscribed at once -- the underlying SDK call already throttles to
# ~0.5s, this just bounds how often we wake up to poll.
_DOWNLOADS_WS_INTERVAL_S: float = 2.0


@router.websocket("/ui/downloads/ws", name="web_downloads_ws")
async def web_downloads_ws(websocket: WebSocket) -> None:
    """Live overview stream for the downloads page.

    Pushes ``{"overview": {...}, "counts": {...}, "ts": <epoch>}``
    JSON messages every ``_DOWNLOADS_WS_INTERVAL_S`` seconds plus an
    immediate first snapshot on connect. The peer can also send
    ``{"type": "refresh"}`` to request an out-of-band update (used by
    the UI after the user clicks "Refresh" or starts/cancels a
    download). Any other inbound message is ignored.

    The blocking SDK call is funnelled through :func:`asyncio.to_thread`
    so a slow torrent client doesn't stall the FastAPI event loop and
    starve other clients.
    """
    await websocket.accept()
    sdk = get_sdk()

    async def send_snapshot() -> None:
        try:
            overview = await asyncio.to_thread(_load_torrents_overview, sdk)
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("downloads ws snapshot failed: %s", exc)
            overview = {bucket: [] for bucket in _DOWNLOAD_BUCKETS}
        import time as _time

        await websocket.send_json(
            {
                "overview": overview,
                "counts": _overview_counts(overview),
                "ts": _time.time(),
            }
        )

    async def reader() -> None:
        """Consume inbound frames so we notice client-side refreshes / pings."""
        try:
            while True:
                message = await websocket.receive_text()
                try:
                    payload = json.loads(message) if message else {}
                except json.JSONDecodeError:
                    payload = {}
                if isinstance(payload, dict) and payload.get("type") == "refresh":
                    await send_snapshot()
        except WebSocketDisconnect:
            return
        except Exception:  # noqa: BLE001
            _LOG.debug("downloads ws reader closed", exc_info=True)
            return

    reader_task = asyncio.create_task(reader())
    try:
        await send_snapshot()
        while True:
            await asyncio.sleep(_DOWNLOADS_WS_INTERVAL_S)
            if reader_task.done():
                # Peer hung up -- bail before issuing another send.
                break
            await send_snapshot()
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("downloads ws closed: %s", exc, exc_info=True)
    finally:
        reader_task.cancel()
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass


@router.post("/ui/anime/{anime_id}/download", name="web_action_start_download")
def web_action_start_download(
    request: Request,
    anime_id: int,
    url: str | None = Form(None),
    hash_value: str | None = Form(None),
) -> RedirectResponse:
    sdk = get_sdk()
    try:
        sdk.start_download(
            anime_id,
            url=url,
            hash_value=hash_value,
            user_id=DEFAULT_USER_ID,
        )
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("start_download failed: %s", exc)
    return _redirect(_post_download_redirect_path(request, anime_id))


@router.post("/ui/anime/{anime_id}/cancel", name="web_action_cancel")
def web_action_cancel(request: Request, anime_id: int) -> RedirectResponse:
    sdk = get_sdk()
    try:
        sdk.cancel_download(anime_id)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("cancel_download failed: %s", exc)
    return _redirect(_post_download_redirect_path(request, anime_id))


# ---------------------------------------------------------------------------
# Torrent search
# ---------------------------------------------------------------------------


@router.get("/ui/torrents", name="web_torrents")
def web_torrents(
    request: Request,
    term: str | None = None,
    anime_id: int | None = None,
) -> HTMLResponse:
    maybe = _next_ui_redirect_for_request(request)
    if maybe is not None:
        return maybe
    sdk = get_sdk()
    results: list[dict[str, Any]] = []
    term_clean = (term or "").strip()
    if term_clean:
        terms = [t.strip() for t in term_clean.split(",") if t.strip()]
        try:
            raw = sdk.search_torrents(terms, profile="interactive", limit=TORRENT_RESULT_LIMIT)
            results = _normalize_torrents(raw)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("torrent search failed: %s", exc)
    return _render(
        request,
        "torrents.html",
        {
            "results": results,
            "term": term_clean,
            "anime_id": anime_id,
            "active_nav": "torrents",
        },
    )


def _resolve_anime_search_term(
    sdk: ClientSDK, anime_id: int, raw_term: str | None
) -> tuple[str, str]:
    """Return ``(term_clean, torrent_term_source)`` for the inline torrent search.

    Empty / whitespace-only ``raw_term`` falls back in order to: the last
    successful torrent query for this anime; saved search terms
    (``title_synonyms`` rows); then the main title plus alternate titles.
    ``torrent_term_source`` is ``explicit``, ``memory``, ``saved``,
    ``title``, or ``none``.
    """
    term_clean = (raw_term or "").strip()
    if term_clean:
        return term_clean, "explicit"
    try:
        last = sdk.get_last_torrent_search_query(anime_id)
    except Exception:  # noqa: BLE001
        last = None
    if last and str(last).strip():
        return str(last).strip(), "memory"
    try:
        saved = list(sdk.get_search_terms(anime_id) or [])
    except Exception:  # noqa: BLE001
        saved = []
    if saved:
        return ", ".join(saved), "saved"
    try:
        anime = sdk.get_anime(anime_id)
    except Exception:  # noqa: BLE001
        return "", "none"
    if isinstance(anime, dict):
        variants = title_variants_for_torrent_search(anime)
        if variants:
            return ", ".join(variants), "title"
    return "", "none"


@router.get("/ui/anime/{anime_id}/torrents", name="web_anime_torrent_search")
def web_anime_torrent_search(
    request: Request,
    anime_id: int,
    term: str | None = None,
) -> HTMLResponse:
    """Inline (HTMX) torrent search scoped to an anime.

    Returns the ``partials/anime_torrent_results.html`` skeleton so the
    anime detail page can swap it in-place. The skeleton wires a live
    SSE connection to :func:`web_anime_torrent_stream`; rows are then
    streamed after the search completes, ordered by seed count.

    When ``term`` is empty we fall back to the anime's saved search
    terms (if any) and finally to its title and alternate titles.
    """
    sdk = get_sdk()
    term_clean, torrent_term_source = _resolve_anime_search_term(sdk, anime_id, term)
    return _render(
        request,
        "partials/anime_torrent_results.html",
        {
            "term": term_clean,
            "torrent_term_source": torrent_term_source,
            "anime_id": anime_id,
            "search_error": None,
            "stream_limit": TORRENT_RESULT_LIMIT,
        },
    )


@router.get("/ui/anime/{anime_id}/torrents/stream", name="web_anime_torrent_stream")
def web_anime_torrent_stream(
    request: Request,
    anime_id: int,
    term: str | None = None,
) -> StreamingResponse:
    """Server-Sent Events feed for the inline torrent search.

    Pushes one ``event: row`` per result (a ready-to-render HTML
    ``<tr>``) as soon as the underlying engines emit it, then a final
    ``event: end`` once the search completes (or a single
    ``event: error`` if validation fails). The client applies the
    top-k-by-seeds cap in real time while rows stream in.
    """
    sdk = get_sdk()
    term_clean, _torrent_term_source = _resolve_anime_search_term(sdk, anime_id, term)

    def event_stream() -> Iterable[bytes]:
        if not term_clean:
            yield _sse_event(
                "error",
                "Provide a search term, save one above, or set an anime title.",
            )
            yield _sse_event("end", "")
            return

        terms = [t.strip() for t in term_clean.split(",") if t.strip()]
        # Warm signal -- lets the JS show "Searching…" before the first
        # engine returns. SSE comments are ignored by the client but
        # flush the connection.
        yield b": stream-open\n\n"

        emitted = 0
        stream_failed = False
        try:
            for raw in sdk.stream_torrents(
                terms, profile="interactive", limit=TORRENT_RESULT_LIMIT
            ):
                if emitted >= TORRENT_RESULT_LIMIT:
                    break
                row = _normalize_torrents([raw])
                if not row:
                    continue
                html = templates.get_template(
                    "partials/anime_torrent_row.html"
                ).render({"row": row[0], "anime_id": anime_id, "request": request})
                yield _sse_event("row", html)
                emitted += 1
        except ValidationError as exc:
            stream_failed = True
            yield _sse_event("error", str(exc))
        except Exception as exc:  # noqa: BLE001
            stream_failed = True
            _LOG.warning("inline torrent stream failed: %s", exc)
            yield _sse_event(
                "error",
                "Torrent search failed; check the search engines configuration.",
            )
        if not stream_failed:
            try:
                sdk.set_last_torrent_search_query(anime_id, term_clean)
            except Exception:  # noqa: BLE001
                _LOG.debug("persist last torrent query failed", exc_info=True)
        yield _sse_event("end", str(emitted))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def _safe_browse_dir(raw: str) -> Path:
    """Resolve a user-supplied path to a readable directory.

    Empty / invalid input falls back to the user's home folder. Files
    are resolved to their containing directory so the modal still
    shows something useful when the field is pointed at a target
    file."""
    candidate: Path
    if not raw or not raw.strip():
        candidate = Path.home()
    else:
        try:
            candidate = Path(raw).expanduser()
        except (TypeError, ValueError):
            candidate = Path.home()
    try:
        candidate = candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        candidate = Path.home()
    if candidate.exists() and candidate.is_file():
        candidate = candidate.parent
    if not candidate.exists() or not candidate.is_dir():
        candidate = Path.home()
    return candidate


@router.get("/ui/browse", name="web_browse")
def web_browse(request: Request, path: str = "") -> HTMLResponse:
    """Render a directory listing partial for the file-browser modal.

    Used by path-shaped settings fields (cache, iconPath, dbPath,
    dataPath, …). Read-only -- the modal only navigates the local
    filesystem and writes the chosen path back into the originating
    input via a small JS bridge.
    """
    target = _safe_browse_dir(path)
    entries: list[dict[str, Any]] = []
    error: str | None = None
    try:
        raw_entries = list(target.iterdir())
    except (PermissionError, OSError) as exc:
        _LOG.info("web_browse: cannot list %s: %s", target, exc)
        raw_entries = []
        error = f"Cannot list {target}: {exc}"

    raw_entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
    for entry in raw_entries:
        try:
            is_dir = entry.is_dir()
            size = entry.stat().st_size if not is_dir else None
        except OSError:
            continue
        entries.append(
            {
                "name": entry.name,
                "path": str(entry),
                "is_dir": is_dir,
                "size_human": _humanize_size(size) if size is not None else None,
            }
        )

    parent = target.parent
    parent_path = str(parent) if parent != target else None
    return _render(
        request,
        "partials/file_browser.html",
        {
            "current_path": str(target),
            "parent_path": parent_path,
            "entries": entries,
            "error": error,
        },
    )


def _settings_context(
    current: dict[str, Any],
    *,
    raw_settings_json: str = "",
) -> dict[str, Any]:
    return {
        "sections": settings_form.build_sections(current),
        "current_settings_json": json.dumps(current, indent=2, sort_keys=True),
        "raw_settings_json": raw_settings_json,
        "active_nav": "settings",
    }


@router.get("/ui/settings", name="web_settings")
def web_settings(request: Request) -> HTMLResponse:
    maybe = _next_ui_redirect_for_request(request)
    if maybe is not None:
        return maybe
    sdk = get_sdk()
    try:
        current = sdk.get_settings() or {}
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("get_settings failed: %s", exc)
        current = {"error": str(exc)}
    # Refresh the buffer's category filter on every settings-related
    # request so a settings.json edit (made through any client) takes
    # effect on the live log viewer without an app restart.
    try:
        log_buffer.sync_from_settings(current)
    except Exception:  # noqa: BLE001 - best effort
        _LOG.debug("log_buffer sync_from_settings failed", exc_info=True)
    return _render(request, "settings.html", _settings_context(current))


@router.post("/ui/settings", name="web_settings_save")
async def web_settings_save(request: Request) -> HTMLResponse:
    sdk = get_sdk()
    form = await request.form()
    raw_json = (form.get("settings_json") or "").strip()

    try:
        current = sdk.get_settings() or {}
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("get_settings failed: %s", exc)
        current = {}

    validation_error: str | None = None
    flash = None
    updates: dict[str, Any] | None = None

    if raw_json:
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            validation_error = (
                f"Invalid JSON: {exc.msg} (line {exc.lineno}, col {exc.colno})"
            )
            return _render(
                request,
                "settings.html",
                {
                    **_settings_context(current, raw_settings_json=raw_json),
                    "validation_error": validation_error,
                },
                status_code=400,
            )
        if not isinstance(parsed, dict):
            validation_error = "Advanced JSON must be a top-level object."
            return _render(
                request,
                "settings.html",
                {
                    **_settings_context(current, raw_settings_json=raw_json),
                    "validation_error": validation_error,
                },
                status_code=400,
            )
        updates = parsed
    else:
        updates = settings_form.parse_form(form, current)

    if not updates:
        return _render(
            request,
            "settings.html",
            {
                **_settings_context(current),
                "flash": _flash("info", "No changes to save."),
            },
        )

    try:
        updated = sdk.update_settings(updates) or current
        flash = _flash("success", "Settings saved.")
        current = updated
        # Push the freshly saved category preferences into the live
        # log buffer so the next records emitted from any thread
        # honour the new whitelist immediately.
        try:
            log_buffer.sync_from_settings(current)
        except Exception:  # noqa: BLE001 - best effort
            _LOG.debug("log_buffer sync_from_settings failed", exc_info=True)
    except ValidationError as exc:
        validation_error = str(exc)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("update_settings failed: %s", exc)
        validation_error = f"Could not save settings: {exc}"

    return _render(
        request,
        "settings.html",
        {
            **_settings_context(current, raw_settings_json="" if not validation_error else raw_json),
            "validation_error": validation_error,
            "flash": flash,
        },
        status_code=200 if not validation_error else 400,
    )


# ---------------------------------------------------------------------------
# Live logs
# ---------------------------------------------------------------------------

# Filter levels surfaced in the UI. Reuses the buffer's ordering so the
# template and the route validation stay in sync.
LOG_LEVEL_CHOICES: list[dict[str, str]] = [
    {"value": "DEBUG", "label": "Debug"},
    {"value": "INFO", "label": "Info"},
    {"value": "WARNING", "label": "Warning"},
    {"value": "ERROR", "label": "Error"},
    {"value": "CRITICAL", "label": "Critical"},
]

LOG_TAIL_INITIAL = 250
"""How many records to render on the first paint of /ui/logs."""

LOG_STREAM_HEARTBEAT = 15.0
"""Seconds between SSE keep-alive comments when no record matches."""


def _parse_log_filters(
    level: str | None,
    logger: str | None,
    q: str | None,
) -> tuple[int, str | None, str | None]:
    """Coerce raw query-string filters into the buffer's API."""
    min_level = log_buffer._level_value(level, default=logging.NOTSET)
    logger_clean = (logger or "").strip() or None
    text_clean = (q or "").strip() or None
    return min_level, logger_clean, text_clean


def _selected_categories(request: Request) -> list[str]:
    """Return the ``category`` query params, normalized to uppercase.

    Used as an ad-hoc display filter on top of the persistent
    "enabled categories" preference stored in settings.
    """
    raw = request.query_params.getlist("category") if hasattr(
        request, "query_params"
    ) else []
    return [c.strip().upper() for c in raw if c.strip()]


def _sync_log_buffer_from_settings_safe() -> None:
    """Best-effort settings refresh into the log buffer. Never raises."""
    try:
        current = get_sdk().get_settings() or {}
    except Exception:  # noqa: BLE001
        _LOG.debug("settings refresh failed for log buffer", exc_info=True)
        return
    try:
        log_buffer.sync_from_settings(current)
    except Exception:  # noqa: BLE001
        _LOG.debug("log_buffer.sync_from_settings failed", exc_info=True)


@router.get("/ui/logs", name="web_logs")
def web_logs(
    request: Request,
    level: str = "",
    logger: str | None = None,
    q: str | None = None,
) -> HTMLResponse:
    """Render the live log viewer page with an initial snapshot.

    The snapshot lets non-JS / pre-SSE clients see recent history
    immediately; the JS layer then upgrades the page by subscribing
    to :func:`web_logs_stream` for live tail updates.
    """
    maybe = _next_ui_redirect_for_request(request)
    if maybe is not None:
        return maybe
    # Pick up any settings.json change since the last visit. Cheap on
    # every render because the SDK caches the parsed file.
    _sync_log_buffer_from_settings_safe()

    min_level, logger_substr, text = _parse_log_filters(level, logger, q)
    categories = _selected_categories(request)
    records = log_buffer.global_buffer.snapshot(
        min_level=min_level,
        logger_substr=logger_substr,
        text=text,
        categories=categories or None,
        limit=LOG_TAIL_INITIAL,
    )
    last_id = records[-1]["id"] if records else 0
    total_in_buffer = len(log_buffer.global_buffer.snapshot())
    known_cats = log_buffer.global_buffer.known_categories()
    disabled_cats = log_buffer.global_buffer.disabled_categories
    selected_set = set(categories)
    category_chips = [
        {
            "name": cat,
            "active": cat in selected_set,
            "disabled_in_settings": cat in disabled_cats,
        }
        for cat in known_cats
    ]
    return _render(
        request,
        "logs.html",
        {
            "records": records,
            "last_id": last_id,
            "active_filter_level": (level or "").upper(),
            "active_filter_logger": logger or "",
            "active_filter_q": q or "",
            "active_filter_categories": list(categories),
            "level_choices": LOG_LEVEL_CHOICES,
            "category_chips": category_chips,
            "total_in_buffer": total_in_buffer,
            "active_nav": "logs",
            "page_title": "Logs",
        },
    )


@router.get("/ui/logs/data", name="web_logs_data", response_class=JSONResponse)
def web_logs_data(
    request: Request,
    level: str = "",
    logger: str | None = None,
    q: str | None = None,
    since: int = 0,
    limit: int = LOG_TAIL_INITIAL,
) -> JSONResponse:
    """Return the recent records as JSON.

    ``since`` allows clients to ask only for records newer than the
    id they last saw -- used by the JS client on reconnect to catch
    up any messages that landed while it was paused / offline.
    """
    min_level, logger_substr, text = _parse_log_filters(level, logger, q)
    categories = _selected_categories(request)
    snap = log_buffer.global_buffer.snapshot(
        min_level=min_level,
        logger_substr=logger_substr,
        text=text,
        categories=categories or None,
    )
    if since:
        try:
            since_int = int(since)
        except (TypeError, ValueError):
            since_int = 0
        if since_int:
            snap = [r for r in snap if int(r.get("id") or 0) > since_int]
    if limit and limit > 0:
        snap = snap[-limit:]
    return JSONResponse(
        {
            "records": snap,
            "last_id": snap[-1]["id"] if snap else since,
            "buffered": len(log_buffer.global_buffer.snapshot()),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/ui/logs/stream", name="web_logs_stream")
def web_logs_stream(
    request: Request,
    level: str = "",
    logger: str | None = None,
    q: str | None = None,
) -> StreamingResponse:
    """Server-Sent Events feed of new log records that match ``level/logger/q``.

    Each frame's ``event: record`` body is the JSON payload of one
    record (see :class:`log_buffer.BufferingHandler` for the schema).
    The endpoint also emits an opening comment for proxy buffering
    flush and periodic ``: heartbeat`` comments while the buffer is
    quiet so the connection stays open through stingy load-balancers.

    The ``category`` query parameter may be repeated to whitelist
    specific categories (e.g. ``?category=HTTP&category=DOWNLOAD``).
    This is a display-only filter on top of the persistent
    ``logs.enabled_categories`` setting -- categories silenced in
    settings never reach this stream regardless of query string.
    """
    min_level, logger_substr, text = _parse_log_filters(level, logger, q)
    categories = _selected_categories(request)
    subscriber = log_buffer.global_buffer.subscribe()

    def event_stream() -> Iterable[bytes]:
        try:
            yield b": stream-open\n\n"
            for record in log_buffer.stream_filtered(
                subscriber,
                min_level=min_level,
                logger_substr=logger_substr,
                text=text,
                categories=categories or None,
                timeout=LOG_STREAM_HEARTBEAT,
            ):
                if record is None:
                    yield b": heartbeat\n\n"
                    continue
                yield _sse_event("record", json.dumps(record, default=str))
        finally:
            log_buffer.global_buffer.unsubscribe(subscriber)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/ui/logs/clear", name="web_logs_clear")
def web_logs_clear(request: Request) -> Response:
    """Drop every record from the buffer and redirect back to the page."""
    log_buffer.global_buffer.clear()
    if _is_htmx(request):
        return _render(
            request,
            "logs.html",
            {
                "records": [],
                "last_id": 0,
                "active_filter_level": "",
                "active_filter_logger": "",
                "active_filter_q": "",
                "level_choices": LOG_LEVEL_CHOICES,
                "total_in_buffer": 0,
                "active_nav": "logs",
                "page_title": "Logs",
                "flash": _flash("info", "Log buffer cleared."),
            },
        )
    return _redirect("/ui/logs")


# ---------------------------------------------------------------------------
# Progressive Web App (PWA)
# ---------------------------------------------------------------------------
#
# The web UI is served under ``/ui/``. To keep the service-worker
# scope aligned with that surface (and stay clear of the JSON API at
# the root), the service worker is exposed at ``/ui/sw.js`` and the
# manifest at ``/ui/manifest.webmanifest``. The actual files live
# under ``clients/http/static/`` so they can be edited as plain assets
# and served alongside the rest of the static tree, but proxying them
# through dedicated routes lets us:
#
#   * set the correct ``Service-Worker-Allowed`` / cache headers,
#   * return JSON content-types,
#   * keep paths stable even if the static mount point changes.


_MANIFEST_NAME = "AnimeManager"
_MANIFEST_SHORT_NAME = "Anime"
_MANIFEST_DESCRIPTION = (
    "Browse, tag, and queue downloads for your anime catalog — "
    "powered by the embedded AnimeManager SDK."
)
_MANIFEST_THEME = "#0e0f11"
_MANIFEST_ACCENT = "#56d8ef"


def _no_store_headers() -> dict[str, str]:
    """Headers for assets that must never be served from a CDN cache."""
    return {"Cache-Control": "no-cache, must-revalidate"}


@router.get(
    "/ui/manifest.webmanifest",
    name="web_manifest",
    include_in_schema=False,
    response_class=JSONResponse,
)
def web_manifest() -> JSONResponse:
    """Serve the PWA web app manifest.

    Constructed dynamically so the brand name / colors stay in sync
    with the rest of the UI without juggling a separate JSON file.
    Returning ``application/manifest+json`` is required for Chromium's
    installability heuristics to recognize the response.
    """
    manifest = {
        "name": _MANIFEST_NAME,
        "short_name": _MANIFEST_SHORT_NAME,
        "description": _MANIFEST_DESCRIPTION,
        "start_url": "/ui/library",
        "scope": "/ui/",
        "id": "/ui/",
        "display": "standalone",
        "display_override": ["standalone", "minimal-ui"],
        "orientation": "any",
        "background_color": _MANIFEST_THEME,
        "theme_color": _MANIFEST_THEME,
        "prefer_related_applications": False,
        "categories": ["entertainment", "utilities"],
        "lang": "en",
        "icons": [
            {
                "src": "/ui/static/icons/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/ui/static/icons/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/ui/static/icons/maskable-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
        "shortcuts": [
            {
                "name": "Library",
                "short_name": "Library",
                "url": "/ui/library",
            },
            {
                "name": "Downloads",
                "short_name": "Downloads",
                "url": "/ui/downloads",
            },
            {
                "name": "Torrent search",
                "short_name": "Torrents",
                "url": "/ui/torrents",
            },
        ],
    }
    return JSONResponse(
        manifest,
        media_type="application/manifest+json",
        headers=_no_store_headers(),
    )


@router.get(
    "/ui/sw.js",
    name="web_service_worker",
    include_in_schema=False,
)
def web_service_worker() -> Response:
    """Serve the service worker from ``/ui/sw.js``.

    The path is what controls the worker's scope; Chromium will refuse
    to register a SW for ``/ui/`` if it's served from anywhere outside
    that prefix unless we set ``Service-Worker-Allowed``. Keeping the
    file at this route is the simplest contract.
    """
    sw_path = STATIC_DIR / "js" / "sw.js"
    if not sw_path.is_file():
        raise HTTPException(status_code=404, detail="Service worker missing.")
    return FileResponse(
        sw_path,
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, must-revalidate",
            "Service-Worker-Allowed": "/ui/",
        },
    )


@router.get(
    "/ui/offline",
    name="web_offline",
    include_in_schema=False,
)
def web_offline(request: Request) -> HTMLResponse:
    """Render the offline fallback used by the service worker.

    The page is intentionally standalone (inline styles, no external
    JS) so it renders even when no other asset is cached.
    """
    maybe = _next_ui_redirect_for_request(request)
    if maybe is not None:
        return maybe
    return templates.TemplateResponse(
        "offline.html",
        {"request": request},
    )


# ---------------------------------------------------------------------------
# Static assets
# ---------------------------------------------------------------------------


def mount_static(app) -> None:
    """Mount the static asset tree under ``/ui/static``.

    Exposed as a helper so :mod:`clients.http.app` can attach it at
    construction time without importing FastAPI internals here.
    """
    app.mount(
        "/ui/static",
        StaticFiles(directory=str(STATIC_DIR), check_dir=True),
        name="web_static",
    )


__all__ = ["router", "mount_static", "get_sdk"]
