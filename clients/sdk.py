"""Shared client SDK consumed by Tk/Qt/HTTP adapters."""

from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache
from typing import Any

try:
    from ..composition.root import build_embedded_facade
    from ..application.playback.contract import SESSION_TTL_SECONDS
    from ..domain.errors import AnimeManagerError
except ImportError:
    from composition.root import build_embedded_facade
    from application.playback.contract import SESSION_TTL_SECONDS
    from domain.errors import AnimeManagerError


@lru_cache(maxsize=1)
def _facade():
    return build_embedded_facade()


class ClientSDK:
    """Stable command/query API for all client adapters."""

    def __init__(self) -> None:
        self._facade = _facade()

    def _attach_picture_variants(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Attach ``picture_variants`` from the pictures table onto anime dicts."""
        if not items:
            return items
        ids = [int(item["id"]) for item in items if item.get("id") is not None]
        if not ids:
            return items
        batcher = getattr(self._facade, "get_anime_pictures_batch", None)
        cache: dict[int, list[dict[str, Any]]] = {}
        if callable(batcher):
            try:
                cache = dict(batcher(ids) or {})
            except Exception:
                cache = {}
        for item in items:
            anime_id = item.get("id")
            if anime_id is None:
                item["picture_variants"] = []
                continue
            variants = cache.get(int(anime_id))
            if variants is None:
                try:
                    variants = list(
                        self._facade.get_anime_pictures(int(anime_id)) or []
                    )
                except Exception:
                    variants = []
            item["picture_variants"] = variants
        return items

    def _serialize_anime(self, item: Any) -> dict[str, Any]:
        payload = asdict(item) if not isinstance(item, dict) else dict(item)
        self._attach_picture_variants([payload])
        return payload

    def search_anime(
        self, query: str, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        response = self._facade.search_anime(query, limit, offset=offset)
        return {
            "items": self._attach_picture_variants(
                [asdict(item) for item in response.items]
            ),
            "has_next": response.has_next,
        }

    def stream_search_anime(
        self, query: str, limit: int = 50, offset: int = 0
    ):
        """Yield serializable anime dicts progressively (local then API).

        Mirrors :meth:`stream_torrents`: clients (e.g. the HTTP
        WebSocket) iterate without caring whether the underlying facade
        supports streaming -- when it does, results land card-by-card;
        when it doesn't, the materialized list is fanned out as a
        single batch.
        """
        streamer = getattr(self._facade, "stream_search_anime", None)
        if callable(streamer):
            for item in streamer(query, limit, offset=offset):
                yield self._serialize_anime(item)
            return
        for item in self._facade.search_anime(query, limit, offset=offset).items:
            yield self._serialize_anime(item)

    def browse_season(
        self, year: int, season: str, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        response = self._facade.browse_season(
            year, season, limit, offset=offset
        )
        return {
            "items": self._attach_picture_variants(
                [asdict(item) for item in response.items]
            ),
            "has_next": response.has_next,
        }

    def stream_browse_season(
        self, year: int, season: str, limit: int = 50, offset: int = 0
    ):
        """Yield serializable anime dicts for a broadcast season."""
        streamer = getattr(self._facade, "stream_browse_season", None)
        if callable(streamer):
            for item in streamer(year, season, limit, offset=offset):
                yield self._serialize_anime(item)
            return
        for item in self._facade.browse_season(
            year, season, limit, offset=offset
        ).items:
            yield self._serialize_anime(item)

    def browse_genre(
        self, genre: str | list[str], limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        response = self._facade.browse_genre(genre, limit, offset=offset)
        return {
            "items": self._attach_picture_variants(
                [asdict(item) for item in response.items]
            ),
            "has_next": response.has_next,
        }

    def stream_browse_genre(
        self, genre: str | list[str], limit: int = 50, offset: int = 0
    ):
        """Yield serializable anime dicts for a genre browse."""
        streamer = getattr(self._facade, "stream_browse_genre", None)
        if callable(streamer):
            for item in streamer(genre, limit, offset=offset):
                yield self._serialize_anime(item)
            return
        for item in self._facade.browse_genre(
            genre, limit, offset=offset
        ).items:
            yield self._serialize_anime(item)

    def browse_top(
        self, category: str, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        response = self._facade.browse_top(category, limit, offset=offset)
        return {
            "items": self._attach_picture_variants(
                [asdict(item) for item in response.items]
            ),
            "has_next": response.has_next,
        }

    def stream_browse_top(
        self, category: str, limit: int = 50, offset: int = 0
    ):
        """Yield serializable anime dicts for a top browse."""
        streamer = getattr(self._facade, "stream_browse_top", None)
        if callable(streamer):
            for item in streamer(category, limit, offset=offset):
                yield self._serialize_anime(item)
            return
        for item in self._facade.browse_top(
            category, limit, offset=offset
        ).items:
            yield self._serialize_anime(item)

    def get_anime_list(
        self,
        filter_name: str = "DEFAULT",
        user_id: int | None = None,
        list_start: int = 0,
        list_stop: int = 50,
        hide_rated: bool | None = None,
    ) -> dict[str, Any]:
        response = self._facade.get_anime_list(
            filter_name=filter_name,
            user_id=user_id,
            list_start=list_start,
            list_stop=list_stop,
            hide_rated=hide_rated,
        )
        return {
            "items": self._attach_picture_variants(
                [asdict(item) for item in response.items]
            ),
            "has_next": response.has_next,
        }

    def stop_hydration(self) -> None:
        """Stop the background metadata hydration worker."""
        hydration = getattr(self._facade, "hydration", None)
        if hydration is None:
            return
        stopper = getattr(hydration, "stop", None)
        if callable(stopper):
            stopper()

    def get_anime(self, anime_id: int) -> dict[str, Any]:
        result = self._facade.get_anime_details(anime_id)
        payload = asdict(result.entity)
        payload["metadata_pending"] = result.metadata_pending
        payload["metadata_refreshing"] = result.metadata_refreshing
        self._attach_picture_variants([payload])
        return payload

    def refresh_anime_details(self, anime_id: int) -> dict[str, Any]:
        return self._facade.refresh_anime_details(anime_id)

    def start_download(
        self,
        anime_id: int,
        url: str | None = None,
        hash_value: str | None = None,
        user_id: int | None = None,
    ) -> bool:
        return self._facade.start_download(anime_id, url=url, hash_value=hash_value, user_id=user_id)

    def get_download_progress(self, anime_id: int) -> dict[str, Any]:
        return self._facade.get_download_progress(anime_id)

    def cancel_download(self, anime_id: int) -> bool:
        return self._facade.cancel_download(anime_id)

    def pause_torrent(self, hash_value: str) -> bool:
        return self._facade.pause_torrent(hash_value)

    def resume_torrent(self, hash_value: str) -> bool:
        return self._facade.resume_torrent(hash_value)

    def get_active_downloads(self) -> list[dict[str, Any]]:
        return self._facade.get_active_downloads()

    def get_torrents_overview(self) -> dict[str, list[dict[str, Any]]]:
        """Return all torrents bucketed by category for the downloads page.

        Falls back to ``{"active": get_active_downloads(), ...}`` when
        the embedded facade was built without the overview method
        (older revisions). The shape is documented in
        :meth:`AnimeApplicationService.get_torrents_overview`.
        """
        getter = getattr(self._facade, "get_torrents_overview", None)
        if callable(getter):
            try:
                result = getter() or {}
            except Exception:
                result = {}
            if isinstance(result, dict) and result:
                return result
        return {
            "active": list(self._facade.get_active_downloads() or []),
            "seeding": [],
            "completed": [],
            "error": [],
            "other": [],
        }

    def search_torrents(
        self,
        terms: list[str],
        profile: str = "interactive",
        limit: int | None = None,
        allow_nsfw: bool = False,
    ) -> list[dict[str, Any]]:
        return self._facade.search_torrents(
            terms, profile=profile, limit=limit, allow_nsfw=allow_nsfw
        )

    def stream_torrents(
        self,
        terms: list[str],
        profile: str = "interactive",
        limit: int | None = None,
        allow_nsfw: bool = False,
    ):
        """Iterate torrent results as soon as the underlying engines return them.

        ``limit`` overrides the per-term row cap; omit for the profile default.
        Falls back transparently to materialized :meth:`search_torrents`
        when the embedded facade is older than the streaming contract.
        """
        streamer = getattr(self._facade, "stream_torrents", None)
        if callable(streamer):
            yield from streamer(
                terms, profile=profile, limit=limit, allow_nsfw=allow_nsfw
            )
            return
        for row in self._facade.search_torrents(
            terms, profile=profile, limit=limit, allow_nsfw=allow_nsfw
        ):
            yield row

    def set_tag(self, anime_id: int, tag: str, user_id: int) -> None:
        self._facade.set_tag(anime_id, tag, user_id)

    def set_like(self, anime_id: int, user_id: int, liked: bool = True) -> None:
        self._facade.set_like(anime_id, user_id, liked)

    def set_auto_download(
        self, anime_id: int, user_id: int, enabled: bool = True
    ) -> None:
        self._facade.set_auto_download(anime_id, user_id, enabled)

    def mark_seen(self, anime_id: int, file_name: str, user_id: int) -> None:
        self._facade.mark_seen(anime_id, file_name, user_id)

    def get_user_state(self, anime_id: int, user_id: int) -> dict[str, Any]:
        return self._facade.get_user_state(anime_id, user_id)

    def get_search_terms(self, anime_id: int) -> list[str]:
        return self._facade.get_search_terms(anime_id)

    def add_search_term(self, anime_id: int, term: str) -> bool:
        return self._facade.add_search_term(anime_id, term)

    def remove_search_term(self, anime_id: int, term: str) -> bool:
        return self._facade.remove_search_term(anime_id, term)

    def get_disabled_search_titles(self, anime_id: int) -> list[str]:
        return self._facade.get_disabled_search_titles(anime_id)

    def disable_search_title(self, anime_id: int, title: str) -> bool:
        return self._facade.disable_search_title(anime_id, title)

    def enable_search_title(self, anime_id: int, title: str) -> bool:
        return self._facade.enable_search_title(anime_id, title)

    def get_settings(self) -> dict[str, Any]:
        return self._facade.get_settings()

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        return self._facade.update_settings(updates)

    def get_relations(self, anime_id: int, relation_type: str = "anime") -> list[dict[str, Any]]:
        rows = [dict(row) for row in (self._facade.get_relations(anime_id, relation_type) or []) if isinstance(row, dict)]
        rel_ids: list[int] = []
        for row in rows:
            rel_id = row.get("rel_id") or row.get("anime_id")
            if rel_id is None:
                continue
            try:
                rel_ids.append(int(rel_id))
            except (TypeError, ValueError):
                continue
        cache: dict[int, list[dict[str, Any]]] = {}
        batcher = getattr(self._facade, "get_anime_pictures_batch", None)
        if callable(batcher) and rel_ids:
            try:
                cache = dict(batcher(rel_ids) or {})
            except Exception:
                cache = {}
        for row in rows:
            rel_id = row.get("rel_id") or row.get("anime_id")
            try:
                key = int(rel_id) if rel_id is not None else None
            except (TypeError, ValueError):
                key = None
            row["picture_variants"] = cache.get(key, []) if key is not None else []
        return rows

    def get_anime_torrents(self, anime_id: int) -> list[dict[str, Any]]:
        return self._facade.get_anime_torrents(anime_id)

    def get_characters(self, anime_id: int) -> list[dict[str, Any]]:
        return self._facade.get_characters(anime_id)

    def get_character(self, character_id: int) -> dict[str, Any]:
        return self._facade.get_character(character_id)

    def get_anime_pictures(self, anime_id: int) -> list[dict[str, Any]]:
        return self._facade.get_anime_pictures(anime_id)

    def refresh_anime_characters(self, anime_id: int) -> list[dict[str, Any]]:
        return self._facade.refresh_anime_characters(anime_id)

    def refresh_character(self, character_id: int) -> dict[str, Any]:
        return self._facade.refresh_character(character_id)

    def refresh_anime_pictures(self, anime_id: int) -> list[dict[str, Any]]:
        return self._facade.refresh_anime_pictures(anime_id)

    def list_episode_files(
        self, anime_id: int, user_id: int | None = None
    ) -> list[dict[str, Any]]:
        files = self._facade.list_episode_files(anime_id, user_id=user_id)
        return [asdict(item) for item in files]

    def set_episode_progress(
        self,
        anime_id: int,
        user_id: int,
        file_id: str,
        status: str,
        position_seconds: float | None = None,
    ) -> None:
        self._facade.set_episode_progress(
            anime_id,
            user_id,
            file_id,
            status,
            position_seconds=position_seconds,
        )

    def delete_episode_file(self, anime_id: int, file_id: str, user_id: int) -> bool:
        return bool(self._facade.delete_episode_file(anime_id, file_id, user_id))

    def create_playback_session(
        self,
        anime_id: int,
        file_id: str,
        *,
        client_host: str = "",
        ttl_seconds: int = SESSION_TTL_SECONDS,
        audio_track: int | None = None,
        subtitle_track: int | None = None,
        start_time_seconds: float | None = None,
    ) -> dict[str, Any]:
        session = self._facade.create_playback_session(
            anime_id=anime_id,
            file_id=file_id,
            client_host=client_host,
            ttl_seconds=ttl_seconds,
            audio_track=audio_track,
            subtitle_track=subtitle_track,
            start_time_seconds=start_time_seconds,
        )
        return asdict(session)

    def get_playback_session(self, session_id: str) -> dict[str, Any] | None:
        session = self._facade.get_playback_session(session_id)
        return asdict(session) if session is not None else None

    def heartbeat_playback_session(self, session_id: str) -> dict[str, Any]:
        return asdict(self._facade.heartbeat_playback_session(session_id))

    def stop_playback_session(self, session_id: str) -> None:
        self._facade.stop_playback_session(session_id)

    def resolve_playback_media_path(
        self,
        *,
        session_id: str,
        token: str,
        segment_name: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        session, media_path = self._facade.resolve_playback_media_path(
            session_id=session_id,
            token=token,
            segment_name=segment_name,
        )
        return asdict(session), media_path

    def run_startup_jobs(self) -> dict[str, Any] | None:
        """Synchronously run the startup processing pipeline.

        See :meth:`composition.facade.EmbeddedClientFacade.run_startup_jobs`
        for behavior. Returns a serialisable summary dict so HTTP/CLI
        callers can introspect the result.
        """
        runner = getattr(self._facade, "run_startup_jobs", None)
        if not callable(runner):
            return None
        report = runner()
        if report is None:
            return None
        return {
            "total": report.total,
            "failures": report.failures,
            "elapsed_ms": report.elapsed_ms,
            "outcomes": [
                {
                    "name": o.name,
                    "ok": o.ok,
                    "detail": o.detail,
                    "elapsed_ms": o.elapsed_ms,
                }
                for o in report.outcomes
            ],
        }

    def kickoff_startup_jobs(self):
        """Fire the startup pipeline on a background thread.

        Returns the worker :class:`threading.Thread`, or ``None`` when
        the wired facade does not expose a startup-jobs service.
        """
        kickoff = getattr(self._facade, "kickoff_startup_jobs", None)
        if not callable(kickoff):
            return None
        return kickoff()

    def start_schedule_loop(self):
        """Start the daily provider schedule refresh loop."""
        starter = getattr(self._facade, "start_schedule_loop", None)
        if not callable(starter):
            return None
        return starter()

    def start_auto_download_loop(self):
        """Start the periodic auto-download loop."""
        starter = getattr(self._facade, "start_auto_download_loop", None)
        if not callable(starter):
            return None
        return starter()

    def stop_schedule_loop(self) -> None:
        """Stop the daily provider schedule refresh loop."""
        stopper = getattr(self._facade, "stop_schedule_loop", None)
        if callable(stopper):
            stopper()


__all__ = ["ClientSDK", "AnimeManagerError"]
