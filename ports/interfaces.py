"""Protocol definitions for application layer dependencies.

This module is the canonical home of the port interfaces. The legacy
``backend.ports.interfaces`` module is a thin compatibility shim that
re-exports from here.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from domain.entities import AnimeEntity


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

    def get_anime(self, anime_id: int) -> Optional[AnimeEntity]:
        ...

    def get_search_terms(self, anime_id: int) -> list[str]:
        ...

    def add_search_term(self, anime_id: int, term: str) -> bool:
        ...

    def remove_search_term(self, anime_id: int, term: str) -> bool:
        ...

    def get_settings(self) -> dict:
        ...

    def update_settings(self, updates: dict) -> dict:
        ...

    def get_relations(self, anime_id: int, relation_type: str = "anime") -> list[dict]:
        ...

    def get_anime_torrents(self, anime_id: int) -> list[dict]:
        ...


class MetadataProviderPort(Protocol):
    def search(self, query: str, limit: int = 50) -> list[AnimeEntity]:
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
        limit: int = 200,
    ) -> list[dict]:
        ...

    def stream_torrents(
        self,
        terms: list[str],
        profile: str = "interactive",
        limit: int = 200,
    ):
        """Optional streaming variant of :meth:`search_torrents`.

        Implementations should yield each result dict as soon as it is
        produced by the underlying search engines. The application
        service degrades to :meth:`search_torrents` automatically when
        a port has not implemented this method.
        """
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
    "AnimeRepositoryPort",
    "MetadataProviderPort",
    "DownloadPort",
    "UserActionsPort",
    "MediaLibraryPort",
    "MediaTranscoderPort",
]
