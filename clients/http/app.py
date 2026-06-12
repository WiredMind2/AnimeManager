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

from fastapi import FastAPI, HTTPException, Request
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
        port_closer = getattr(port, "close", None)
        if callable(port_closer):
            port_closer()
        else:
            closer = getattr(dm, "close", None)
            if callable(closer):
                closer()
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("download port shutdown skipped: %s", exc)


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
        return RedirectResponse(_web.browser_library_url(), status_code=307)
    return {"service": "animemanager-http-client-adapter", "status": "ok"}


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


@app.get("/anime/{anime_id}/relations")
def anime_relations(anime_id: int):
    try:
        return {"items": get_sdk().get_relations(anime_id)}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/anime/{anime_id}/episode-files")
def anime_episode_files(anime_id: int, user_id: int = 1):
    try:
        return {"items": get_sdk().list_episode_files(anime_id, user_id=user_id)}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/anime/{anime_id}/library-torrents")
def anime_library_torrents(anime_id: int):
    """Saved and in-flight torrents for the anime detail downloads table."""
    try:
        from . import web as web_module

        return {"items": web_module._collect_anime_torrents(get_sdk(), anime_id)}
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.get("/anime/{anime_id}/torrent-search-options")
def anime_torrent_search_options(anime_id: int):
    """Catalog title toggles, manual terms, and active search terms."""
    try:
        from . import web as web_module

        ctx = web_module._build_torrent_search_options_context(get_sdk(), anime_id)
        return {
            "catalog_title_states": ctx.get("catalog_title_states") or [],
            "manual_terms": ctx.get("manual_terms") or [],
            "active_terms": ctx.get("active_terms") or [],
        }
    except Exception as exc:  # pragma: no cover
        raise _map_error(exc) from exc


@app.post("/anime/{anime_id}/search-titles/toggle")
def toggle_search_title(anime_id: int, title: str, enabled: bool = True):
    try:
        sdk = get_sdk()
        clean = title.strip()
        if clean:
            if enabled:
                sdk.enable_search_title(anime_id, clean)
            else:
                sdk.disable_search_title(anime_id, clean)
        return {"ok": True}
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
