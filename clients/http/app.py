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

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

try:
    from . import log_buffer as _log_buffer
    from . import web as _web
    from .errors import map_error_to_http as _map_error
    from .errors import register_exception_handlers
    from .health import build_health_snapshot, build_metrics_snapshot, require_local_client
    from .telemetry_middleware import install_telemetry_middleware
    from ..sdk import ClientSDK
except ImportError:
    from clients.http import log_buffer as _log_buffer
    from clients.http import web as _web
    from clients.http.errors import map_error_to_http as _map_error
    from clients.http.errors import register_exception_handlers
    from clients.http.health import build_health_snapshot, build_metrics_snapshot, require_local_client
    from clients.http.telemetry_middleware import install_telemetry_middleware
    from clients.sdk import ClientSDK

# Capture every logger feeding the root before FastAPI/uvicorn start
# emitting their own startup chatter so the live log viewer shows the
# full session history from boot onwards.
_log_buffer.install()

_LOG = logging.getLogger("animemanager.http")


def _init_observability_exporters(_app: FastAPI) -> None:
    """Wire optional Sentry/OpenTelemetry exporters when env vars are set."""
    try:
        from adapters.observability.sentry import init_sentry
    except ImportError:
        init_sentry = None  # type: ignore[assignment,misc]
    if init_sentry is not None:
        init_sentry(_app)
    try:
        from adapters.observability.otel import init_opentelemetry
    except ImportError:
        init_opentelemetry = None  # type: ignore[assignment,misc]
    if init_opentelemetry is not None:
        init_opentelemetry(_app)


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
    stopper = getattr(sdk, "stop_schedule_loop", None)
    if callable(stopper):
        try:
            stopper()
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("schedule loop shutdown skipped: %s", exc)
    hydration_stopper = getattr(sdk, "stop_hydration", None)
    if callable(hydration_stopper):
        try:
            hydration_stopper()
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("hydration shutdown skipped: %s", exc)
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


def _warm_embedded_backend() -> None:
    """Initialize the embedded SDK before accepting HTTP traffic.

    Uvicorn runs lifespan startup before listening; warming here ensures
    the first SSR/API request does not pay the full composition-root cost
    while Next.js is already serving pages.
    """
    try:
        sdk = get_sdk()
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("Embedded backend warm-up skipped: %s", exc)
        return

    kickoff = getattr(sdk, "kickoff_startup_jobs", None)
    if callable(kickoff):
        try:
            kickoff()
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("startup jobs kickoff skipped: %s", exc)

    schedule = getattr(sdk, "start_schedule_loop", None)
    if callable(schedule):
        try:
            schedule()
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("schedule loop start skipped: %s", exc)


@asynccontextmanager
async def _http_lifespan(app: FastAPI):
    _init_observability_exporters(app)
    _warm_embedded_backend()
    yield
    _shutdown_embedded_background()


app = FastAPI(
    title="AnimeManager HTTP Client Adapter",
    lifespan=_http_lifespan,
)
install_telemetry_middleware(app)
register_exception_handlers(app)
_web.mount_static(app)
app.include_router(_web.router)


@lru_cache(maxsize=1)
def get_sdk() -> ClientSDK:
    return ClientSDK()


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


@app.get("/health")
def health():
    """Process health derived from in-process telemetry counters."""
    return build_health_snapshot()


@app.get("/metrics")
def metrics(request: Request):
    """Full in-process telemetry snapshot (LAN-only)."""
    require_local_client(request)
    return build_metrics_snapshot()


@app.get("/anime/{anime_id}")
def get_anime(anime_id: int):
    return get_sdk().get_anime(anime_id)


@app.post("/anime/{anime_id}/refresh")
def refresh_anime(anime_id: int):
    return get_sdk().refresh_anime_details(anime_id)


@app.get("/animelist")
def get_anime_list(
    filter: str = "DEFAULT",
    user_id: int | None = None,
    list_start: int = 0,
    list_stop: int = 50,
    hide_rated: bool | None = None,
):
    return get_sdk().get_anime_list(
        filter_name=filter,
        user_id=user_id,
        list_start=list_start,
        list_stop=list_stop,
        hide_rated=hide_rated,
    )


@app.get("/search")
def search(query: str, limit: int = 50):
    return get_sdk().search_anime(query=query, limit=limit)


@app.get("/season")
def browse_season(year: int, season: str, limit: int = 50):
    return get_sdk().browse_season(year=year, season=season, limit=limit)


@app.get("/genre")
def browse_genre(name: str, limit: int = 50):
    return get_sdk().browse_genre(genre=name, limit=limit)


@app.get("/genres")
def list_genres():
    from domain.policies.genre import GENRES

    return {"items": sorted(GENRES)}


