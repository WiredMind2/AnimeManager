"""HTTP adapter implemented as a peer client over shared SDK.

The module exposes two surfaces:

* a JSON API (``/anime``, ``/animelist``, ``/search``, ...) for
  programmatic clients and the test suite,
* a server-rendered web UI mounted under ``/ui`` (see
  :mod:`clients.http.web`), which is the canonical user-facing web
  client.

Both surfaces consume the same :class:`clients.sdk.ClientSDK`. The
root path redirects to the web UI; the JSON service description lives
at ``/api``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

try:
    from ...domain.errors import NotFoundError, ValidationError
    from . import log_buffer as _log_buffer
    from . import web as _web
    from ..sdk import ClientSDK
except ImportError:
    from clients.http import log_buffer as _log_buffer
    from clients.http import web as _web
    from clients.sdk import ClientSDK
    from domain.errors import NotFoundError, ValidationError

# Capture every logger feeding the root before FastAPI/uvicorn start
# emitting their own startup chatter so the live log viewer shows the
# full session history from boot onwards.
_log_buffer.install()

_LOG = logging.getLogger("animemanager.http")


def _shutdown_embedded_background() -> None:
    """Release legacy download workers so uvicorn can exit after Ctrl+C.

    :class:`~application.services.download_manager.DownloadManager` holds a
    :class:`~concurrent.futures.ThreadPoolExecutor` whose worker threads are
    non-daemon; if we never call :meth:`~DownloadManager.close`, graceful
    shutdown waits indefinitely once ``Shutting down`` is logged.
    """
    try:
        sdk = get_sdk()
    except Exception:  # noqa: BLE001
        return
    facade = getattr(sdk, "_facade", None)
    if facade is None:
        return
    service = getattr(facade, "_service", None)
    if service is None:
        return
    port = getattr(service, "_download_port", None)
    if port is None:
        return
    dm = getattr(port, "_download_manager", None)
    if dm is None:
        return
    try:
        closer = getattr(dm, "close", None)
        if callable(closer):
            closer()
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("download manager shutdown skipped: %s", exc)


@asynccontextmanager
async def _http_lifespan(_app: FastAPI):
    yield
    _shutdown_embedded_background()


app = FastAPI(
    title="AnimeManager HTTP Client Adapter",
    lifespan=_http_lifespan,
)
_web.mount_static(app)
app.include_router(_web.router)


@lru_cache(maxsize=1)
def get_sdk() -> ClientSDK:
    return ClientSDK()


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@app.get("/")
def root(request: Request):
    """Service probe + browser entrypoint.

    Plain HTTP tooling (curl, the test suite, monitoring probes)
    receives the JSON status payload. Browsers that send an
    ``Accept: text/html`` header are bounced to the web UI with 307
    (preserves the GET method semantics; some clients re-issue a 303
    GET as if it were a POST-result which caused spurious double GETs
    in the access log).
    """
    accept = request.headers.get("accept", "").lower()
    if "text/html" in accept:
        return RedirectResponse("/ui/library", status_code=307)
    return {"service": "animemanager-http-client-adapter", "status": "ok"}


@app.get("/ui/api/meta")
def ui_api_meta():
    """Expose stable backend capabilities consumed by Next.js UI."""
    return {
        "service": "animemanager-http-client-adapter",
        "ui_api_version": "2026-05-18",
        "streams": {
            "library_ws": "/ui/library/ws",
            "downloads_ws": "/ui/downloads/ws",
            "torrent_sse": "/ui/anime/{anime_id}/torrents/stream",
            "logs_sse": "/ui/logs/stream",
        },
    }


@app.get("/ui/api/config")
def ui_api_config():
    """Static UI configuration shared with the legacy web templates."""
    return {
        "filter_options": _web.FILTER_OPTIONS,
        "page_size": _web.PAGE_SIZE,
        "torrent_result_limit": _web.TORRENT_RESULT_LIMIT,
    }


@app.get("/ui/api/library")
def ui_api_library(
    q: str | None = None,
    filter: str = "DEFAULT",
    page: int = 1,
    list_start: int | None = None,
    list_stop: int | None = None,
    hide_rated: bool | None = None,
):
    """Library payload for Next.js pages.

    When ``q`` is non-empty, this returns search-mode results.
    Otherwise it mirrors the filter/list pagination payload.
    """
    try:
        sdk = get_sdk()
        query = (q or "").strip()
        page_num = max(1, int(page))
        page_size = _web.PAGE_SIZE
        start = list_start if list_start is not None else (page_num - 1) * page_size
        stop = list_stop if list_stop is not None else start + page_size
        if query:
            items = sdk.search_anime(query=query, limit=max(1, stop - start))
            return {
                "mode": "search",
                "query": query,
                "items": items,
                "has_next": False,
                "list_start": start,
                "list_stop": stop,
                "page": page_num,
                "page_size": page_size,
                "filter": filter,
                "streaming_search": len(query) >= 3,
                "search_ws_path": "/ui/library/ws",
            }
        listing = sdk.get_anime_list(
            filter_name=filter,
            list_start=start,
            list_stop=stop,
            hide_rated=hide_rated,
        )
        return {
            "mode": "list",
            "query": "",
            "items": listing.get("items", []),
            "has_next": bool(listing.get("has_next")),
            "list_start": start,
            "list_stop": stop,
            "page": page_num,
            "page_size": page_size,
            "filter": filter,
            "streaming_search": False,
            "search_ws_path": "",
        }
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/ui/api/anime/{anime_id}/bundle")
def ui_api_anime_bundle(
    anime_id: int,
    user_id: int = 1,
):
    """Aggregate anime detail payload for Next.js detail/watch pages."""
    try:
        sdk = get_sdk()
        anime = sdk.get_anime(anime_id)
        state = sdk.get_user_state(anime_id, user_id)
        terms = sdk.get_search_terms(anime_id)
        episodes = sdk.list_episode_files(anime_id, user_id=user_id)
        relations = sdk.get_relations(anime_id)
        characters = sdk.list_anime_characters(anime_id)
        display = _web.anime_detail_display_for_api(
            sdk,
            anime_id,
            anime=anime if isinstance(anime, dict) else None,
            terms=list(terms or []),
        )
        return {
            "anime": anime,
            "state": state,
            "search_terms": terms,
            "episodes": episodes,
            "relations": display.get("relations", relations),
            "characters": characters,
            "last_torrent_query": sdk.get_last_torrent_search_query(anime_id) or "",
            **display,
        }
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/ui/api/anime/{anime_id}/watch")
def ui_api_anime_watch(
    anime_id: int,
    file_id: str = "",
    user_id: int = 1,
):
    try:
        return _web.watch_context_for_api(
            get_sdk(),
            anime_id,
            file_id=file_id,
            user_id=user_id,
        )
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/ui/api/settings")
def ui_api_settings():
    try:
        from . import settings_form

        current = get_sdk().get_settings() or {}
        return {
            "settings": current,
            "sections": settings_form.build_sections(current),
        }
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/ui/api/logs/page")
def ui_api_logs_page(
    request: Request,
    level: str = "",
    logger: str | None = None,
    q: str | None = None,
):
    """Logs page snapshot for Next.js (mirrors ``web_logs`` context)."""
    try:
        _web._sync_log_buffer_from_settings_safe()
        min_level, logger_substr, text = _web._parse_log_filters(level, logger, q)
        categories = _web._selected_categories(request)
        records = _web.log_buffer.global_buffer.snapshot(
            min_level=min_level,
            logger_substr=logger_substr,
            text=text,
            categories=categories or None,
            limit=_web.LOG_TAIL_INITIAL,
        )
        last_id = records[-1]["id"] if records else 0
        total_in_buffer = len(_web.log_buffer.global_buffer.snapshot())
        known_cats = _web.log_buffer.global_buffer.known_categories()
        disabled_cats = _web.log_buffer.global_buffer.disabled_categories
        selected_set = set(categories)
        category_chips = [
            {
                "name": cat,
                "active": cat in selected_set,
                "disabled_in_settings": cat in disabled_cats,
            }
            for cat in known_cats
        ]
        return {
            "records": records,
            "last_id": last_id,
            "active_filter_level": (level or "").upper(),
            "active_filter_logger": logger or "",
            "active_filter_q": q or "",
            "active_filter_categories": list(categories),
            "level_choices": _web.LOG_LEVEL_CHOICES,
            "category_chips": category_chips,
            "total_in_buffer": total_in_buffer,
        }
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/ui/api/anime/{anime_id}/characters")
def ui_api_anime_characters(anime_id: int):
    try:
        return {"items": get_sdk().list_anime_characters(anime_id)}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/ui/api/anime/{anime_id}/episodes")
def ui_api_anime_episodes(anime_id: int, user_id: int = 1):
    try:
        return {"items": get_sdk().list_episode_files(anime_id, user_id=user_id)}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/ui/api/torrents/search")
def ui_api_torrent_search(
    anime_id: int | None = None,
    term: str = "",
    profile: str = "interactive",
    limit: int = 200,
):
    """Search torrents using the same contract as Next.js torrent views."""
    query = term.strip()
    if not query and anime_id is not None:
        query = get_sdk().get_last_torrent_search_query(anime_id) or ""
    terms = [part.strip() for part in query.split(",") if part.strip()]
    try:
        raw = get_sdk().search_torrents(terms=terms, profile=profile, limit=limit)
        items = _web._normalize_torrents(raw)
        if anime_id is not None and query:
            get_sdk().set_last_torrent_search_query(anime_id, query)
        return {"query": query, "items": items}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/ui/api/downloads/overview")
def ui_api_downloads_overview():
    try:
        overview = get_sdk().get_torrents_overview()
        counts = {key: len(overview.get(key) or []) for key in overview.keys()}
        return {"overview": overview, "counts": counts}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/ui/api/logs")
def ui_api_logs(
    level: str = "INFO",
    logger: str = "",
    q: str = "",
    limit: int = 200,
    since: int = 0,
):
    """Read a JSON slice of buffered logs for Next.js log page."""
    min_level, logger_substr, text = _web._parse_log_filters(level, logger, q)
    snap = _web.log_buffer.global_buffer.snapshot(
        min_level=min_level,
        logger_substr=logger_substr,
        text=text,
        categories=None,
    )
    if since:
        snap = [r for r in snap if int(r.get("id") or 0) > int(since)]
    if limit and limit > 0:
        snap = snap[-limit:]
    return {
        "records": snap,
        "last_id": snap[-1]["id"] if snap else since,
        "buffered": len(_web.log_buffer.global_buffer.snapshot()),
    }


@app.post("/ui/api/anime/{anime_id}/like")
def ui_api_like_anime(anime_id: int, payload: dict = Body(default={})):
    try:
        user_id = int(payload.get("user_id", 1))
        liked = bool(payload.get("liked", True))
        get_sdk().set_like(anime_id, user_id=user_id, liked=liked)
        return {"ok": True}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.post("/ui/api/anime/{anime_id}/tag")
def ui_api_tag_anime(anime_id: int, payload: dict = Body(default={})):
    try:
        user_id = int(payload.get("user_id", 1))
        tag = str(payload.get("tag", "")).strip()
        get_sdk().set_tag(anime_id, tag=tag, user_id=user_id)
        return {"ok": True, "tag": tag}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.post("/ui/api/anime/{anime_id}/download")
def ui_api_download_anime(anime_id: int, payload: dict = Body(default={})):
    try:
        return {
            "started": get_sdk().start_download(
                anime_id,
                url=payload.get("url"),
                hash_value=payload.get("hash"),
                user_id=int(payload.get("user_id", 1)),
            )
        }
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.post("/ui/api/anime/{anime_id}/cancel")
def ui_api_cancel_anime_download(anime_id: int):
    try:
        return {"cancelled": bool(get_sdk().cancel_download(anime_id))}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/anime/{anime_id}")
def get_anime(anime_id: int):
    try:
        return get_sdk().get_anime(anime_id)
    except Exception as exc:  # pragma: no cover - mapping path
        raise _map_error(exc) from exc


@app.get("/animelist")
def get_anime_list(
    filter: str = "DEFAULT",
    user_id: int | None = None,
    list_start: int = 0,
    list_stop: int = 50,
    hide_rated: bool | None = None,
):
    try:
        return get_sdk().get_anime_list(
            filter_name=filter,
            user_id=user_id,
            list_start=list_start,
            list_stop=list_stop,
            hide_rated=hide_rated,
        )
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/search")
def search(query: str, limit: int = 50):
    try:
        return get_sdk().search_anime(query=query, limit=limit)
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.post("/download/{anime_id}")
def start_download(anime_id: int, url: str | None = None, hash_value: str | None = None, user_id: int | None = None):
    try:
        started = get_sdk().start_download(anime_id, url=url, hash_value=hash_value, user_id=user_id)
        return {"started": started}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/download/progress/{anime_id}")
def download_progress(anime_id: int):
    try:
        return get_sdk().get_download_progress(anime_id)
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.post("/download/cancel/{anime_id}")
def cancel_download(anime_id: int):
    try:
        return {"cancelled": get_sdk().cancel_download(anime_id)}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/download/active")
def active_downloads():
    try:
        return {"items": get_sdk().get_active_downloads()}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/torrents/search")
def search_torrents(term: str, profile: str = "interactive", limit: int = 200):
    terms = [part.strip() for part in term.split(",") if part.strip()]
    try:
        return get_sdk().search_torrents(terms=terms, profile=profile, limit=limit)
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.post("/tag/{anime_id}")
def set_tag(anime_id: int, tag: str, user_id: int):
    try:
        get_sdk().set_tag(anime_id, tag, user_id)
        return {"ok": True}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.post("/like/{anime_id}")
def set_like(anime_id: int, user_id: int, liked: bool = True):
    try:
        get_sdk().set_like(anime_id, user_id=user_id, liked=liked)
        return {"ok": True}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.post("/seen/{anime_id}")
def mark_seen(anime_id: int, file_name: str, user_id: int):
    try:
        get_sdk().mark_seen(anime_id, file_name=file_name, user_id=user_id)
        return {"ok": True}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/state/{anime_id}")
def user_state(anime_id: int, user_id: int):
    try:
        return get_sdk().get_user_state(anime_id, user_id)
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/search-terms/{anime_id}")
def search_terms(anime_id: int):
    try:
        return {"items": get_sdk().get_search_terms(anime_id)}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.post("/search-terms/{anime_id}")
def add_search_term(anime_id: int, term: str):
    try:
        return {"added": get_sdk().add_search_term(anime_id, term)}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.delete("/search-terms/{anime_id}")
def remove_search_term(anime_id: int, term: str):
    try:
        return {"removed": get_sdk().remove_search_term(anime_id, term)}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/settings")
def get_settings():
    try:
        return get_sdk().get_settings()
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.patch("/settings")
def update_settings(updates: dict):
    try:
        return get_sdk().update_settings(updates)
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc
