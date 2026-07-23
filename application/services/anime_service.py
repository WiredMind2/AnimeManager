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
from application.playback.contract import SESSION_TTL_SECONDS
from application.playback.file_ids import find_episode_by_file_id, progress_for_file_id
from application.services.anime_hydration import (
    PRIORITY_PREFETCH,
    AnimeDetailsResult,
    AnimeHydrationService,
)
from domain.dto import (
    AnimeListRequest,
    AnimeListResponse,
    DownloadRequest,
    GenreBrowseRequest,
    SearchRequest,
    SeasonBrowseRequest,
    TopBrowseRequest,
)
from domain.entities import AnimeEntity
from domain.errors import NotFoundError, ValidationError
from domain.policies import (
    is_anime_metadata_missing,
    normalize_airing_season,
    normalize_genre,
    normalize_genres,
    normalize_search_query,
    normalize_top_category,
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
        hydration_service: AnimeHydrationService | None = None,
    ) -> None:
        self._anime_repository = anime_repository
        self._metadata_provider = metadata_provider
        self._download_port = download_port
        self._user_actions_port = user_actions_port
        self._media_streaming = media_streaming_service
        self._hydration = hydration_service

    def _prefetch_metadata(
        self,
        entities,
        *,
        priority: int = PRIORITY_PREFETCH,
    ) -> None:
        if self._hydration is None:
            return
        self._hydration.schedule_entities(entities, priority=priority)

    # Page-size / depth caps for merged browse+search lists.
    _BROWSE_MAX_LIMIT = 100
    _BROWSE_MAX_OFFSET = 2000

    def _prefetch_entity(
        self, entity: AnimeEntity, *, priority: int = PRIORITY_PREFETCH
    ) -> None:
        if entity is None:
            return
        if not is_anime_metadata_missing(entity, catalog_id=entity.id):
            return
        self._prefetch_metadata([entity], priority=priority)

    def _normalize_page(self, offset: int, limit: int) -> tuple[int, int, int]:
        """Return ``(offset, limit, fetch_count)`` for over-fetch paging."""
        safe_offset = max(0, int(offset or 0))
        if safe_offset > self._BROWSE_MAX_OFFSET:
            raise ValidationError(
                f"offset must be between 0 and {self._BROWSE_MAX_OFFSET}."
            )
        safe_limit = max(1, min(int(limit or 50), self._BROWSE_MAX_LIMIT))
        return safe_offset, safe_limit, safe_offset + safe_limit + 1

    @staticmethod
    def _slice_page(
        merged: list[AnimeEntity], offset: int, limit: int
    ) -> AnimeListResponse:
        has_next = len(merged) > offset + limit
        return AnimeListResponse(
            items=merged[offset : offset + limit],
            has_next=has_next,
        )

    def _merge_unique(
        self,
        sources,
        *,
        fetch_count: int,
    ) -> list[AnimeEntity]:
        """Deduplicate entities from callables/iterables up to ``fetch_count``."""
        seen_ids: set[int] = set()
        merged: list[AnimeEntity] = []
        for source in sources:
            if len(merged) >= fetch_count:
                break
            batch = source() if callable(source) else source
            if batch is None:
                continue
            for entity in batch:
                if entity is None or entity.id <= 0 or entity.id in seen_ids:
                    continue
                seen_ids.add(entity.id)
                merged.append(entity)
                if len(merged) >= fetch_count:
                    break
        return merged

    def search_anime(self, request: SearchRequest) -> AnimeListResponse:
        query = normalize_search_query(request.query)
        if len(query) < 3:
            raise ValidationError(
                "Search query must contain at least 3 characters."
            )

        offset, limit, fetch_count = self._normalize_page(
            request.offset, request.limit
        )

        matched_genre: str | None = None
        try:
            matched_genre = normalize_genre(query)
        except ValidationError:
            matched_genre = None

        sources = []
        if matched_genre is not None:
            sources.append(
                lambda g=matched_genre: self._anime_repository.list_by_genre(
                    g, fetch_count
                )
            )
        sources.append(
            lambda: self._anime_repository.search(query, fetch_count)
        )
        sources.append(
            lambda: self._metadata_provider.search(query, fetch_count)
        )

        merged = self._merge_unique(sources, fetch_count=fetch_count)
        page = self._slice_page(merged, offset, limit)
        self._prefetch_metadata(page.items)
        return page

    def stream_search_anime(self, request: SearchRequest):
        """Yield :class:`AnimeEntity` results progressively for one page.

        Emission order:
        1. The local catalog (fast, single batch) -- so the UI shows
           something within a frame even before any external provider
           replies.
        2. Each remote provider as it completes, deduplicated against
           what has already been emitted.

        When ``offset`` is set, earlier ranks are skipped so callers can
        stream page 2+ without materializing the full list first.
        """
        query = normalize_search_query(request.query)
        if len(query) < 3:
            raise ValidationError(
                "Search query must contain at least 3 characters."
            )

        offset, limit, fetch_count = self._normalize_page(
            request.offset, request.limit
        )
        seen_ids: set[int] = set()
        skipped = 0
        yielded = 0

        def _emit(entity: AnimeEntity):
            nonlocal skipped, yielded
            if entity is None or entity.id <= 0 or entity.id in seen_ids:
                return False
            seen_ids.add(entity.id)
            if skipped < offset:
                skipped += 1
                return False
            if yielded >= limit:
                return False
            self._prefetch_entity(entity)
            yielded += 1
            return True

        matched_genre: str | None = None
        try:
            matched_genre = normalize_genre(query)
        except ValidationError:
            matched_genre = None

        if matched_genre is not None:
            for entity in self._anime_repository.list_by_genre(
                matched_genre, fetch_count
            ):
                if _emit(entity):
                    yield entity
                if yielded >= limit:
                    return

        for entity in self._anime_repository.search(query, fetch_count):
            if _emit(entity):
                yield entity
            if yielded >= limit:
                return

        streamer = getattr(self._metadata_provider, "stream_search", None)
        if callable(streamer):
            for entity in streamer(query, fetch_count):
                if _emit(entity):
                    yield entity
                if yielded >= limit:
                    return
            return

        for entity in self._metadata_provider.search(query, fetch_count):
            if _emit(entity):
                yield entity
            if yielded >= limit:
                return

    def browse_season(self, request: SeasonBrowseRequest) -> AnimeListResponse:
        year = validate_season_year(request.year)
        season = normalize_airing_season(request.season)
        offset, limit, fetch_count = self._normalize_page(
            request.offset, request.limit
        )

        sources = [
            lambda: self._anime_repository.list_by_airing_season(
                year, season, fetch_count
            ),
        ]
        browser = getattr(self._metadata_provider, "browse_season", None)
        if callable(browser):
            sources.append(lambda: browser(year, season, fetch_count))
        else:
            sources.append(
                lambda: self._metadata_provider.search(
                    f"{season} {year}", fetch_count
                )
            )

        merged = self._merge_unique(sources, fetch_count=fetch_count)
        page = self._slice_page(merged, offset, limit)
        self._prefetch_metadata(page.items)
        return page

    def stream_browse_season(self, request: SeasonBrowseRequest):
        """Yield season browse results: local catalog first, then providers."""
        year = validate_season_year(request.year)
        season = normalize_airing_season(request.season)
        offset, limit, fetch_count = self._normalize_page(
            request.offset, request.limit
        )
        seen_ids: set[int] = set()
        skipped = 0
        yielded = 0

        def _emit(entity: AnimeEntity):
            nonlocal skipped, yielded
            if entity is None or entity.id <= 0 or entity.id in seen_ids:
                return False
            seen_ids.add(entity.id)
            if skipped < offset:
                skipped += 1
                return False
            if yielded >= limit:
                return False
            self._prefetch_entity(entity)
            yielded += 1
            return True

        for entity in self._anime_repository.list_by_airing_season(
            year, season, fetch_count
        ):
            if _emit(entity):
                yield entity
            if yielded >= limit:
                return

        streamer = getattr(self._metadata_provider, "stream_browse_season", None)
        if callable(streamer):
            for entity in streamer(year, season, fetch_count):
                if _emit(entity):
                    yield entity
                if yielded >= limit:
                    return
            return

        browser = getattr(self._metadata_provider, "browse_season", None)
        if callable(browser):
            for entity in browser(year, season, fetch_count):
                if _emit(entity):
                    yield entity
                if yielded >= limit:
                    return
            return

        for entity in self._metadata_provider.search(
            f"{season} {year}", fetch_count
        ):
            if _emit(entity):
                yield entity
            if yielded >= limit:
                return

    def browse_genre(self, request: GenreBrowseRequest) -> AnimeListResponse:
        genres = normalize_genres(request.genres)
        offset, limit, fetch_count = self._normalize_page(
            request.offset, request.limit
        )

        sources = [
            lambda: self._anime_repository.list_by_genre(genres, fetch_count),
        ]
        browser = getattr(self._metadata_provider, "browse_genre", None)
        if callable(browser):
            sources.append(lambda: browser(genres, fetch_count))
        else:
            sources.append(
                lambda: self._metadata_provider.search(
                    ", ".join(genres), fetch_count
                )
            )

        merged = self._merge_unique(sources, fetch_count=fetch_count)
        page = self._slice_page(merged, offset, limit)
        self._prefetch_metadata(page.items)
        return page

    def stream_browse_genre(self, request: GenreBrowseRequest):
        """Yield genre browse results: local catalog first, then providers."""
        genres = normalize_genres(request.genres)
        offset, limit, fetch_count = self._normalize_page(
            request.offset, request.limit
        )
        seen_ids: set[int] = set()
        skipped = 0
        yielded = 0

        def _emit(entity: AnimeEntity):
            nonlocal skipped, yielded
            if entity is None or entity.id <= 0 or entity.id in seen_ids:
                return False
            seen_ids.add(entity.id)
            if skipped < offset:
                skipped += 1
                return False
            if yielded >= limit:
                return False
            self._prefetch_entity(entity)
            yielded += 1
            return True

        for entity in self._anime_repository.list_by_genre(genres, fetch_count):
            if _emit(entity):
                yield entity
            if yielded >= limit:
                return

        streamer = getattr(self._metadata_provider, "stream_browse_genre", None)
        if callable(streamer):
            for entity in streamer(genres, fetch_count):
                if _emit(entity):
                    yield entity
                if yielded >= limit:
                    return
            return

        browser = getattr(self._metadata_provider, "browse_genre", None)
        if callable(browser):
            for entity in browser(genres, fetch_count):
                if _emit(entity):
                    yield entity
                if yielded >= limit:
                    return
            return

        for entity in self._metadata_provider.search(
            ", ".join(genres), fetch_count
        ):
            if _emit(entity):
                yield entity
            if yielded >= limit:
                return

    def browse_top(self, request: TopBrowseRequest) -> AnimeListResponse:
        category = normalize_top_category(request.category)
        offset, limit, fetch_count = self._normalize_page(
            request.offset, request.limit
        )

        sources = [
            lambda: self._anime_repository.list_by_top_category(
                category, fetch_count
            ),
        ]
        browser = getattr(self._metadata_provider, "browse_top", None)
        if callable(browser):
            sources.append(lambda: browser(category, fetch_count))

        merged = self._merge_unique(sources, fetch_count=fetch_count)
        page = self._slice_page(merged, offset, limit)
        self._prefetch_metadata(page.items)
        return page

    def stream_browse_top(self, request: TopBrowseRequest):
        """Yield top browse results: local catalog first, then providers."""
        category = normalize_top_category(request.category)
        offset, limit, fetch_count = self._normalize_page(
            request.offset, request.limit
        )
        seen_ids: set[int] = set()
        skipped = 0
        yielded = 0

        def _emit(entity: AnimeEntity):
            nonlocal skipped, yielded
            if entity is None or entity.id <= 0 or entity.id in seen_ids:
                return False
            seen_ids.add(entity.id)
            if skipped < offset:
                skipped += 1
                return False
            if yielded >= limit:
                return False
            self._prefetch_entity(entity)
            yielded += 1
            return True

        for entity in self._anime_repository.list_by_top_category(
            category, fetch_count
        ):
            if _emit(entity):
                yield entity
            if yielded >= limit:
                return

        streamer = getattr(self._metadata_provider, "stream_browse_top", None)
        if callable(streamer):
            for entity in streamer(category, fetch_count):
                if _emit(entity):
                    yield entity
                if yielded >= limit:
                    return
            return

        browser = getattr(self._metadata_provider, "browse_top", None)
        if callable(browser):
            for entity in browser(category, fetch_count):
                if _emit(entity):
                    yield entity
                if yielded >= limit:
                    return

    def get_anime_list(self, request: AnimeListRequest) -> AnimeListResponse:
        items, has_next = self._anime_repository.list_anime(
            criteria=request.filter,
            list_start=request.list_start,
            list_stop=request.list_stop,
            hide_rated=request.hide_rated,
            user_id=request.user_id,
        )
        self._prefetch_metadata(items)
        return AnimeListResponse(items=items, has_next=has_next)

    def get_anime_details(self, anime_id: int) -> AnimeDetailsResult:
        anime_id = int(anime_id)
        entity = self._anime_repository.get_anime(anime_id)
        if entity is None:
            if (
                self._hydration is None
                or not self._hydration.catalog_id_exists(anime_id)
            ):
                raise NotFoundError(f"Anime with id={anime_id} not found")
            entity = AnimeEntity(id=anime_id, title="")

        pending = is_anime_metadata_missing(entity, catalog_id=anime_id)
        can_hydrate = (
            self._hydration is not None
            and self._hydration.catalog_id_exists(anime_id)
        )
        refreshing = (
            self._hydration.is_detail_refreshing(anime_id)
            if self._hydration is not None
            else False
        )
        if pending and can_hydrate and not refreshing:
            self._hydration.kickoff_detail_refresh(
                anime_id,
                after_hydrate=self._refresh_detail_extras,
            )
            refreshing = True
        return AnimeDetailsResult(
            entity=entity,
            # Only advertise pending when hydration can actually refresh.
            metadata_pending=pending and can_hydrate,
            metadata_refreshing=refreshing,
        )

    def refresh_anime_details(self, anime_id: int) -> dict:
        anime_id = int(anime_id)
        if self._hydration is None:
            return {"accepted": False, "anime_id": anime_id}
        if not self._hydration.catalog_id_exists(anime_id):
            # DB row may exist without an indexList entry; do not 404.
            if self._anime_repository.get_anime(anime_id) is None:
                raise NotFoundError(f"Anime with id={anime_id} not found")
            return {"accepted": False, "anime_id": anime_id}
        self._hydration.kickoff_detail_refresh(
            anime_id,
            after_hydrate=self._refresh_detail_extras,
        )
        return {"accepted": True, "anime_id": anime_id}

    def _refresh_detail_extras(self, anime_id: int) -> None:
        try:
            self.refresh_anime_characters(anime_id)
        except Exception:
            pass
        try:
            self.refresh_anime_pictures(anime_id)
        except Exception:
            pass

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
            source=getattr(request, "source", None),
        )

    def get_download_progress(self, anime_id: int) -> dict:
        return self._download_port.get_download_progress(anime_id)

    def cancel_download(self, anime_id: int) -> bool:
        return self._download_port.cancel_download(anime_id)

    def pause_torrent(self, hash_value: str) -> bool:
        return self._download_port.pause_torrent(hash_value)

    def resume_torrent(self, hash_value: str) -> bool:
        return self._download_port.resume_torrent(hash_value)

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
        limit: int | None = None,
        allow_nsfw: bool = False,
    ) -> list[dict]:
        sanitized = self._sanitize_terms(terms)
        return self._download_port.search_torrents(
            sanitized, profile=profile, limit=limit, allow_nsfw=allow_nsfw
        )

    def stream_torrents(
        self,
        terms: list[str],
        profile: str = "interactive",
        limit: int | None = None,
        allow_nsfw: bool = False,
    ):
        """Yield torrent dicts progressively as engines emit them.

        Falls back to :meth:`search_torrents` (returning the materialized
        list as a single batch) when the active download port has not
        implemented streaming. Callers can therefore consume the result
        uniformly with a ``for row in ...`` loop.

        ``limit`` is a per-term row cap override; omit to use the profile
        default. Total rows scale with the number of planned terms.
        """
        sanitized = self._sanitize_terms(terms)
        streamer = getattr(self._download_port, "stream_torrents", None)
        if callable(streamer):
            yield from streamer(
                sanitized, profile=profile, limit=limit, allow_nsfw=allow_nsfw
            )
            return
        for row in self._download_port.search_torrents(
            sanitized, profile=profile, limit=limit, allow_nsfw=allow_nsfw
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
        if str(tag or "").strip().upper() == "SEEN":
            self._remove_torrents_for_seen_anime(anime_id)

    def set_like(self, anime_id: int, user_id: int, liked: bool = True) -> None:
        self._user_actions_port.set_like(anime_id, liked, user_id)

    def set_auto_download(
        self, anime_id: int, user_id: int, enabled: bool = True
    ) -> None:
        setter = getattr(self._user_actions_port, "set_auto_download", None)
        if not callable(setter):
            return
        setter(anime_id, enabled, user_id)

    def mark_seen(self, anime_id: int, file_name: str, user_id: int) -> None:
        self._user_actions_port.mark_seen(anime_id, file_name, user_id)
        self._remove_torrents_for_seen_anime(anime_id)

    def _remove_torrents_for_seen_anime(self, anime_id: int) -> None:
        marker = getattr(
            self._download_port,
            "mark_torrents_deleted_for_seen_anime",
            None,
        )
        if not callable(marker):
            return
        try:
            marker(anime_id)
        except Exception:
            pass

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
        result = self._anime_repository.update_settings(updates)
        self._apply_libtorrent_max_connections(updates)
        return result

    def _apply_libtorrent_max_connections(self, updates: dict) -> None:
        tm_updates = updates.get("torrent_managers")
        if not isinstance(tm_updates, dict):
            return
        lib_updates = tm_updates.get("LibTorrent")
        if not isinstance(lib_updates, dict) or "max_connections" not in lib_updates:
            return
        apply = getattr(self._download_port, "apply_max_connections", None)
        if not callable(apply):
            return
        try:
            apply(lib_updates.get("max_connections"))
        except Exception:
            pass

    @staticmethod
    def _normalize_relation_row(row: dict) -> dict:
        rel_id = row.get("rel_id") or row.get("anime_id")
        relation_name = row.get("relation") or row.get("name")
        media_type = row.get("media_type") or row.get("type") or "anime"
        return {
            "id": row.get("id"),
            "rel_id": rel_id,
            "anime_id": rel_id,
            "type": media_type,
            "media_type": media_type,
            "name": relation_name,
            "relation": relation_name,
            "title": row.get("title"),
            "picture": row.get("picture"),
            "status": row.get("status"),
            "date_from": row.get("date_from"),
            "episodes": row.get("episodes"),
        }

    def get_relations(self, anime_id: int, relation_type: str = "anime") -> list[dict]:
        rows = self._anime_repository.get_relations(anime_id, relation_type)
        return [self._normalize_relation_row(row) for row in rows if isinstance(row, dict)]

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

    def get_anime_pictures_batch(self, anime_ids: list[int]) -> dict[int, list[dict]]:
        getter = getattr(self._anime_repository, "get_anime_pictures_batch", None)
        if not callable(getter):
            out: dict[int, list[dict]] = {}
            for anime_id in anime_ids or []:
                out[int(anime_id)] = self.get_anime_pictures(int(anime_id))
            return out
        return dict(getter(list(anime_ids) or []) or {})

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
            p = progress_for_file_id(progress, row.file_id)
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
        deleted_path = ""
        if self._media_streaming is not None:
            episodes = self._media_streaming.list_episode_files(
                ListEpisodeFilesQuery(anime_id=anime_id)
            )
            selected = find_episode_by_file_id(episodes, file_id)
            if selected is not None:
                deleted_path = str(selected.path or "").strip()
        ok = bool(media.delete_episode_file(anime_id, file_id))
        if ok:
            self._user_actions_port.delete_episode_progress(anime_id, user_id, file_id)
            self._sync_watching_tag_from_library(anime_id, user_id)
            if deleted_path:
                marker = getattr(
                    self._download_port,
                    "mark_torrents_deleted_for_removed_file",
                    None,
                )
                if callable(marker):
                    try:
                        marker(anime_id, deleted_path)
                    except Exception:
                        pass
        return ok

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
