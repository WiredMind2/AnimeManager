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
import json
import ipaddress
import logging
import os
import queue
import re
import threading
import time
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlencode, urlparse

from fastapi import (
    APIRouter,
    Form,
    HTTPException,
    Query,
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
    from ...domain.errors import (
        AnimeManagerError,
        NotFoundError,
        UnauthorizedError,
        ValidationError,
    )
    from ..sdk import ClientSDK
    from application.services import player_session_log
    from . import log_buffer, settings_form
    from .errors import map_error_to_status
    from .telemetry_events import ingest_client_events
except ImportError:  # pragma: no cover
    from application.services import player_session_log  # type: ignore
    from clients.sdk import ClientSDK
    from clients.http import log_buffer, settings_form  # type: ignore  # noqa: F401
    from clients.http.errors import map_error_to_status  # type: ignore
    from clients.http.telemetry_events import ingest_client_events  # type: ignore
    from domain.errors import (  # type: ignore  # noqa: F401
        AnimeManagerError,
        NotFoundError,
        UnauthorizedError,
        ValidationError,
    )

_LOG = logging.getLogger(__name__)

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

    The detail page surfaces both the "Downloaded episodes" library
    (persisted torrent metadata) and any task currently making progress
    for the same anime, so the user always sees a single accurate list.
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
                    if str(row.get("state") or "").upper() == "DELETED":
                        break
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
    source = str(data.get("source") or "").strip().lower()
    data["source"] = source if source in ("manual", "auto") else "manual"
    persisted_status = str(data.get("status") or "").lower()
    if persisted_status == "deleted":
        data["state"] = "DELETED"
        return data
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
    source = str(dl.get("source") or "").strip().lower()
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
        "source": source if source in ("manual", "auto") else "manual",
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


def browser_library_url() -> str:
    """Browser entry point for the library — Next.js or legacy ``/ui/library``.

    When ``WEB_FRONTEND_URL`` is set (e.g. ``http://127.0.0.1:3000`` for the
    Next.js dev server), HTML clients are sent to the modern frontend. Otherwise
    the embedded Jinja UI remains the default so existing deployments keep working.
    """
    frontend = os.environ.get("WEB_FRONTEND_URL", "").strip()
    if frontend:
        return f"{frontend.rstrip('/')}/library"
    return "/ui/library"


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
        {"anime": anime, "user_state": user_state},
    )


def _stay_on_page_redirect(request: Request, anime_id: int) -> RedirectResponse:
    """PRG fallback that returns the user to the page they submitted from."""
    referer = request.headers.get("referer", "")
    if referer:
        parsed = urlparse(referer)
        path = parsed.path or ""
        if path.startswith("/ui/"):
            suffix = f"?{parsed.query}" if parsed.query else ""
            return _redirect(f"{path}{suffix}")
    return _redirect(f"/ui/anime/{anime_id}")


def _start_download_response(request: Request, anime_id: int) -> Response:
    """Keep torrent download actions on the current page (HTMX or PRG)."""
    if not _is_htmx(request):
        return _stay_on_page_redirect(request, anime_id)
    sdk = get_sdk()
    return _render(
        request,
        "partials/download_started.html",
        {
            "anime_torrents": _collect_anime_torrents(sdk, anime_id),
        },
    )


def _annotate_episode_playability(episode_files: list[Any]) -> list[Any]:
    """Tag each episode file dict with a ``playable`` flag.

    Files whose probe found no tracks at all are typically torrent
    preallocations whose download hasn't finished — ffmpeg can't read
    them, so the UI should not offer a Play action. Items that lack the
    probe keys entirely (older SDK shapes) are assumed playable.
    """
    for item in episode_files:
        if not isinstance(item, dict):
            continue
        has_probe_info = "audio_tracks" in item or "subtitle_tracks" in item
        item["playable"] = bool(
            not has_probe_info
            or item.get("audio_tracks")
            or item.get("subtitle_tracks")
        )
    return episode_files


def _episode_player_response(request: Request, anime_id: int) -> Response:
    """Swap the episode table after HTMX mutations; 204 for API-style POSTs."""
    if not _is_htmx(request):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    sdk = get_sdk()
    try:
        anime = sdk.get_anime(anime_id)
    except Exception:  # noqa: BLE001
        anime = {"id": anime_id, "title": ""}
    try:
        episode_files = _annotate_episode_playability(
            list(sdk.list_episode_files(anime_id, user_id=DEFAULT_USER_ID) or [])
        )
    except Exception:  # noqa: BLE001
        _LOG.debug("episode file lookup failed (panel)", exc_info=True)
        episode_files = []
    return _render(
        request,
        "partials/anime_episode_player.html",
        {"anime": anime, "episode_files": episode_files},
    )


def _map_error(exc: Exception) -> tuple[int, str]:
    return map_error_to_status(exc)


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


