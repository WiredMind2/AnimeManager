"""Transport-agnostic embedded facade for client adapters.

This module is the canonical home of :class:`EmbeddedClientFacade`,
the single in-process boundary consumed by Tk/Qt/HTTP clients. The
facade is constructed by :func:`composition.root.build_embedded_facade`.

The legacy ``backend.interfaces.embedded.facade`` module is a thin
compatibility shim that re-exports from here.
"""

from __future__ import annotations

from typing import Any, Optional

from application.playback.contract import SESSION_TTL_SECONDS
from application.services.anime_service import AnimeApplicationService
from application.services.startup_jobs import (
    StartupJobReport,
    StartupJobsService,
)
from domain.dto import AnimeListRequest, DownloadRequest, GenreBrowseRequest, SearchRequest, SeasonBrowseRequest, TopBrowseRequest


class EmbeddedClientFacade:
    """Single in-process boundary consumed by Tk/Qt/HTTP clients."""

    def __init__(
        self,
        service: AnimeApplicationService,
        *,
        startup_jobs: Optional[StartupJobsService] = None,
        hydration: Optional[Any] = None,
    ) -> None:
        self._service = service
        self._startup_jobs = startup_jobs
        self._hydration = hydration

    @property
    def hydration(self):
        """Background metadata hydration queue, when wired."""
        return self._hydration

    @property
    def startup_jobs(self) -> Optional[StartupJobsService]:
        """The startup processing pipeline, if one was wired in.

        Returned as ``Optional`` so unit tests and partial graphs can
        skip the wiring without crashing.
        """
        return self._startup_jobs

    def run_startup_jobs(self) -> Optional[StartupJobReport]:
        """Synchronously execute the startup processing pipeline.

        Returns the aggregate :class:`StartupJobReport`, or ``None`` if
        no startup-jobs service was wired into this facade (e.g. in
        unit tests).
        """
        if self._startup_jobs is None:
            return None
        return self._startup_jobs.run()

    def kickoff_startup_jobs(self):
        """Fire-and-forget variant of :meth:`run_startup_jobs`.

        Returns the worker :class:`threading.Thread` (or ``None`` when
        no startup-jobs service is wired) so callers can join in tests
        without blocking interactive launches.
        """
        if self._startup_jobs is None:
            return None
        return self._startup_jobs.run_in_background()

    def start_schedule_loop(self):
        """Start the daily provider schedule refresh loop."""
        if self._startup_jobs is None:
            return None
        return self._startup_jobs.start_schedule_loop()

    def start_auto_download_loop(self):
        """Start the periodic auto-download loop."""
        if self._startup_jobs is None:
            return None
        starter = getattr(self._startup_jobs, "start_auto_download_loop", None)
        if not callable(starter):
            return None
        return starter()

    def stop_schedule_loop(self) -> None:
        """Stop the daily provider schedule refresh loop."""
        if self._startup_jobs is None:
            return
        self._startup_jobs.stop_schedule_loop()
        stopper = getattr(self._startup_jobs, "stop_auto_download_loop", None)
        if callable(stopper):
            stopper()

    def search_anime(self, query: str, limit: int = 50, offset: int = 0):
        return self._service.search_anime(
            SearchRequest(query=query, limit=limit, offset=offset)
        )

    def stream_search_anime(
        self, query: str, limit: int = 50, offset: int = 0
    ):
        """Yield :class:`AnimeEntity` results progressively (local then API)."""
        streamer = getattr(self._service, "stream_search_anime", None)
        request = SearchRequest(query=query, limit=limit, offset=offset)
        if callable(streamer):
            yield from streamer(request)
            return
        for item in self._service.search_anime(request).items:
            yield item

    def browse_season(
        self, year: int, season: str, limit: int = 50, offset: int = 0
    ):
        return self._service.browse_season(
            SeasonBrowseRequest(
                year=year, season=season, limit=limit, offset=offset
            )
        )

    def stream_browse_season(
        self, year: int, season: str, limit: int = 50, offset: int = 0
    ):
        """Yield :class:`AnimeEntity` results for a broadcast season."""
        streamer = getattr(self._service, "stream_browse_season", None)
        request = SeasonBrowseRequest(
            year=year, season=season, limit=limit, offset=offset
        )
        if callable(streamer):
            yield from streamer(request)
            return
        for item in self._service.browse_season(request).items:
            yield item

    def browse_genre(
        self, genre: str | list[str], limit: int = 50, offset: int = 0
    ):
        from domain.policies.genre import normalize_genres

        genres = normalize_genres(genre)
        return self._service.browse_genre(
            GenreBrowseRequest(genres=genres, limit=limit, offset=offset)
        )

    def stream_browse_genre(
        self, genre: str | list[str], limit: int = 50, offset: int = 0
    ):
        """Yield :class:`AnimeEntity` results for a genre browse."""
        from domain.policies.genre import normalize_genres

        genres = normalize_genres(genre)
        streamer = getattr(self._service, "stream_browse_genre", None)
        request = GenreBrowseRequest(
            genres=genres, limit=limit, offset=offset
        )
        if callable(streamer):
            yield from streamer(request)
            return
        for item in self._service.browse_genre(request).items:
            yield item

    def browse_top(self, category: str, limit: int = 50, offset: int = 0):
        return self._service.browse_top(
            TopBrowseRequest(category=category, limit=limit, offset=offset)
        )

    def stream_browse_top(
        self, category: str, limit: int = 50, offset: int = 0
    ):
        """Yield :class:`AnimeEntity` results for a top browse."""
        streamer = getattr(self._service, "stream_browse_top", None)
        request = TopBrowseRequest(
            category=category, limit=limit, offset=offset
        )
        if callable(streamer):
            yield from streamer(request)
            return
        for item in self._service.browse_top(request).items:
            yield item

    def get_anime_list(
        self,
        filter_name: str = "DEFAULT",
        user_id: int | None = None,
        list_start: int = 0,
        list_stop: int = 50,
        hide_rated: bool | None = None,
    ):
        return self._service.get_anime_list(
            AnimeListRequest(
                filter=filter_name,
                user_id=user_id,
                list_start=list_start,
                list_stop=list_stop,
                hide_rated=hide_rated,
            )
        )

    def get_anime_details(self, anime_id: int):
        return self._service.get_anime_details(anime_id)

    def refresh_anime_details(self, anime_id: int) -> dict:
        return self._service.refresh_anime_details(anime_id)

    def start_download(
        self,
        anime_id: int,
        url: str | None = None,
        hash_value: str | None = None,
        user_id: int | None = None,
    ) -> bool:
        return self._service.start_download(
            DownloadRequest(
                anime_id=anime_id,
                url=url,
                hash_value=hash_value,
                user_id=user_id,
            )
        )

    def get_download_progress(self, anime_id: int):
        return self._service.get_download_progress(anime_id)

    def cancel_download(self, anime_id: int) -> bool:
        return self._service.cancel_download(anime_id)

    def pause_torrent(self, hash_value: str) -> bool:
        return self._service.pause_torrent(hash_value)

    def resume_torrent(self, hash_value: str) -> bool:
        return self._service.resume_torrent(hash_value)

    def get_active_downloads(self) -> list[dict]:
        return self._service.get_active_downloads()

    def get_torrents_overview(self) -> dict[str, list[dict]]:
        return self._service.get_torrents_overview()

    def search_torrents(
        self,
        terms: list[str],
        profile: str = "interactive",
        limit: int | None = None,
        allow_nsfw: bool = False,
    ) -> list[dict]:
        return self._service.search_torrents(
            terms, profile=profile, limit=limit, allow_nsfw=allow_nsfw
        )

    def stream_torrents(
        self,
        terms: list[str],
        profile: str = "interactive",
        limit: int | None = None,
        allow_nsfw: bool = False,
    ):
        return self._service.stream_torrents(
            terms, profile=profile, limit=limit, allow_nsfw=allow_nsfw
        )

    def set_tag(self, anime_id: int, tag: str, user_id: int) -> None:
        self._service.set_tag(anime_id, tag, user_id)

    def set_like(
        self, anime_id: int, user_id: int, liked: bool = True
    ) -> None:
        self._service.set_like(anime_id, user_id, liked)

    def set_auto_download(
        self, anime_id: int, user_id: int, enabled: bool = True
    ) -> None:
        self._service.set_auto_download(anime_id, user_id, enabled)

    def mark_seen(self, anime_id: int, file_name: str, user_id: int) -> None:
        self._service.mark_seen(anime_id, file_name, user_id)

    def get_user_state(self, anime_id: int, user_id: int) -> dict:
        return self._service.get_user_state(anime_id, user_id)

    def get_search_terms(self, anime_id: int) -> list[str]:
        return self._service.get_search_terms(anime_id)

    def add_search_term(self, anime_id: int, term: str) -> bool:
        return self._service.add_search_term(anime_id, term)

    def remove_search_term(self, anime_id: int, term: str) -> bool:
        return self._service.remove_search_term(anime_id, term)

    def get_disabled_search_titles(self, anime_id: int) -> list[str]:
        return self._service.get_disabled_search_titles(anime_id)

    def disable_search_title(self, anime_id: int, title: str) -> bool:
        return self._service.disable_search_title(anime_id, title)

    def enable_search_title(self, anime_id: int, title: str) -> bool:
        return self._service.enable_search_title(anime_id, title)

    def get_settings(self) -> dict:
        return self._service.get_settings()

    def update_settings(self, updates: dict) -> dict:
        return self._service.update_settings(updates)

    def get_relations(self, anime_id: int, relation_type: str = "anime") -> list[dict]:
        return self._service.get_relations(anime_id, relation_type)

    def get_anime_torrents(self, anime_id: int) -> list[dict]:
        return self._service.get_anime_torrents(anime_id)

    def get_characters(self, anime_id: int) -> list[dict]:
        return self._service.get_characters(anime_id)

    def get_character(self, character_id: int) -> dict:
        return self._service.get_character(character_id)

    def get_anime_pictures(self, anime_id: int) -> list[dict]:
        return self._service.get_anime_pictures(anime_id)

    def get_anime_pictures_batch(self, anime_ids: list[int]) -> dict[int, list[dict]]:
        return self._service.get_anime_pictures_batch(anime_ids)

    def refresh_anime_characters(self, anime_id: int) -> list[dict]:
        return self._service.refresh_anime_characters(anime_id)

    def refresh_character(self, character_id: int) -> dict:
        return self._service.refresh_character(character_id)

    def refresh_anime_pictures(self, anime_id: int) -> list[dict]:
        return self._service.refresh_anime_pictures(anime_id)

    def list_episode_files(self, anime_id: int, user_id: int | None = None):
        return self._service.list_episode_files(anime_id, user_id=user_id)

    def set_episode_progress(
        self,
        anime_id: int,
        user_id: int,
        file_id: str,
        status: str,
        position_seconds: float | None = None,
    ) -> None:
        self._service.set_episode_progress(
            anime_id,
            user_id,
            file_id,
            status,
            position_seconds=position_seconds,
        )

    def delete_episode_file(self, anime_id: int, file_id: str, user_id: int) -> bool:
        return self._service.delete_episode_file(anime_id, file_id, user_id)

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
    ):
        return self._service.create_playback_session(
            anime_id=anime_id,
            file_id=file_id,
            client_host=client_host,
            ttl_seconds=ttl_seconds,
            audio_track=audio_track,
            subtitle_track=subtitle_track,
            start_time_seconds=start_time_seconds,
        )

    def get_playback_session(self, session_id: str):
        return self._service.get_playback_session(session_id)

    def heartbeat_playback_session(self, session_id: str):
        return self._service.heartbeat_playback_session(session_id)

    def stop_playback_session(self, session_id: str) -> None:
        self._service.stop_playback_session(session_id)

    def resolve_playback_media_path(
        self,
        *,
        session_id: str,
        token: str,
        segment_name: str | None = None,
    ):
        return self._service.resolve_playback_media_path(
            session_id=session_id,
            token=token,
            segment_name=segment_name,
        )


__all__ = ["EmbeddedClientFacade"]
