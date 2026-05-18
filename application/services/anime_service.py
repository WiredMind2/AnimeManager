"""Canonical AnimeApplicationService.

This module is the canonical home of the application-level use-case
orchestrator. The legacy ``backend.application.service`` module is a
thin compatibility shim that re-exports from here.
"""

from __future__ import annotations

import base64
import binascii
import os
from urllib.parse import parse_qs, urlparse

from application.commands import (
    CreatePlaybackSessionCommand,
    HeartbeatPlaybackSessionCommand,
    StopPlaybackSessionCommand,
)
from application.dto import EpisodeFileDTO, PlaybackSessionDTO
from application.queries import GetPlaybackSessionQuery, ListEpisodeFilesQuery
from application.services.media_streaming_service import MediaStreamingService
from domain.dto import (
    AnimeListRequest,
    AnimeListResponse,
    DownloadRequest,
    SearchRequest,
)
from domain.entities import AnimeEntity
from domain.errors import NotFoundError, ValidationError
from domain.policies import normalize_search_query
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
        media_streaming_service: MediaStreamingService | None = None,
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

        local_results = self._anime_repository.search(query, request.limit)
        if local_results:
            return local_results

        return self._metadata_provider.search(query, request.limit)

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

    def refresh_anime_metadata(self, anime_id: int) -> AnimeEntity:
        """Best-effort metadata refresh for one anime."""
        refresher = getattr(self._metadata_provider, "refresh_anime", None)
        if callable(refresher):
            try:
                refreshed = refresher(anime_id)
            except Exception:
                refreshed = None
            if isinstance(refreshed, AnimeEntity):
                return refreshed
        return self.get_anime_details(anime_id)

    def delete_anime(self, anime_id: int) -> bool:
        remover = getattr(self._anime_repository, "delete_anime", None)
        if not callable(remover):
            raise ValidationError("Anime deletion is not supported by the repository.")
        return bool(remover(anime_id))

    def get_anime_folder(self, anime_id: int) -> str:
        getter = getattr(self._anime_repository, "get_anime_folder", None)
        if not callable(getter):
            return ""
        try:
            return str(getter(anime_id) or "")
        except Exception:
            return ""

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

    def redownload(self, anime_id: int) -> int:
        redownload = getattr(self._download_port, "redownload", None)
        if not callable(redownload):
            return 0
        try:
            return int(redownload(anime_id) or 0)
        except Exception:
            return 0

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
        rows = self._download_port.search_torrents(
            sanitized, profile=profile, limit=limit
        )
        deduped: list[dict] = []
        seen_hashes: set[str] = set()
        for row in rows or []:
            if not isinstance(row, dict):
                deduped.append(row)
                continue
            normalized_hash = self._normalized_torrent_hash(row)
            if normalized_hash:
                if normalized_hash in seen_hashes:
                    continue
                seen_hashes.add(normalized_hash)
            deduped.append(row)
        return deduped

    def stream_torrents(
        self,
        terms: list[str],
        profile: str = "interactive",
        limit: int = 200,
    ):
        """Iterate torrent dicts progressively as engines emit them.

        Falls back to :meth:`search_torrents` (returning the materialized
        list as a single batch) when the active download port has not
        implemented streaming. Callers can therefore consume the result
        uniformly with a ``for row in ...`` loop.
        """
        sanitized = self._sanitize_terms(terms)
        seen_hashes: set[str] = set()
        streamer = getattr(self._download_port, "stream_torrents", None)
        if callable(streamer):
            for row in streamer(sanitized, profile=profile, limit=limit):
                if not isinstance(row, dict):
                    yield row
                    continue
                normalized_hash = self._normalized_torrent_hash(row)
                if normalized_hash:
                    if normalized_hash in seen_hashes:
                        continue
                    seen_hashes.add(normalized_hash)
                yield row
            return
        for row in self._download_port.search_torrents(
            sanitized, profile=profile, limit=limit
        ):
            if not isinstance(row, dict):
                yield row
                continue
            normalized_hash = self._normalized_torrent_hash(row)
            if normalized_hash:
                if normalized_hash in seen_hashes:
                    continue
                seen_hashes.add(normalized_hash)
            yield row

    def _sanitize_terms(self, terms: list[str]) -> list[str]:
        if not terms:
            raise ValidationError("At least one search term is required.")
        sanitized = [str(term).strip() for term in terms if str(term).strip()]
        if not sanitized:
            raise ValidationError("At least one non-empty search term is required.")
        return sanitized

    def _normalized_torrent_hash(self, row: dict) -> str | None:
        # Prefer explicit hash fields; if absent, derive from the magnet link.
        # Return a canonical lowercase hex infohash so base32/hex variants
        # from different providers collapse to one identity.
        for key in ("hash", "infohash"):
            value = str(row.get(key) or "").strip()
            normalized = self._canonical_btih(value)
            if normalized:
                return normalized

        link = str(row.get("link") or "").strip()
        if not link:
            return None
        try:
            xt_values = parse_qs(urlparse(link).query).get("xt", [])
        except ValueError:
            return None
        for xt in xt_values:
            text = str(xt or "").strip()
            if not text.lower().startswith("urn:btih:"):
                continue
            normalized = self._canonical_btih(text[9:])
            if normalized:
                return normalized
        return None

    @staticmethod
    def _canonical_btih(raw_value: str) -> str | None:
        token = str(raw_value or "").strip()
        if not token:
            return None
        lowered = token.lower()
        if len(lowered) == 40 and all(ch in "0123456789abcdef" for ch in lowered):
            return lowered
        if len(token) == 32:
            try:
                decoded = base64.b32decode(token.upper(), casefold=True)
            except (binascii.Error, ValueError):
                decoded = None
            if decoded is not None and len(decoded) == 20:
                return decoded.hex()
        # Some providers expose truncated/non-standard hash strings.
        # Keep a normalized fallback so equal values still dedupe.
        if lowered and lowered.replace("-", "").isalnum():
            return lowered
        return None

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

    def get_last_torrent_search_query(self, anime_id: int) -> str | None:
        return self._anime_repository.get_last_torrent_search_query(anime_id)

    def set_last_torrent_search_query(self, anime_id: int, query: str) -> None:
        self._anime_repository.set_last_torrent_search_query(anime_id, query)

    def get_settings(self) -> dict:
        return self._anime_repository.get_settings()

    def update_settings(self, updates: dict) -> dict:
        if not isinstance(updates, dict) or not updates:
            raise ValidationError("Settings updates must be a non-empty object.")
        return self._anime_repository.update_settings(updates)

    def get_relations(self, anime_id: int, relation_type: str = "anime") -> list[dict]:
        return self._anime_repository.get_relations(anime_id, relation_type)

    def list_anime_characters(self, anime_id: int) -> list[dict]:
        return list(self._anime_repository.list_anime_characters(anime_id) or [])

    def get_anime_torrents(self, anime_id: int) -> list[dict]:
        getter = getattr(self._anime_repository, "get_anime_torrents", None)
        if not callable(getter):
            return []
        return list(getter(anime_id) or [])

    def _list_episode_files_core(self, anime_id: int) -> list[EpisodeFileDTO]:
        media = self._require_media_streaming()
        return media.list_episode_files(ListEpisodeFilesQuery(anime_id=anime_id))

    def _has_completed_torrent(self, anime_id: int) -> bool:
        for row in self.get_anime_torrents(anime_id):
            if not isinstance(row, dict):
                continue
            state = str(row.get("state") or "").upper()
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

    def redownload_episode(self, anime_id: int, file_id: str, user_id: int) -> bool:
        """Delete one local episode file and restart its persisted torrent."""
        target: EpisodeFileDTO | None = None
        for row in self.list_episode_files(anime_id, user_id=user_id):
            if row.file_id == str(file_id or "").strip():
                target = row
                break
        if target is None:
            return False
        hash_value = self._resolve_torrent_hash_for_episode(
            anime_id,
            str(target.path or ""),
            str(target.title or ""),
        )
        if not hash_value:
            return False
        if target.path:
            self.delete_episode_file(anime_id, file_id, user_id)
        return bool(
            self.start_download(
                DownloadRequest(
                    anime_id=anime_id,
                    hash_value=hash_value,
                    user_id=user_id,
                )
            )
        )

    def _resolve_torrent_hash_for_episode(
        self, anime_id: int, file_path: str, file_title: str
    ) -> str | None:
        """Match a local file to a torrent hash stored for this anime."""
        file_norm = self._norm_path_key(file_path)
        path_rows: list[tuple[str, str]] = []
        name_rows: list[tuple[str, str]] = []

        def ingest(row: dict) -> None:
            if not isinstance(row, dict):
                return
            try:
                if int(row.get("anime_id") or 0) != int(anime_id):
                    return
            except (TypeError, ValueError):
                return
            hash_value = str(row.get("hash") or row.get("hash_value") or "").strip()
            if not hash_value:
                return
            name = str(row.get("name") or "")
            torrent_path = str(row.get("path") or "").strip()
            if torrent_path:
                path_rows.append((hash_value, torrent_path))
            name_rows.append((hash_value, name))

        for row in self.get_active_downloads() or []:
            ingest(row)
        overview = self.get_torrents_overview() or {}
        if isinstance(overview, dict):
            for bucket in overview.values():
                if not isinstance(bucket, list):
                    continue
                for row in bucket:
                    ingest(row)

        if file_norm:
            for hash_value, torrent_path in path_rows:
                if self._path_under_torrent(file_norm, torrent_path):
                    return hash_value

        for row in self.get_anime_torrents(anime_id):
            if not isinstance(row, dict):
                continue
            hash_value = str(row.get("hash") or "").strip()
            if hash_value:
                name_rows.append((hash_value, str(row.get("name") or "")))

        title_fold = file_title.casefold().strip()
        stem_fold = os.path.splitext(file_title)[0].casefold().strip()
        if stem_fold or title_fold:
            for hash_value, name in name_rows:
                name_fold = name.casefold()
                if stem_fold and stem_fold in name_fold:
                    return hash_value
                if title_fold and title_fold in name_fold:
                    return hash_value

        unique_hashes = sorted({h for h, _ in name_rows if h})
        if len(unique_hashes) == 1:
            return unique_hashes[0]
        return None

    @staticmethod
    def _norm_path_key(path: str) -> str:
        text = str(path or "").strip()
        if not text:
            return ""
        try:
            return os.path.normcase(os.path.realpath(os.path.normpath(text)))
        except OSError:
            return os.path.normcase(os.path.normpath(text))

    @staticmethod
    def _path_under_torrent(file_norm: str, torrent_path: str) -> bool:
        if not file_norm or not torrent_path:
            return False
        torrent_norm = AnimeApplicationService._norm_path_key(torrent_path)
        if not torrent_norm:
            return False
        if file_norm == torrent_norm:
            return True
        sep = os.sep
        return file_norm.startswith(torrent_norm + sep)

    def delete_all_files(self, anime_id: int, user_id: int) -> int:
        media = self._require_media_streaming()
        files = media.list_episode_files(ListEpisodeFilesQuery(anime_id=anime_id))
        deleted = 0
        for row in files:
            if media.delete_episode_file(anime_id, row.file_id):
                self._user_actions_port.delete_episode_progress(
                    anime_id, user_id, row.file_id
                )
                deleted += 1
        if deleted:
            self._sync_watching_tag_from_library(anime_id, user_id)
        return deleted

    def delete_seen_episodes(self, anime_id: int, user_id: int) -> int:
        anime = self.get_anime_details(anime_id)
        last_seen = str(anime.last_seen or "").strip()
        if not last_seen:
            return 0
        media = self._require_media_streaming()
        files = media.list_episode_files(ListEpisodeFilesQuery(anime_id=anime_id))
        file_ids_to_delete: list[str] = []
        for row in files:
            if row.path == last_seen:
                break
            file_ids_to_delete.append(row.file_id)
        deleted = 0
        for file_id in file_ids_to_delete:
            if media.delete_episode_file(anime_id, file_id):
                self._user_actions_port.delete_episode_progress(
                    anime_id, user_id, file_id
                )
                deleted += 1
        if deleted:
            self._sync_watching_tag_from_library(anime_id, user_id)
        return deleted

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

    def _require_media_streaming(self) -> MediaStreamingService:
        if self._media_streaming is None:
            raise ValidationError("Media streaming is not configured.")
        return self._media_streaming


__all__ = ["AnimeApplicationService"]
