"""Startup library tag sync and SEEN purge."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from application.services.torrent_file_presence import folder_has_video_files
from application.services.torrent_index_repair import _parse_anime_id_from_folder_name
from ports.interfaces import MediaLibraryPort, UserActionsPort


@dataclass(frozen=True)
class PromoteWatchingResult:
    promoted: int = 0
    scanned: int = 0


@dataclass(frozen=True)
class PurgeSeenResult:
    purged_folders: int = 0
    purged_torrents: int = 0
    seen_candidates: int = 0


class LibraryStartupSyncService:
    """Promote local-library tags and purge on-disk SEEN anime at startup."""

    def __init__(
        self,
        *,
        user_actions: UserActionsPort,
        media_library: MediaLibraryPort,
        anime_path: str,
        list_anime_folders: Callable[[], list[str]] | None = None,
        cancel_download: Callable[[int], bool] | None = None,
        purge_torrents_for_anime: Callable[[int], int] | None = None,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        self._user_actions = user_actions
        self._media_library = media_library
        self._anime_path = str(anime_path or "").strip()
        self._list_anime_folders = list_anime_folders or self._default_list_folders
        self._cancel_download = cancel_download
        self._purge_torrents_for_anime = purge_torrents_for_anime
        self._log = log_fn or (lambda _msg: None)

    def _default_list_folders(self) -> list[str]:
        if not self._anime_path or not os.path.isdir(self._anime_path):
            return []
        try:
            return sorted(
                name
                for name in os.listdir(self._anime_path)
                if os.path.isdir(os.path.join(self._anime_path, name))
            )
        except OSError:
            return []

    def promote_watching_tags(self, user_id: int) -> PromoteWatchingResult:
        if not self._anime_path:
            return PromoteWatchingResult()

        promoted = 0
        scanned = 0
        for name in self._list_anime_folders():
            anime_id = _parse_anime_id_from_folder_name(name)
            if anime_id is None:
                continue
            folder = os.path.join(self._anime_path, name)
            if not folder_has_video_files(folder):
                continue
            scanned += 1
            try:
                state = self._user_actions.get_user_state(anime_id, user_id)
                tag = str(state.get("tag") or "NONE").upper()
                if tag not in ("NONE", "WATCHLIST"):
                    continue
                self._user_actions.set_tag(anime_id, "WATCHING", user_id)
                promoted += 1
            except Exception as exc:  # noqa: BLE001
                self._log(
                    f"promote_watching_tags failed for anime {anime_id}: "
                    f"{type(exc).__name__}: {exc}"
                )
        return PromoteWatchingResult(promoted=promoted, scanned=scanned)

    def purge_seen_libraries(self, user_id: int) -> PurgeSeenResult:
        if not self._anime_path:
            return PurgeSeenResult()

        try:
            seen_ids = self._user_actions.list_anime_ids_by_tag("SEEN", user_id)
        except Exception as exc:  # noqa: BLE001
            self._log(
                f"purge_seen_libraries tag lookup failed: "
                f"{type(exc).__name__}: {exc}"
            )
            return PurgeSeenResult()

        purged_folders = 0
        purged_torrents = 0
        for anime_id in seen_ids:
            try:
                state = self._user_actions.get_user_state(anime_id, user_id)
                if str(state.get("tag") or "").upper() != "SEEN":
                    continue
            except Exception as exc:  # noqa: BLE001
                self._log(
                    f"purge_seen_libraries state check failed for anime {anime_id}: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue

            if self._cancel_download is not None:
                try:
                    self._cancel_download(anime_id)
                except Exception as exc:  # noqa: BLE001
                    self._log(
                        f"purge_seen_libraries cancel failed for anime {anime_id}: "
                        f"{type(exc).__name__}: {exc}"
                    )

            if self._purge_torrents_for_anime is not None:
                try:
                    purged_torrents += int(self._purge_torrents_for_anime(anime_id) or 0)
                except Exception as exc:  # noqa: BLE001
                    self._log(
                        f"purge_seen_libraries torrent purge failed for anime {anime_id}: "
                        f"{type(exc).__name__}: {exc}"
                    )

            try:
                if self._media_library.delete_anime_folder(anime_id):
                    purged_folders += 1
            except Exception as exc:  # noqa: BLE001
                self._log(
                    f"purge_seen_libraries folder delete failed for anime {anime_id}: "
                    f"{type(exc).__name__}: {exc}"
                )

            try:
                self._user_actions.clear_episode_progress(anime_id, user_id)
            except Exception as exc:  # noqa: BLE001
                self._log(
                    f"purge_seen_libraries progress clear failed for anime {anime_id}: "
                    f"{type(exc).__name__}: {exc}"
                )

        return PurgeSeenResult(
            purged_folders=purged_folders,
            purged_torrents=purged_torrents,
            seen_candidates=len(seen_ids),
        )


__all__ = [
    "LibraryStartupSyncService",
    "PromoteWatchingResult",
    "PurgeSeenResult",
]
