"""Protocol definitions for application layer dependencies.

This module is the canonical home of the port interfaces. The legacy
``backend.ports.interfaces`` module is a thin compatibility shim that
re-exports from here.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Protocol

from domain.entities import AnimeEntity
from shared.contracts import RepairStrategy


class CatalogIndexPort(Protocol):
    """Lookup and allocation of internal ids in ``indexList``."""

    def find_by_external(self, provider_key: str, external_id: int) -> Optional[int]:
        ...

    def get_external_ids(self, internal_id: int) -> Dict[str, int]:
        ...

    def backfill_external_ids(
        self, internal_id: int, external_ids: Mapping[str, int]
    ) -> None:
        ...

    def allocate(self, external_ids: Mapping[str, int]) -> int:
        ...


class CatalogMergePort(Protocol):
    """Consolidate duplicate catalogue rows across satellite tables."""

    def merge(self, duplicate_id: int, canonical_id: int) -> int:
        ...

    def repair_duplicates(
        self, *, strategy: RepairStrategy = RepairStrategy.PROVIDER_ID
    ) -> int:
        ...


class CatalogMappingPort(Protocol):
    """Cross-provider id lookups for catalogue enrichment."""

    def lookup_kitsu_mappings(self, kitsu_id: int) -> Dict[str, int]:
        ...

    def lookup_anilist_cross_ids(self, anilist_id: int) -> Dict[str, int]:
        ...

    def lookup_mal_cross_ids(self, mal_id: int) -> Dict[str, int]:
        ...


class AnimeRepositoryPort(Protocol):
    def search(self, query: str, limit: int = 50) -> list[AnimeEntity]:
        ...

    def list_anime(
        self,
        criteria: str,
        list_start: int,
        list_stop: int,
        hide_rated: Optional[bool],
        user_id: Optional[int],
    ) -> tuple[list[AnimeEntity], bool]:
        ...

    def list_by_airing_season(
        self,
        year: int,
        season: str,
        limit: int = 50,
    ) -> list[AnimeEntity]:
        ...

    def list_by_genre(
        self,
        genre: str | list[str],
        limit: int = 50,
    ) -> list[AnimeEntity]:
        ...

    def list_by_top_category(
        self,
        category: str,
        limit: int = 50,
    ) -> list[AnimeEntity]:
        ...

    def get_anime(self, anime_id: int) -> Optional[AnimeEntity]:
        ...

    def anime_row_exists(self, anime_id: int) -> bool:
        ...

    def get_search_terms(self, anime_id: int) -> list[str]:
        ...

    def add_search_term(self, anime_id: int, term: str) -> bool:
        ...

    def remove_search_term(self, anime_id: int, term: str) -> bool:
        ...

    def get_disabled_search_titles(self, anime_id: int) -> list[str]:
        ...

    def disable_search_title(self, anime_id: int, title: str) -> bool:
        ...

    def enable_search_title(self, anime_id: int, title: str) -> bool:
        ...

    def get_settings(self) -> dict:
        ...

    def update_settings(self, updates: dict) -> dict:
        ...

    def get_relations(self, anime_id: int, relation_type: str = "anime") -> list[dict]:
        ...

    def get_anime_torrents(self, anime_id: int) -> list[dict]:
        ...

    def get_characters(self, anime_id: int) -> list[dict]:
        ...

    def get_character(self, character_id: int) -> Optional[dict]:
        ...

    def get_anime_pictures(self, anime_id: int) -> list[dict]:
        ...

    def get_anime_pictures_batch(self, anime_ids: list[int]) -> dict[int, list[dict]]:
        ...

    def refresh_anime_characters(self, anime_id: int) -> list[dict]:
        ...

    def refresh_character(self, character_id: int) -> dict:
        ...

    def refresh_anime_pictures(self, anime_id: int) -> list[dict]:
        ...


class AnimeHydrationPort(Protocol):
    """Fetch and persist metadata for orphan catalogue rows."""

    def hydrate_anime(self, catalog_id: int) -> bool:
        ...

    def catalog_id_exists(self, catalog_id: int) -> bool:
        ...


class MetadataProviderPort(Protocol):
    def search(self, query: str, limit: int = 50) -> list[AnimeEntity]:
        ...

    def browse_season(
        self, year: int, season: str, limit: int = 50
    ) -> list[AnimeEntity]:
        ...

    def stream_browse_season(self, year: int, season: str, limit: int = 50):
        ...

    def browse_genre(
        self, genre: str | list[str], limit: int = 50
    ) -> list[AnimeEntity]:
        ...

    def stream_browse_genre(self, genre: str | list[str], limit: int = 50):
        ...

    def browse_top(
        self, category: str, limit: int = 50
    ) -> list[AnimeEntity]:
        ...

    def stream_browse_top(self, category: str, limit: int = 50):
        ...


class DownloadPort(Protocol):
    def start_download(
        self,
        anime_id: int,
        url: str | None = None,
        hash_value: str | None = None,
        user_id: int | None = None,
    ) -> bool:
        ...

    def get_download_progress(self, anime_id: int) -> dict:
        ...

    def cancel_download(self, anime_id: int) -> bool:
        ...

    def get_active_downloads(self) -> list[dict]:
        ...

    def get_torrents_overview(self) -> dict[str, list[dict]]:
        """Optional unified view of every torrent (active, seeding, completed).

        Implementations should return a mapping with the keys
        ``active``, ``seeding``, ``completed``, ``error`` and
        ``other``; each value is a list of dicts shaped like
        :meth:`get_active_downloads` entries plus a ``category`` /
        ``up_speed`` field. The application service degrades to a
        ``{category: get_active_downloads()}`` shape when a port does
        not implement this method.
        """
        ...

    def search_torrents(
        self,
        terms: list[str],
        profile: str = "interactive",
        limit: int | None = None,
        allow_nsfw: bool = False,
    ) -> list[dict]:
        ...

    def stream_torrents(
        self,
        terms: list[str],
        profile: str = "interactive",
        limit: int | None = None,
        allow_nsfw: bool = False,
    ):
        """Optional streaming variant of :meth:`search_torrents`.

        ``limit`` overrides the per-term row cap for this request. When
        omitted, the active search profile default is used. There is no
        separate global result ceiling.
        """
        ...

    def mark_torrents_deleted_for_removed_file(
        self, anime_id: int, deleted_path: str
    ) -> int:
        """Mark torrents owning ``deleted_path`` as deleted and stop client restore."""
        ...

    def mark_torrents_deleted_for_seen_anime(self, anime_id: int) -> int:
        """Stop downloads and mark torrents deleted when anime is tagged SEEN."""
        ...


class UserActionsPort(Protocol):
    def set_tag(self, anime_id: int, tag: str, user_id: int) -> None:
        ...

    def set_like(self, anime_id: int, liked: bool, user_id: int) -> None:
        ...

    def mark_seen(self, anime_id: int, file_name: str, user_id: int) -> None:
        ...

    def get_user_state(self, anime_id: int, user_id: int) -> dict:
        ...

    def list_anime_ids_with_tag(self, tag: str) -> list[int]:
        """Return anime IDs whose ``user_tags.tag`` equals ``tag`` (any user)."""
        ...

    def get_episode_progress_map(self, anime_id: int, user_id: int) -> dict[str, dict[str, Any]]:
        """Return ``file_id`` → ``{"status", "position_seconds"}`` for one anime."""
        ...

    def set_episode_progress(
        self,
        anime_id: int,
        user_id: int,
        file_id: str,
        status: str,
        position_seconds: float | None = None,
    ) -> None:
        """Persist per-file watch state (``UNSEEN`` / ``IN_PROGRESS`` / ``SEEN``)."""
        ...

    def delete_episode_progress(
        self, anime_id: int, user_id: int, file_id: str
    ) -> None:
        """Remove stored progress when the underlying file is deleted."""
        ...


class MediaLibraryPort(Protocol):
    def list_episode_files(self, anime_id: int) -> list[dict[str, Any]]:
        """Return locally available episode files for one anime."""
        ...

    def delete_episode_file(self, anime_id: int, file_id: str) -> bool:
        """Delete one on-disk episode file resolved from ``file_id``. Return success."""
        ...

    def get_stream_cache_root(self) -> str:
        """Return the filesystem root used to store HLS artifacts."""
        ...


class MediaTranscoderPort(Protocol):
    def ensure_hls_session(
        self,
        *,
        session_id: str,
        source_path: str,
        output_dir: str,
        audio_track: int | None = None,
        subtitle_track: int | None = None,
        start_segment_index: int = 0,
        segment_seconds: int | None = None,
        duration_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Start (or reuse) a transcoding session and return artifact metadata.

        ``start_segment_index`` lets the caller restart encoding from an
        arbitrary segment offset (used to satisfy a user seek that
        landed beyond what ffmpeg has produced so far). When the value
        differs from the active session's offset, implementations should
        terminate the current ffmpeg process and spawn a fresh one
        seeking to ``start_segment_index * segment_seconds`` while
        preserving segment numbering and timestamps so that the
        resulting .ts files line up with the canonical playlist.
        """
        ...

    def probe_media_tracks(self, source_path: str) -> dict[str, list[dict[str, Any]]]:
        """Return available audio/subtitle tracks for source_path."""
        ...

    def probe_media_duration(self, source_path: str) -> float:
        """Return the total duration of ``source_path`` in seconds.

        Returns ``0.0`` when the duration cannot be determined (e.g. a
        live stream or a container that ffprobe cannot read). Callers
        are expected to treat ``0.0`` as "unknown" and fall back to a
        live/event-style playlist rather than a VOD playlist.
        """
        ...

    def stop_hls_session(self, session_id: str) -> None:
        ...


__all__ = [
    "CatalogIndexPort",
    "CatalogMergePort",
    "CatalogMappingPort",
    "AnimeRepositoryPort",
    "AnimeHydrationPort",
    "MetadataProviderPort",
    "DownloadPort",
    "UserActionsPort",
    "MediaLibraryPort",
    "MediaTranscoderPort",
]