def _host_resolves_to_private_address(host: str) -> bool:
    """True when ``host`` is a DNS name that resolves to a LAN address."""
    import socket

    try:
        infos = socket.getaddrinfo(
            host,
            None,
            type=socket.SOCK_STREAM,
        )
    except OSError:
        return False
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return True
    return False


def _is_client_allowed_for_streaming(request: Request, sdk: ClientSDK) -> bool:
    host = _client_host(request)
    if not host:
        return False
    if host in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return True

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

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Browsers often use a machine name (``http://desktop:8081``) rather
        # than a literal IP. The old check rejected every non-IP host, which
        # made manifests load (from HTML) while every segment/manifest fetch
        # returned 403 and the player sat on "Buffering…" forever.
        return _host_resolves_to_private_address(host)

    return bool(ip.is_private or ip.is_loopback or ip.is_link_local)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/ui", include_in_schema=False)
def web_ui_root() -> RedirectResponse:
    return _redirect_get(browser_library_url())


@router.get("/ui/library", name="web_library")
def web_library(
    request: Request,
    filter: str = "DEFAULT",
    q: str | None = None,
    page: int = 1,
) -> HTMLResponse:
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


# Cap on streamed cards per WS/SSE session. Clients may over-fetch by
# one (page size + 1) to detect ``has_next`` for the pager.
_LIBRARY_STREAM_MAX_RESULTS: int = 50
_LIBRARY_STREAM_LIMIT_CAP: int = 101


def _clamp_stream_limit(raw_limit: Any, default: int = _LIBRARY_STREAM_MAX_RESULTS) -> int:
    limit = _safe_int(raw_limit, default)
    if limit <= 0 or limit > _LIBRARY_STREAM_LIMIT_CAP:
        return default
    return limit


def _clamp_stream_offset(raw_offset: Any) -> int:
    offset = _safe_int(raw_offset, 0)
    return max(0, offset)


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
    limit = _clamp_stream_limit(websocket.query_params.get("limit"))
    offset = _clamp_stream_offset(websocket.query_params.get("offset"))

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
            for item in sdk.stream_search_anime(query, limit=limit, offset=offset):
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


@router.get("/ui/library/stream", name="web_library_search_stream")
def web_library_search_stream(
    request: Request,
    q: str = "",
    limit: int = _LIBRARY_STREAM_MAX_RESULTS,
    offset: int = 0,
) -> StreamingResponse:
    """Server-Sent Events feed for library search (Next.js proxy compatible).

    Pushes one ``event: card`` per anime (JSON payload) as
    :meth:`ClientSDK.stream_search_anime` yields results — local catalog
    first, then remote providers — then ``event: done`` with the total
    count. Works through the Next.js ``/backend`` HTTP proxy unlike the
    legacy WebSocket at :func:`web_library_search_ws`.
    """
    _ = request  # reserved for future absolute-URL helpers
    query = (q or "").strip()
    limit = _clamp_stream_limit(limit)
    offset = _clamp_stream_offset(offset)

    def event_stream() -> Iterable[bytes]:
        if not query:
            yield _sse_event("error", "Missing search query")
            yield _sse_event("done", "0")
            return

        try:
            from domain.policies import normalize_search_query

            normalized = normalize_search_query(query)
            if len(normalized) < 3:
                yield _sse_event(
                    "error",
                    "Search query must contain at least 3 characters.",
                )
                yield _sse_event("done", "0")
                return
        except ValidationError as exc:
            yield _sse_event("error", str(exc))
            yield _sse_event("done", "0")
            return
        except Exception:  # noqa: BLE001 - never block on validation
            pass

        yield b": stream-open\n\n"

        sdk = get_sdk()
        emitted = 0
        seen_ids: set[Any] = set()
        try:
            for item in sdk.stream_search_anime(
                query, limit=limit, offset=offset
            ):
                anime_id = item.get("id") if isinstance(item, dict) else None
                if anime_id is not None:
                    if anime_id in seen_ids:
                        continue
                    seen_ids.add(anime_id)
                yield _sse_event("card", json.dumps(item))
                emitted += 1
                if emitted >= limit:
                    break
        except ValidationError as exc:
            yield _sse_event("error", str(exc))
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("library search stream failed: %s", exc)
            yield _sse_event(
                "error",
                "Search failed; check the metadata provider configuration.",
            )
        yield _sse_event("done", str(emitted))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/ui/library/season/stream", name="web_library_season_stream")
def web_library_season_stream(
    request: Request,
    year: int = 0,
    season: str = "",
    limit: int = _LIBRARY_STREAM_MAX_RESULTS,
    offset: int = 0,
) -> StreamingResponse:
    """Server-Sent Events feed for broadcast-season browse."""
    _ = request
    season_raw = (season or "").strip()
    limit = _clamp_stream_limit(limit)
    offset = _clamp_stream_offset(offset)

    def event_stream() -> Iterable[bytes]:
        if not season_raw or not year:
            yield _sse_event("error", "Missing year or season.")
            yield _sse_event("done", "0")
            return

        try:
            from domain.policies.season import (
                normalize_airing_season,
                validate_season_year,
            )

            year_value = validate_season_year(year)
            season_value = normalize_airing_season(season_raw)
        except ValidationError as exc:
            yield _sse_event("error", str(exc))
            yield _sse_event("done", "0")
            return
        except Exception:  # noqa: BLE001
            yield _sse_event("error", "Invalid season browse parameters.")
            yield _sse_event("done", "0")
            return

        yield b": stream-open\n\n"

        sdk = get_sdk()
        emitted = 0
        seen_ids: set[Any] = set()
        try:
            for item in sdk.stream_browse_season(
                year_value, season_value, limit=limit, offset=offset
            ):
                anime_id = item.get("id") if isinstance(item, dict) else None
                if anime_id is not None:
                    if anime_id in seen_ids:
                        continue
                    seen_ids.add(anime_id)
                yield _sse_event("card", json.dumps(item))
                emitted += 1
                if emitted >= limit:
                    break
        except ValidationError as exc:
            yield _sse_event("error", str(exc))
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("library season stream failed: %s", exc)
            yield _sse_event(
                "error",
                "Season browse failed; check the metadata provider configuration.",
            )
        yield _sse_event("done", str(emitted))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/ui/library/genre/stream", name="web_library_genre_stream")
def web_library_genre_stream(
    request: Request,
    genre: str = "",
    limit: int = _LIBRARY_STREAM_MAX_RESULTS,
    offset: int = 0,
) -> StreamingResponse:
    """Server-Sent Events feed for genre browse."""
    _ = request
    genre_raw = (genre or "").strip()
    limit = _clamp_stream_limit(limit)
    offset = _clamp_stream_offset(offset)

    def event_stream() -> Iterable[bytes]:
        if not genre_raw:
            yield _sse_event("error", "Missing genre.")
            yield _sse_event("done", "0")
            return

        try:
            from domain.policies.genre import normalize_genres

            genre_value = normalize_genres(genre_raw)
        except ValidationError as exc:
            yield _sse_event("error", str(exc))
            yield _sse_event("done", "0")
            return
        except Exception:  # noqa: BLE001
            yield _sse_event("error", "Invalid genre browse parameters.")
            yield _sse_event("done", "0")
            return

        yield b": stream-open\n\n"

        sdk = get_sdk()
        emitted = 0
        seen_ids: set[Any] = set()
        try:
            for item in sdk.stream_browse_genre(
                genre_value, limit=limit, offset=offset
            ):
                anime_id = item.get("id") if isinstance(item, dict) else None
                if anime_id is not None:
                    if anime_id in seen_ids:
                        continue
                    seen_ids.add(anime_id)
                yield _sse_event("card", json.dumps(item))
                emitted += 1
                if emitted >= limit:
                    break
        except ValidationError as exc:
            yield _sse_event("error", str(exc))
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("library genre stream failed: %s", exc)
            yield _sse_event(
                "error",
                "Genre browse failed; check the metadata provider configuration.",
            )
        yield _sse_event("done", str(emitted))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/ui/library/top/stream", name="web_library_top_stream")
def web_library_top_stream(
    request: Request,
    category: str = "all",
    limit: int = _LIBRARY_STREAM_MAX_RESULTS,
    offset: int = 0,
) -> StreamingResponse:
    """Server-Sent Events feed for top-by-popularity browse."""
    _ = request
    category_raw = (category or "").strip()
    limit = _clamp_stream_limit(limit)
    offset = _clamp_stream_offset(offset)

    def event_stream() -> Iterable[bytes]:
        if not category_raw:
            yield _sse_event("error", "Missing category.")
            yield _sse_event("done", "0")
            return

        try:
            from domain.policies.top import normalize_top_category

            category_value = normalize_top_category(category_raw)
        except ValidationError as exc:
            yield _sse_event("error", str(exc))
            yield _sse_event("done", "0")
            return
        except Exception:  # noqa: BLE001
            yield _sse_event("error", "Invalid top browse parameters.")
            yield _sse_event("done", "0")
            return

        yield b": stream-open\n\n"

        sdk = get_sdk()
        emitted = 0
        seen_ids: set[Any] = set()
        try:
            for item in sdk.stream_browse_top(
                category_value, limit=limit, offset=offset
            ):
                anime_id = item.get("id") if isinstance(item, dict) else None
                if anime_id is not None:
                    if anime_id in seen_ids:
                        continue
                    seen_ids.add(anime_id)
                yield _sse_event("card", json.dumps(item))
                emitted += 1
                if emitted >= limit:
                    break
        except ValidationError as exc:
            yield _sse_event("error", str(exc))
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("library top stream failed: %s", exc)
            yield _sse_event(
                "error",
                "Top browse failed; check the metadata provider configuration.",
            )
        yield _sse_event("done", str(emitted))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/ui/anime/{anime_id}", name="web_anime_detail")
def web_anime_detail(request: Request, anime_id: int) -> HTMLResponse:
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
    try:
        relations = list(sdk.get_relations(anime_id) or [])
    except Exception:  # noqa: BLE001
        _LOG.debug("relations lookup failed", exc_info=True)

    trailer_embed: str | None = None
    if isinstance(anime, dict):
        trailer_embed = _youtube_embed_url(anime.get("trailer"))

    anime_torrents = _collect_anime_torrents(sdk, anime_id)
    try:
        episode_files = _annotate_episode_playability(
            list(sdk.list_episode_files(anime_id, user_id=DEFAULT_USER_ID) or [])
        )
    except Exception:  # noqa: BLE001
        _LOG.debug("episode file lookup failed", exc_info=True)
        episode_files = []

    torrent_search = _build_torrent_search_options_context(sdk, anime_id)

    return _render(
        request,
        "anime_detail.html",
        {
            "anime": anime,
            "user_state": user_state,
            "terms": terms,
            "relations": relations,
            "active_nav": "library",
            "page_title": anime.get("title") if isinstance(anime, dict) else None,
            "trailer_embed": trailer_embed,
            "anime_torrents": anime_torrents,
            "episode_files": episode_files,
            **torrent_search,
        },
    )


def _watch_page_context(
    sdk: Any,
    anime_id: int,
    *,
    file_id: str = "",
) -> dict[str, Any]:
    """Shared watch-page data (``web_anime_watch`` / ``web_anime_watch_json``)."""
    try:
        anime = sdk.get_anime(anime_id)
    except NotFoundError as exc:
        raise exc

    try:
        episode_files = _annotate_episode_playability(
            list(sdk.list_episode_files(anime_id, user_id=DEFAULT_USER_ID) or [])
        )
    except Exception:  # noqa: BLE001
        episode_files = []

    selected_file_id = str(file_id or "").strip()
    if not selected_file_id and episode_files:
        # Default to the first *playable* file. Files that ffprobe could
        # not read (no tracks at all) are typically still-downloading
        # torrent preallocations and would fail to start.
        playable = next(
            (item for item in episode_files if item.get("playable")),
            episode_files[0],
        )
        selected_file_id = str(playable.get("file_id") or "")
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
    }