@app.post("/download/{anime_id}")
def start_download(anime_id: int, url: str | None = None, hash_value: str | None = None, user_id: int | None = None):
    started = get_sdk().start_download(anime_id, url=url, hash_value=hash_value, user_id=user_id)
    return {"started": started}


@app.get("/download/progress/{anime_id}")
def download_progress(anime_id: int):
    return get_sdk().get_download_progress(anime_id)


@app.post("/download/cancel/{anime_id}")
def cancel_download(anime_id: int):
    return {"cancelled": get_sdk().cancel_download(anime_id)}


@app.get("/download/active")
def active_downloads():
    return {"items": get_sdk().get_active_downloads()}


@app.get("/torrents/search")
def search_torrents(
    term: str,
    profile: str = "interactive",
    limit: int | None = None,
    allow_nsfw: bool = False,
):
    """Search torrents.

    `limit` is a **per-term** row cap (overrides the active profile).
    Omit it to use the profile default. Total rows scale with the number
    of search terms — there is no global hard ceiling.
    """
    terms = [part.strip() for part in term.split(",") if part.strip()]
    return get_sdk().search_torrents(
        terms=terms, profile=profile, limit=limit, allow_nsfw=allow_nsfw
    )


@app.post("/tag/{anime_id}")
def set_tag(anime_id: int, tag: str, user_id: int):
    get_sdk().set_tag(anime_id, tag, user_id)
    return {"ok": True}


@app.post("/like/{anime_id}")
def set_like(anime_id: int, user_id: int, liked: bool = True):
    get_sdk().set_like(anime_id, user_id=user_id, liked=liked)
    return {"ok": True}


@app.post("/seen/{anime_id}")
def mark_seen(anime_id: int, file_name: str, user_id: int):
    get_sdk().mark_seen(anime_id, file_name=file_name, user_id=user_id)
    return {"ok": True}


@app.get("/state/{anime_id}")
def user_state(anime_id: int, user_id: int):
    return get_sdk().get_user_state(anime_id, user_id)


@app.get("/search-terms/{anime_id}")
def search_terms(anime_id: int):
    return {"items": get_sdk().get_search_terms(anime_id)}


@app.post("/search-terms/{anime_id}")
def add_search_term(anime_id: int, term: str):
    return {"added": get_sdk().add_search_term(anime_id, term)}


@app.delete("/search-terms/{anime_id}")
def remove_search_term(anime_id: int, term: str):
    return {"removed": get_sdk().remove_search_term(anime_id, term)}


@app.get("/anime/{anime_id}/relations")
def anime_relations(anime_id: int):
    return {"items": get_sdk().get_relations(anime_id)}


@app.get("/anime/{anime_id}/characters")
def anime_characters(anime_id: int):
    return {"items": get_sdk().get_characters(anime_id)}


@app.post("/anime/{anime_id}/characters/refresh")
def refresh_anime_characters(anime_id: int):
    return {"items": get_sdk().refresh_anime_characters(anime_id)}


@app.get("/characters/{character_id}")
def get_character(character_id: int):
    return get_sdk().get_character(character_id)


@app.post("/characters/{character_id}/refresh")
def refresh_character(character_id: int):
    return get_sdk().refresh_character(character_id)


@app.get("/anime/{anime_id}/pictures")
def anime_pictures(anime_id: int):
    return {"items": get_sdk().get_anime_pictures(anime_id)}


@app.get("/anime/{anime_id}/episode-files")
def anime_episode_files(anime_id: int, user_id: int = 1):
    return {"items": get_sdk().list_episode_files(anime_id, user_id=user_id)}


@app.get("/anime/{anime_id}/library-torrents")
def anime_library_torrents(anime_id: int):
    """Saved and in-flight torrents for the anime detail downloads table."""
    from . import web as web_module

    return {"items": web_module._collect_anime_torrents(get_sdk(), anime_id)}


@app.get("/anime/{anime_id}/torrent-search-options")
def anime_torrent_search_options(anime_id: int):
    """Catalog title toggles, manual terms, and active search terms."""
    from . import web as web_module

    ctx = web_module._build_torrent_search_options_context(get_sdk(), anime_id)
    return {
        "catalog_title_states": ctx.get("catalog_title_states") or [],
        "manual_terms": ctx.get("manual_terms") or [],
        "active_terms": ctx.get("active_terms") or [],
    }


@app.post("/anime/{anime_id}/search-titles/toggle")
def toggle_search_title(anime_id: int, title: str, enabled: bool = True):
    sdk = get_sdk()
    clean = title.strip()
    if clean:
        if enabled:
            sdk.enable_search_title(anime_id, clean)
        else:
            sdk.disable_search_title(anime_id, clean)
    return {"ok": True}


@app.get("/settings")
def get_settings():
    return get_sdk().get_settings()


@app.patch("/settings")
def update_settings(updates: dict):
    return get_sdk().update_settings(updates)
