"""Canonical AnimeApplicationService.

This module is the canonical home of the application-level use-case
orchestrator. The legacy ``backend.application.service`` module is a
thin compatibility shim that re-exports from here.
"""

from __future__ import annotations

from application.commands import (
    CreatePlaybackSessionCommand,
    HeartbeatPlaybackSessionCommand,
    StopPlaybackSessionCommand,
)
from application.dto import EpisodeFileDTO, PlaybackSessionDTO
from application.queries import GetPlaybackSessionQuery, ListEpisodeFilesQuery
from application.playback import PlaybackService
from domain.dto import (
    AnimeListRequest,
    AnimeListResponse,
    DownloadRequest,
    GenreBrowseRequest,
    SearchRequest,
    SeasonBrowseRequest,
)
from domain.entities import AnimeEntity
from domain.errors import NotFoundError, ValidationError
from domain.policies import (
    normalize_airing_season,
    normalize_genre,
    normalize_search_query,
    validate_season_year,
)
from ports.interfaces import (
    AnimeRepositoryPort,
    DownloadPort,
    MetadataProviderPort,
    UserActionsPort,
)


class AnimeApplicationService:
    """Thin orchestrator exposing stable use-cases to every client adapter."""

    def __init__(
        self,
        anime_repository: AnimeRepositoryPort,
        metadata_provider: MetadataProviderPort,
        download_port: DownloadPort,
        user_actions_port: UserActionsPort,
        media_streaming_service: PlaybackService | None = None,
    ) -> None:
        self._anime_repository = anime_repository
        self._metadata_provider = metadata_provider
        self._download_port = download_port
        self._user_actions_port = user_actions_port
        self._media_streaming = media_streaming_service

    def search_anime(self, request: SearchRequest) -> list[AnimeEntity]:
        query = normalize_search_query(request.query)
        if len(query) < 3:
            raise ValidationError(
                "Search query must contain at least 3 characters."
            )

        seen_ids: set[int] = set()
        merged: list[AnimeEntity] = []
        limit = request.limit

        matched_genre: str | None = None
        try:
            matched_genre = normalize_genre(query)
        except ValidationError:
            matched_genre = None

        if matched_genre is not None:
            for entity in self._anime_repository.list_by_genre(matched_genre, limit):
                if entity.id in seen_ids:
                    continue
                seen_ids.add(entity.id)
                merged.append(entity)
                if len(merged) >= limit:
                    return merged

        for entity in self._anime_repository.search(query, limit):
            if entity.id in seen_ids:
                continue
            seen_ids.add(entity.id)
            merged.append(entity)
            if len(merged) >= limit:
                return merged

        for entity in self._metadata_provider.search(query, limit):
            if entity.id in seen_ids:
                continue
            seen_ids.add(entity.id)
            merged.append(entity)
            if len(merged) >= limit:
                break

        return merged

    def stream_search_anime(self, request: SearchRequest):
        """Yield :class:`AnimeEntity` results progressively.

        Emission order:
        1. The local catalog (fast, single batch) -- so the UI shows
           something within a frame even before any external provider
           replies.
        2. Each remote provider as it completes, deduplicated against
           what has already been emitted.

        Callers can therefore append cards to the page as soon as the
        first batch lands instead of waiting for the slowest provider.
        """
        query = normalize_search_query(request.query)
        if len(query) < 3:
            raise ValidationError(
                "Search query must contain at least 3 characters."
            )

        seen_ids: set[int] = set()

        matched_genre: str | None = None
        try:
            matched_genre = normalize_genre(query)
        except ValidationError:
            matched_genre = None

        if matched_genre is not None:
            for entity in self._anime_repository.list_by_genre(
                matched_genre, request.limit
            ):
                if entity.id in seen_ids:
                    continue
                seen_ids.add(entity.id)
                yield entity

        local_results = self._anime_repository.search(query, request.limit)
        if local_results:
            for entity in local_results:
                if entity.id in seen_ids:
                    continue
                seen_ids.add(entity.id)
                yield entity

        streamer = getattr(self._metadata_provider, "stream_search", None)
        if callable(streamer):
            for entity in streamer(query, request.limit):
                if entity is None or entity.id in seen_ids:
                    continue
                seen_ids.add(entity.id)
                yield entity
            return

        for entity in self._metadata_provider.search(query, request.limit):
            if entity is None or entity.id in seen_ids:
                continue
            seen_ids.add(entity.id)
            yield entity

    def browse_season(self, request: SeasonBrowseRequest) -> list[AnimeEntity]:
        year = validate_season_year(request.year)
        season = normalize_airing_season(request.season)
        limit = request.limit
        seen_ids: set[int] = set()
        merged: list[AnimeEntity] = []

        for entity in self._anime_repository.list_by_airing_season(
            year, season, limit
        ):
            if entity.id in seen_ids:
                continue
            seen_ids.add(entity.id)
            merged.append(entity)
            if len(merged) >= limit:
                return merged

        browser = getattr(self._metadata_provider, "browse_season", None)
        if callable(browser):
            for entity in browser(year, season, limit):
                if entity is None or entity.id in seen_ids:
                    continue
                seen_ids.add(entity.id)
                merged.append(entity)
                if len(merged) >= limit:
                    break
            return merged

        for entity in self._metadata_provider.search(f"{season} {year}", limit):
            if entity is None or entity.id in seen_ids:
                continue
            seen_ids.add(entity.id)
            merged.append(entity)
            if len(merged) >= limit:
                break
        return merged

    def stream_browse_season(self, request: SeasonBrowseRequest):
        """Yield season browse results: local catalog first, then providers."""
        year = validate_season_year(request.year)
        season = normalize_airing_season(request.season)
        seen_ids: set[int] = set()

        for entity in self._anime_repository.list_by_airing_season(
            year, season, request.limit
        ):
            if entity.id in seen_ids:
                continue
            seen_ids.add(entity.id)
            yield entity

        streamer = getattr(self._metadata_provider, "stream_browse_season", None)
        if callable(streamer):
            for entity in streamer(year, season, request.limit):
                if entity is None or entity.id in seen_ids:
                    continue
                seen_ids.add(entity.id)
                yield entity
            return

        browser = getattr(self._metadata_provider, "browse_season", None)
        if callable(browser):
            for entity in browser(year, season, request.limit):
                if entity is None or entity.id in seen_ids:
                    continue
                seen_ids.add(entity.id)
                yield entity
            return

        for entity in self._metadata_provider.search(f"{season} {year}", request.limit):
            if entity is None or entity.id in seen_ids:
                continue
            seen_ids.add(entity.id)
            yield entity

    def browse_genre(self, request: GenreBrowseRequest) -> list[AnimeEntity]:
        genre = normalize_genre(request.genre)
        limit = request.limit
        seen_ids: set[int] = set()
        merged: list[AnimeEntity] = []

        for entity in self._anime_repository.list_by_genre(genre, limit):
            if entity.id in seen_ids:
                continue
            seen_ids.add(entity.id)
            merged.append(entity)
            if len(merged) >= limit:
                return merged

        browser = getattr(self._metadata_provider, "browse_genre", None)
        if callable(browser):
            for entity in browser(genre, limit):
                if entity is None or entity.id in seen_ids:
                    continue
                seen_ids.add(entity.id)
                merged.append(entity)
                if len(merged) >= limit:
                    break
            return merged

        for entity in self._metadata_provider.search(genre, limit):
            if entity is None or entity.id in seen_ids:
                continue
            seen_ids.add(entity.id)
            merged.append(entity)
            if len(merged) >= limit:
                break
        return merged

    def stream_browse_genre(self, request: GenreBrowseRequest):
        """Yield genre browse results: local catalog first, then providers."""
        genre = normalize_genre(request.genre)
        seen_ids: set[int] = set()

        for entity in self._anime_repository.list_by_genre(genre, request.limit):
            if entity.id in seen_ids:
                continue
            seen_ids.add(entity.id)
            yield entity

        streamer = getattr(self._metadata_provider, "stream_browse_genre", None)
        if callable(streamer):
            for entity in streamer(genre, request.limit):
                if entity is None or entity.id in seen_ids:
                    continue
                seen_ids.add(entity.id)
                yield entity
            return

        browser = getattr(self._metadata_provider, "browse_genre", None)
        if callable(browser):
            for entity in browser(genre, request.limit):
                if entity is None or entity.id in seen_ids:
                    continue
                seen_ids.add(entity.id)
                yield entity
            return

        for entity in self._metadata_provider.search(genre, request.limit):
            if entity is None or entity.id in seen_ids:
                continue
            seen_ids.add(entity.id)
            yield entity

    def get_anime_list(self, request: AnimeListRequest) -> AnimeListResponse:
        items, has_next = self._anime_repository.list_anime(
            criteria=request.filter,
            list_start=request.list_start,
            list_stop=request.list_stop,
            hide_rated=request.hide_rated,
            user_id=request.user_id,
        )
        return AnimeListResponse(items=items, has_next=has_next)

    def get_anime_details(self, anime_id: int) -> AnimeEntity:
        anime = self._anime_repository.get_anime(anime_id)
        if anime is None:
            raise NotFoundError(f"Anime with id={anime_id} not found")
        return anime

    def start_download(self, request: DownloadRequest) -> bool:
        if request.url is None and request.hash_value is None:
            raise ValidationError(
                "Either url or hash_value must be provided."
            )
        return self._download_port.start_download(
            anime_id=request.anime_id,
            url=request.url,
            hash_value=request.hash_value,
            user_id=request.user_id,
        )

    def get_download_progress(self, anime_id: int) -> dict:
        return self._download_port.get_download_progress(anime_id)

    def cancel_download(self, anime_id: int) -> bool:
        return self._download_port.cancel_download(anime_id)

    def get_active_downloads(self) -> list[dict]:
        return self._download_port.get_active_downloads()

    def get_torrents_overview(self) -> dict[str, list[dict]]:
        """Unified active / seeding / completed view for the downloads page.

        Delegates to the download port when it implements
        ``get_torrents_overview`` (full overview including torrents
        added in previous sessions). Falls back to deriving a single
        ``active`` bucket from :meth:`get_active_downloads` so older
        adapters keep working without any change.
        """
        getter = getattr(self._download_port, "get_torrents_overview", None)
        if callable(getter):
            try:
                result = getter() or {}
            except Exception:
                result = {}
            if isinstance(result, dict) and result:
                return {
                    "active": list(result.get("active") or []),
                    "seeding": list(result.get("seeding") or []),
                    "completed": list(result.get("completed") or []),
                    "error": list(result.get("error") or []),
                    "other": list(result.get("other") or []),
                }
        return {
            "active": list(self._download_port.get_active_downloads() or []),
            "seeding": [],
            "completed": [],
            "error": [],
            "other": [],
        }

    def search_torrents(
        self,
        terms: list[str],
        profile: str = "interactive",
        limit: int = 200,
    ) -> list[dict]:
        sanitized = self._sanitize_terms(terms)
        return self._download_port.search_torrents(
            sanitized, profile=profile, limit=limit
        )

    def stream_torrents(
        self,
        terms: list[str],
        profile: str = "interactive",
        limit: int = 200,
    ):
        """Yield torrent dicts progressively as engines emit them.

        Falls back to :meth:`search_torrents` (returning the materialized
        list as a single batch) when the active download port has not
        implemented streaming. Callers can therefore consume the result
        uniformly with a ``for row in ...`` loop.
        """
        sanitized = self._sanitize_terms(terms)
        streamer = getattr(self._download_port, "stream_torrents", None)
        if callable(streamer):
            yield from streamer(sanitized, profile=profile, limit=limit)
            return
        for row in self._download_port.search_torrents(
            sanitized, profile=profile, limit=limit
        ):
            yield row

    def _sanitize_terms(self, terms: list[str]) -> list[str]:
        if not terms:
            raise ValidationError("At least one search term is required.")
        sanitized = [str(term).strip() for term in terms if str(term).strip()]
        if not sanitized:
            raise ValidationError("At least one non-empty search term is required.")
        return sanitized

    def set_tag(self, anime_id: int, tag: str, user_id: int) -> None:
        self._user_actions_port.set_tag(anime_id, tag, user_id)

    def set_like(self, anime_id: int, user_id: int, liked: bool = True) -> None:
        self._user_actions_port.set_like(anime_id, liked, user_id)

    def mark_seen(self, anime_id: int, file_name: str, user_id: int) -> None:
        self._user_actions_port.mark_seen(anime_id, file_name, user_id)

    def get_user_state(self, anime_id: int, user_id: int) -> dict:
        return self._user_actions_port.get_user_state(anime_id, user_id)

    def get_search_terms(self, anime_id: int) -> list[str]:
        return self._anime_repository.get_search_terms(anime_id)

    def add_search_term(self, anime_id: int, term: str) -> bool:
        clean = term.strip()
        if len(clean) < 2:
            raise ValidationError("Search term must contain at least 2 characters.")
        return self._anime_repository.add_search_term(anime_id, clean)

    def remove_search_term(self, anime_id: int, term: str) -> bool:
        clean = term.strip()
        if not clean:
            raise ValidationError("Search term cannot be empty.")
        return self._anime_repository.remove_search_term(anime_id, clean)

    def get_disabled_search_titles(self, anime_id: int) -> list[str]:
        getter = getattr(self._anime_repository, "get_disabled_search_titles", None)
        if not callable(getter):
            return []
        return list(getter(anime_id) or [])

    def disable_search_title(self, anime_id: int, title: str) -> bool:
        clean = title.strip()
        if not clean:
            raise ValidationError("Title cannot be empty.")
        disable = getattr(self._anime_repository, "disable_search_title", None)
        if not callable(disable):
            return False
        return bool(disable(anime_id, clean))

    def enable_search_title(self, anime_id: int, title: str) -> bool:
        clean = title.strip()
        if not clean:
            raise ValidationError("Title cannot be empty.")
        enable = getattr(self._anime_repository, "enable_search_title", None)
        if not callable(enable):
            return False
        return bool(enable(anime_id, clean))

    def get_settings(self) -> dict:
        return self._anime_repository.get_settings()

    def update_settings(self, updates: dict) -> dict:
        if not isinstance(updates, dict) or not updates:
            raise ValidationError("Settings updates must be a non-empty object.")
        return self._anime_repository.update_settings(updates)

    def get_relations(self, anime_id: int, relation_type: str = "anime") -> list[dict]:
        return self._anime_repository.get_relations(anime_id, relation_type)

    def get_anime_torrents(self, anime_id: int) -> list[dict]:
        getter = getattr(self._anime_repository, "get_anime_torrents", None)
        if not callable(getter):
            return []
        return list(getter(anime_id) or [])

    def get_characters(self, anime_id: int) -> list[dict]:
        getter = getattr(self._anime_repository, "get_characters", None)
        if not callable(getter):
            return []
        return list(getter(anime_id) or [])

    def get_character(self, character_id: int) -> dict:
        getter = getattr(self._anime_repository, "get_character", None)
        if not callable(getter):
            raise NotFoundError(f"Character with id={character_id} not found")
        payload = getter(character_id)
        if payload is None:
            raise NotFoundError(f"Character with id={character_id} not found")
        return payload

    def get_anime_pictures(self, anime_id: int) -> list[dict]:
        getter = getattr(self._anime_repository, "get_anime_pictures", None)
        if not callable(getter):
            return []
        return list(getter(anime_id) or [])

    def refresh_anime_characters(self, anime_id: int) -> list[dict]:
        refresher = getattr(self._anime_repository, "refresh_anime_characters", None)
        if not callable(refresher):
            return self.get_characters(anime_id)
        return list(refresher(anime_id) or [])

    def refresh_character(self, character_id: int) -> dict:
        refresher = getattr(self._anime_repository, "refresh_character", None)
        if not callable(refresher):
            return self.get_character(character_id)
        return refresher(character_id)

    def refresh_anime_pictures(self, anime_id: int) -> list[dict]:
        refresher = getattr(self._anime_repository, "refresh_anime_pictures", None)
        if not callable(refresher):
            return self.get_anime_pictures(anime_id)
        return list(refresher(anime_id) or [])

    def _list_episode_files_core(self, anime_id: int) -> list[EpisodeFileDTO]:
        media = self._require_media_streaming()
        return media.list_episode_files(ListEpisodeFilesQuery(anime_id=anime_id))

    def _has_completed_torrent(self, anime_id: int) -> bool:
        for row in self.get_anime_torrents(anime_id):
            if not isinstance(row, dict):
                continue
            if str(row.get("status") or "").lower() == "deleted":
                continue
            state = str(row.get("state") or "").upper()
            if state == "DELETED":
                continue
            if state == "COMPLETE":
                return True
            try:
                size = int(row.get("size") or 0)
                downloaded = int(row.get("downloaded") or 0)
            except (TypeError, ValueError):
                continue
            if size > 0 and downloaded >= size:
                return True
        for dl in self.get_active_downloads():
            if not isinstance(dl, dict):
                continue
            try:
                if int(dl.get("anime_id") or 0) != int(anime_id):
                    continue
            except (TypeError, ValueError):
                continue
            prog = dl.get("progress")
            if isinstance(prog, (int, float)) and float(prog) >= 0.999:
                return True
        return False

    def _sync_watching_tag_from_library(self, anime_id: int, user_id: int) -> None:
        """Promote ``NONE`` / ``WATCHLIST`` to ``WATCHING`` when local episodes exist."""
        try:
            has_files = bool(self._list_episode_files_core(anime_id))
            if not has_files and not self._has_completed_torrent(anime_id):
                return
            state = self._user_actions_port.get_user_state(anime_id, user_id)
            tag = str(state.get("tag") or "NONE").upper()
            if tag in ("NONE", "WATCHLIST"):
                self._user_actions_port.set_tag(anime_id, "WATCHING", user_id)
        except Exception:  # noqa: BLE001
            return

    def list_episode_files(
        self, anime_id: int, user_id: int | None = None
    ) -> list[EpisodeFileDTO]:
        core = self._list_episode_files_core(anime_id)
        if user_id is None:
            return core
        progress = self._user_actions_port.get_episode_progress_map(anime_id, user_id)
        merged: list[EpisodeFileDTO] = []
        for row in core:
            p = progress.get(row.file_id) or {}
            st = str(p.get("status") or "UNSEEN").upper()
            pos_raw = p.get("position_seconds")
            try:
                pos = float(pos_raw) if pos_raw is not None else None
            except (TypeError, ValueError):
                pos = None
            merged.append(
                EpisodeFileDTO(
                    file_id=row.file_id,
                    title=row.title,
                    path=row.path,
                    size_bytes=row.size_bytes,
                    season=row.season,
                    episode=row.episode,
                    audio_tracks=list(row.audio_tracks or []),
                    subtitle_tracks=list(row.subtitle_tracks or []),
                    watch_status=st,
                    position_seconds=pos,
                    duration_seconds=row.duration_seconds,
                )
            )
        self._sync_watching_tag_from_library(anime_id, user_id)
        return merged

    def set_episode_progress(
        self,
        anime_id: int,
        user_id: int,
        file_id: str,
        status: str,
        position_seconds: float | None = None,
    ) -> None:
        self._user_actions_port.set_episode_progress(
            anime_id, user_id, file_id, status, position_seconds=position_seconds
        )
        self._sync_watching_tag_from_library(anime_id, user_id)

    def delete_episode_file(self, anime_id: int, file_id: str, user_id: int) -> bool:
        media = self._require_media_streaming()
        ok = bool(media.delete_episode_file(anime_id, file_id))
        if ok:
            self._user_actions_port.delete_episode_progress(anime_id, user_id, file_id)
            self._sync_watching_tag_from_library(anime_id, user_id)
        return ok

    def create_playback_session(
        self,
        anime_id: int,
        file_id: str,
        *,
        client_host: str = "",
        ttl_seconds: int = 900,
        audio_track: int | None = None,
        subtitle_track: int | None = None,
        start_time_seconds: float | None = None,
    ) -> PlaybackSessionDTO:
        media = self._require_media_streaming()
        if not str(file_id or "").strip():
            raise ValidationError("A file_id is required to start playback.")
        return media.create_session(
            CreatePlaybackSessionCommand(
                anime_id=anime_id,
                file_id=file_id.strip(),
                client_host=client_host,
                ttl_seconds=ttl_seconds,
                audio_track=audio_track,
                subtitle_track=subtitle_track,
                start_time_seconds=start_time_seconds,
            )
        )

    def get_playback_session(self, session_id: str) -> PlaybackSessionDTO | None:
        media = self._require_media_streaming()
        return media.get_session(session_id)

    def heartbeat_playback_session(self, session_id: str) -> PlaybackSessionDTO:
        media = self._require_media_streaming()
        return media.heartbeat(HeartbeatPlaybackSessionCommand(session_id=session_id))

    def stop_playback_session(self, session_id: str) -> None:
        media = self._require_media_streaming()
        media.stop_session(StopPlaybackSessionCommand(session_id=session_id))

    def resolve_playback_media_path(
        self,
        *,
        session_id: str,
        token: str,
        segment_name: str | None = None,
    ) -> tuple[PlaybackSessionDTO, str]:
        media = self._require_media_streaming()
        return media.resolve_media_path(
            GetPlaybackSessionQuery(
                session_id=session_id,
                token=token,
                segment_name=segment_name,
            )
        )

    def cleanup_playback_sessions(self) -> None:
        if self._media_streaming is None:
            return
        self._media_streaming.cleanup_stale_sessions()

    def _require_media_streaming(self) -> PlaybackService:
        if self._media_streaming is None:
            raise ValidationError("Media streaming is not configured.")
        return self._media_streaming


__all__ = ["AnimeApplicationService"]