@router.get("/ui/anime/{anime_id}/watch.json", name="web_anime_watch_json")
def web_anime_watch_json(
    anime_id: int,
    file_id: str = Query(""),
) -> JSONResponse:
    sdk = get_sdk()
    try:
        ctx = _watch_page_context(sdk, anime_id, file_id=file_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"No anime with id {anime_id}.") from None
    return JSONResponse(ctx, headers={"Cache-Control": "no-store"})


@router.get("/ui/anime/{anime_id}/watch", name="web_anime_watch")
def web_anime_watch(
    request: Request,
    anime_id: int,
    file_id: str = "",
) -> HTMLResponse:
    sdk = get_sdk()
    try:
        ctx = _watch_page_context(sdk, anime_id, file_id=file_id)
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

    anime = ctx["anime"]
    return _render(
        request,
        "watch_episode.html",
        {
            **ctx,
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
    return _torrent_search_options_response(request, sdk, anime_id)


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
    return _torrent_search_options_response(request, sdk, anime_id)


@router.get("/ui/anime/{anime_id}/torrent-search-options", name="web_torrent_search_options")
def web_torrent_search_options(request: Request, anime_id: int) -> HTMLResponse:
    """Render the torrent search options partial for the anime detail modal."""
    return _torrent_search_options_response(request, get_sdk(), anime_id)


@router.post("/ui/anime/{anime_id}/search-titles/toggle", name="web_action_toggle_search_title")
def web_action_toggle_search_title(
    request: Request,
    anime_id: int,
    title: str = Form(""),
    enabled: str = Form(""),
) -> HTMLResponse:
    sdk = get_sdk()
    clean = title.strip()
    if clean:
        try:
            if enabled.strip().lower() in ("true", "1", "yes", "on"):
                sdk.enable_search_title(anime_id, clean)
            else:
                sdk.disable_search_title(anime_id, clean)
        except ValidationError as exc:
            _LOG.info("toggle search title validation: %s", exc)
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("toggle search title failed: %s", exc)
    return _torrent_search_options_response(request, sdk, anime_id)


# ---------------------------------------------------------------------------
# Media playback
# ---------------------------------------------------------------------------


def _streaming_settings_snapshot(sdk: ClientSDK) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    try:
        raw = sdk.get_settings() or {}
        if isinstance(raw, dict):
            settings = raw
    except Exception:  # noqa: BLE001
        settings = {}
    web_cfg = settings.get("web", {}) if isinstance(settings, dict) else {}
    if not isinstance(web_cfg, dict):
        web_cfg = {}
    allowlist = web_cfg.get("player_allowlist", [])
    if isinstance(allowlist, str):
        allowlist = [allowlist]
    return {
        "player_allow_public": bool(web_cfg.get("player_allow_public", False)),
        "player_allowlist": list(allowlist) if isinstance(allowlist, list) else [],
    }


def _playback_output_dir(sdk: ClientSDK, session_id: str) -> str:
    session = sdk.get_playback_session(session_id)
    if session and str(session.get("output_dir") or "").strip():
        return str(session["output_dir"])
    return ""


def _log_stream_access_denied(
    request: Request,
    sdk: ClientSDK,
    *,
    session_id: str = "",
    route: str,
) -> None:
    host = _client_host(request)
    snapshot = _streaming_settings_snapshot(sdk)
    fields: dict[str, Any] = {
        "client_host": host,
        "route": route,
        "result": "403",
        **snapshot,
    }
    if session_id:
        fields["session_id"] = session_id
    output_dir = _playback_output_dir(sdk, session_id) if session_id else ""
    if output_dir:
        player_session_log.append(
            output_dir,
            source="server",
            event="stream_access_denied",
            level="warn",
            **fields,
        )
    _LOG.warning(
        "[PLAYER] stream_access_denied route=%s host=%s session=%s",
        route,
        host,
        session_id or "-",
    )


def _log_stream_resolve_event(
    *,
    output_dir: str,
    event: str,
    client_host: str,
    session_id: str,
    segment: str | None,
    started_at: float,
    result: str,
    status_code: int | None = None,
    detail: str | None = None,
) -> None:
    if not output_dir:
        return
    fields: dict[str, Any] = {
        "client_host": client_host,
        "session_id": session_id,
        "latency_ms": int((time.monotonic() - started_at) * 1000),
        "result": result,
    }
    if segment is not None:
        fields["segment"] = segment
    if status_code is not None:
        fields["status"] = status_code
    if detail:
        fields["detail"] = detail
    player_session_log.append(
        output_dir,
        source="server",
        event=event,
        level="warn" if result not in {"ok"} else "info",
        **fields,
    )


@router.post("/ui/anime/{anime_id}/play", name="web_action_play")
def web_action_play(
    request: Request,
    anime_id: int,
    file_id: str = Form(""),
    audio_track: str = Form(""),
    subtitle_track: str = Form(""),
) -> JSONResponse:
    sdk = get_sdk()
    if not _is_client_allowed_for_streaming(request, sdk):
        _log_stream_access_denied(request, sdk, route="play")
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

    # Resume position comes from the server DB only — not from the browser.
    try:
        ep_files = list(sdk.list_episode_files(anime_id, user_id=DEFAULT_USER_ID) or [])
        for ep in ep_files:
            if str(ep.get("file_id") or "") == file_id.strip():
                pos_raw = ep.get("position_seconds")
                if pos_raw is not None:
                    try:
                        server_pos = float(pos_raw)
                    except (TypeError, ValueError):
                        server_pos = 0.0
                    if server_pos >= 10.0:
                        start_time_seconds = server_pos
                break
    except Exception:  # noqa: BLE001
        pass

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
    output_dir = str(session.get("output_dir") or "")
    if output_dir:
        player_session_log.append(
            output_dir,
            source="server",
            event="play_ok",
            session_id=session_id,
            anime_id=anime_id,
            file_id=file_id.strip(),
            client_host=_client_host(request),
            manifest_url=manifest_url,
            hls_anchor_segment=session.get("hls_anchor_segment"),
            duration_seconds=session.get("duration_seconds"),
            total_segments=session.get("total_segments"),
            subtitle_track_count=len(session.get("subtitle_tracks") or []),
        )
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
            "hls_anchor_segment": session.get("hls_anchor_segment"),
            "playback_start_seconds": session.get("playback_start_seconds"),
            "segment_seconds": session.get("segment_seconds"),
            "duration_seconds": session.get("duration_seconds"),
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
    started_at = time.monotonic()
    client_host = _client_host(request)
    if not _is_client_allowed_for_streaming(request, sdk):
        _log_stream_access_denied(request, sdk, session_id=session_id, route="manifest")
        raise HTTPException(status_code=403, detail="Playback is limited to trusted LAN clients.")
    output_dir = _playback_output_dir(sdk, session_id)
    try:
        _session, path = sdk.resolve_playback_media_path(
            session_id=session_id,
            token=token,
            segment_name=None,
        )
        if not output_dir:
            output_dir = str(_session.get("output_dir") or "")
        _log_stream_resolve_event(
            output_dir=output_dir,
            event="manifest_request",
            client_host=client_host,
            session_id=session_id,
            segment=None,
            started_at=started_at,
            result="ok",
        )
    except Exception as exc:  # noqa: BLE001
        code, msg = _map_error(exc)
        _log_stream_resolve_event(
            output_dir=output_dir,
            event="manifest_resolve_error",
            client_host=client_host,
            session_id=session_id,
            segment=None,
            started_at=started_at,
            result="error",
            status_code=code,
            detail=msg,
        )
        raise HTTPException(status_code=code, detail=msg) from exc
    return FileResponse(
        path=path,
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/ui/stream/{session_id}/player.log", name="web_stream_player_log_download")
def web_stream_player_log_download(
    request: Request,
    session_id: str,
    token: str = "",
) -> Response:
    sdk = get_sdk()
    if not _is_client_allowed_for_streaming(request, sdk):
        _log_stream_access_denied(request, sdk, session_id=session_id, route="player_log_download")
        raise HTTPException(status_code=403, detail="Playback is limited to trusted LAN clients.")
    try:
        session, _path = sdk.resolve_playback_media_path(
            session_id=session_id,
            token=token,
            segment_name=None,
        )
    except Exception as exc:  # noqa: BLE001
        code, msg = _map_error(exc)
        raise HTTPException(status_code=code, detail=msg) from exc
    output_dir = str(session.get("output_dir") or "")
    log_path = player_session_log.player_log_path(output_dir)
    if not log_path.is_file():
        raise HTTPException(status_code=404, detail="Player debug log not found.")
    return FileResponse(
        path=str(log_path),
        media_type="text/plain",
        filename="_player.log",
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
    started_at = time.monotonic()
    client_host = _client_host(request)
    if not _is_client_allowed_for_streaming(request, sdk):
        _log_stream_access_denied(request, sdk, session_id=session_id, route="segment")
        raise HTTPException(status_code=403, detail="Playback is limited to trusted LAN clients.")
    output_dir = _playback_output_dir(sdk, session_id)
    try:
        _session, path = sdk.resolve_playback_media_path(
            session_id=session_id,
            token=token,
            segment_name=segment_name,
        )
        if not output_dir:
            output_dir = str(_session.get("output_dir") or "")
        _log_stream_resolve_event(
            output_dir=output_dir,
            event="segment_request",
            client_host=client_host,
            session_id=session_id,
            segment=segment_name,
            started_at=started_at,
            result="ok",
        )
    except Exception as exc:  # noqa: BLE001
        code, msg = _map_error(exc)
        _log_stream_resolve_event(
            output_dir=output_dir,
            event="segment_resolve_error",
            client_host=client_host,
            session_id=session_id,
            segment=segment_name,
            started_at=started_at,
            result="error",
            status_code=code,
            detail=msg,
        )
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
        _log_stream_access_denied(request, sdk, session_id=session_id, route="stop")
        raise HTTPException(status_code=403, detail="Playback is limited to trusted LAN clients.")
    output_dir = _playback_output_dir(sdk, session_id)
    try:
        sdk.stop_playback_session(session_id)
        if output_dir:
            player_session_log.append(
                output_dir,
                source="server",
                event="session_stopped",
                session_id=session_id,
                client_host=_client_host(request),
            )
    except Exception as exc:  # noqa: BLE001
        code, msg = _map_error(exc)
        raise HTTPException(status_code=code, detail=msg) from exc
    return JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})


@router.post("/ui/stream/{session_id}/log", name="web_stream_player_log")
async def web_stream_player_log(
    request: Request,
    session_id: str,
) -> JSONResponse:
    sdk = get_sdk()
    if not _is_client_allowed_for_streaming(request, sdk):
        _log_stream_access_denied(request, sdk, session_id=session_id, route="player_log")
        raise HTTPException(status_code=403, detail="Playback is limited to trusted LAN clients.")
    output_dir = _playback_output_dir(sdk, session_id)
    if not output_dir:
        raise HTTPException(status_code=404, detail="Playback session not found.")
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid JSON body.") from exc
    events = body.get("events") if isinstance(body, dict) else None
    if not isinstance(events, list):
        raise HTTPException(status_code=400, detail="Expected { events: [...] }.")
    accepted = player_session_log.append_client_batch(output_dir, events)
    return JSONResponse(
        {"ok": True, "accepted": accepted},
        headers={"Cache-Control": "no-store"},
    )


@router.post("/ui/telemetry/events", name="web_client_telemetry_events")
async def web_client_telemetry_events(request: Request) -> JSONResponse:
    """Ingest batched browser telemetry events into the live log viewer."""
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid JSON body.") from exc
    events = body.get("events") if isinstance(body, dict) else None
    if not isinstance(events, list):
        raise HTTPException(status_code=400, detail="Expected { events: [...] }.")
    accepted = ingest_client_events(events)
    return JSONResponse(
        {"ok": True, "accepted": accepted},
        headers={"Cache-Control": "no-store"},
    )


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


# Push cadence for the downloads live streams (WebSocket + SSE). Picked
# to feel "live" on the UI without hammering the torrent client when
# several tabs are subscribed at once -- the underlying SDK call already
# throttles to ~0.5s, this just bounds how often we wake up to poll.
_DOWNLOADS_WS_INTERVAL_S: float = 2.0


def _downloads_snapshot_payload(sdk: Any) -> dict[str, Any]:
    """Build one overview/counts/ts payload for downloads live streams."""
    try:
        overview = _load_torrents_overview(sdk)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("downloads snapshot failed: %s", exc)
        overview = {bucket: [] for bucket in _DOWNLOAD_BUCKETS}
    return {
        "overview": overview,
        "counts": _overview_counts(overview),
        "ts": time.time(),
    }


def _downloads_stream_wait() -> bool:
    """Pause between SSE snapshots.

    Returns ``True`` to keep streaming. Tests monkeypatch this to
    ``lambda: False`` so the infinite feed terminates after the first
    snapshot (Starlette's TestClient cannot concurrently read an
    infinite body).
    """
    time.sleep(_DOWNLOADS_WS_INTERVAL_S)
    return True


@router.get("/ui/downloads/stream", name="web_downloads_stream")
def web_downloads_stream(request: Request) -> StreamingResponse:
    """Server-Sent Events feed for the downloads page (Next.js proxy compatible).

    Pushes ``event: snapshot`` frames with
    ``{"overview": {...}, "counts": {...}, "ts": <epoch>}`` every
    ``_DOWNLOADS_WS_INTERVAL_S`` seconds plus an immediate first snapshot
    on connect. Works through the Next.js ``/backend`` HTTP proxy unlike
    the legacy WebSocket at :func:`web_downloads_ws`.

    Out-of-band refresh is handled by the client via
    ``GET /ui/downloads/overview.json`` (EventSource is one-way).
    """
    _ = request  # reserved for disconnect helpers / absolute-URL needs
    sdk = get_sdk()

    def event_stream() -> Iterable[bytes]:
        yield b": stream-open\n\n"
        while True:
            try:
                payload = _downloads_snapshot_payload(sdk)
            except Exception as exc:  # noqa: BLE001
                _LOG.warning("downloads stream snapshot failed: %s", exc)
                empty = {bucket: [] for bucket in _DOWNLOAD_BUCKETS}
                payload = {
                    "overview": empty,
                    "counts": _overview_counts(empty),
                    "ts": time.time(),
                }
            yield _sse_event("snapshot", json.dumps(payload))
            if not _downloads_stream_wait():
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


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
        payload = await asyncio.to_thread(_downloads_snapshot_payload, sdk)
        await websocket.send_json(payload)

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
) -> Response:
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
    return _start_download_response(request, anime_id)


@router.post("/ui/anime/{anime_id}/cancel", name="web_action_cancel")
def web_action_cancel(anime_id: int) -> RedirectResponse:
    sdk = get_sdk()
    try:
        sdk.cancel_download(anime_id)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("cancel_download failed: %s", exc)
    return _redirect("/ui/downloads")


# ---------------------------------------------------------------------------
# Torrent search
# ---------------------------------------------------------------------------


@router.get("/ui/torrents", name="web_torrents")
def web_torrents(
    request: Request,
    term: str | None = None,
    anime_id: int | None = None,
) -> HTMLResponse:
    sdk = get_sdk()
    results: list[dict[str, Any]] = []
    term_clean = (term or "").strip()
    if term_clean:
        terms = [t.strip() for t in term_clean.split(",") if t.strip()]
        try:
            raw = sdk.search_torrents(terms, profile="interactive")
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


def _catalog_titles(anime: dict[str, Any] | None) -> list[str]:
    """Return deduplicated catalog titles (primary + synonyms), preserving order."""
    if not anime or not isinstance(anime, dict):
        return []
    seen: set[str] = set()
    out: list[str] = []
    candidates = [anime.get("title")] + list(anime.get("title_synonyms") or [])
    for raw in candidates:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _catalog_title_keys(catalog: list[str]) -> set[str]:
    return {title.casefold() for title in catalog}


def _dedupe_terms(terms: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in terms:
        text = str(raw).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _manual_search_terms(saved: list[str], catalog_keys: set[str]) -> list[str]:
    """Saved DB terms that are not catalog titles (case-insensitive)."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in saved:
        text = str(raw).strip()
        if not text:
            continue
        key = text.casefold()
        if key in catalog_keys or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _build_torrent_search_options_context(
    sdk: ClientSDK, anime_id: int
) -> dict[str, Any]:
    anime: dict[str, Any] = {"id": anime_id}
    try:
        loaded = sdk.get_anime(anime_id)
        if isinstance(loaded, dict):
            anime = loaded
    except Exception:  # noqa: BLE001
        pass

    catalog = _catalog_titles(anime)
    catalog_keys = _catalog_title_keys(catalog)

    try:
        saved = list(sdk.get_search_terms(anime_id) or [])
    except Exception:  # noqa: BLE001
        saved = []

    manual = _manual_search_terms(saved, catalog_keys)

    try:
        disabled = list(sdk.get_disabled_search_titles(anime_id) or [])
    except Exception:  # noqa: BLE001
        disabled = []

    disabled_keys = {title.casefold() for title in disabled}
    catalog_title_states = [
        {"title": title, "enabled": title.casefold() not in disabled_keys}
        for title in catalog
    ]
    enabled_catalog = [
        state["title"] for state in catalog_title_states if state["enabled"]
    ]
    active_terms = _dedupe_terms([*enabled_catalog, *manual])

    return {
        "anime": anime,
        "anime_id": anime_id,
        "catalog_titles": catalog,
        "catalog_title_states": catalog_title_states,
        "disabled_titles": disabled,
        "manual_terms": manual,
        "active_terms": active_terms,
    }


def _torrent_search_options_response(
    request: Request, sdk: ClientSDK, anime_id: int
) -> HTMLResponse:
    return _render(
        request,
        "partials/torrent_search_options.html",
        _build_torrent_search_options_context(sdk, anime_id),
    )


def _resolve_anime_search_terms(
    sdk: ClientSDK, anime_id: int
) -> tuple[list[str], dict[str, Any]]:
    """Return active search terms and template context for inline torrent search."""
    ctx = _build_torrent_search_options_context(sdk, anime_id)
    return list(ctx.get("active_terms") or []), ctx


def _parse_torrent_search_terms(
    sdk: ClientSDK,
    anime_id: int,
    terms: list[str] | None,
    legacy_term: str | None,
) -> list[str]:
    """Resolve explicit query params or fall back to DB-backed active terms."""
    if terms:
        parsed = _dedupe_terms(terms)
        if parsed:
            return parsed
    legacy = (legacy_term or "").strip()
    if legacy:
        return _dedupe_terms(legacy.split(","))
    active, _ctx = _resolve_anime_search_terms(sdk, anime_id)
    return active


def _build_torrent_stream_url(
    request: Request, anime_id: int, terms: list[str]
) -> str:
    """Build the SSE stream URL with repeated ``terms`` query parameters."""
    base = str(request.url_for("web_anime_torrent_stream", anime_id=anime_id))
    if not terms:
        return base
    qs = urlencode([("terms", term) for term in terms])
    return f"{base}?{qs}"


@router.get("/ui/anime/{anime_id}/torrents", name="web_anime_torrent_search")
def web_anime_torrent_search(
    request: Request,
    anime_id: int,
    terms: list[str] | None = Query(None),
    term: str | None = None,
) -> HTMLResponse:
    """Inline (HTMX) torrent search scoped to an anime.

    Returns the ``partials/anime_torrent_results.html`` skeleton so the
    anime detail page can swap it in-place. The skeleton wires a live
    SSE connection to :func:`web_anime_torrent_stream`; rows are then
    appended progressively as engines respond.

    When no explicit ``terms`` are provided, enabled catalog titles plus
    manual custom terms are searched in parallel.
    """
    sdk = get_sdk()
    active_terms = _parse_torrent_search_terms(sdk, anime_id, terms, term)
    return _render(
        request,
        "partials/anime_torrent_results.html",
        {
            "terms": active_terms,
            "anime_id": anime_id,
            "stream_url": _build_torrent_stream_url(request, anime_id, active_terms),
            "search_error": None,
        },
    )


@router.get("/ui/anime/{anime_id}/torrents/stream", name="web_anime_torrent_stream")
def web_anime_torrent_stream(
    request: Request,
    anime_id: int,
    terms: list[str] | None = Query(None),
    term: str | None = None,
    allow_nsfw: bool = False,
) -> StreamingResponse:
    """Server-Sent Events feed for the inline torrent search.

    Pushes one ``event: row`` per result (a ready-to-render HTML
    ``<tr>``) as soon as the underlying engines emit it, then a final
    ``event: end`` once the search completes (or a single
    ``event: error`` if validation fails). The endpoint never
    materializes the result list, so the user sees the first hits well
    before the slowest engine finishes.
    """
    sdk = get_sdk()
    active_terms = _parse_torrent_search_terms(sdk, anime_id, terms, term)

    def event_stream() -> Iterable[bytes]:
        if not active_terms:
            yield _sse_event(
                "error",
                "No search terms available — enable titles or add custom terms in Search options.",
            )
            yield _sse_event("end", "")
            return

        # Warm signal -- lets the JS show "Searching…" before the first
        # engine returns. SSE comments are ignored by the client but
        # flush the connection.
        yield b": stream-open\n\n"

        emitted = 0
        try:
            for raw in sdk.stream_torrents(
                active_terms,
                profile="interactive",
                allow_nsfw=allow_nsfw,
            ):
                row = _normalize_torrents([raw])
                if not row:
                    continue
                html = templates.get_template(
                    "partials/anime_torrent_row.html"
                ).render({"row": row[0], "anime_id": anime_id, "request": request})
                yield _sse_event("row", html)
                emitted += 1
        except ValidationError as exc:
            yield _sse_event("error", str(exc))
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("inline torrent stream failed: %s", exc)
            yield _sse_event(
                "error",
                "Torrent search failed; check the search engines configuration.",
            )
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
