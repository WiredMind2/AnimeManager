"""Download port adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dataclasses import replace

from adapters.file.local_episode_scanner import LocalEpisodeScanner
from adapters.persistence.user_actions_repository import UserActionsRepository
from adapters.search import SearchFacade
from adapters.search.config import load_profile
from application.services.database_manager import DatabaseManager
from application.services.download_manager import DownloadManager

if TYPE_CHECKING:
    from adapters.persistence.anime_repository import AnimeRepositoryAdapter


class DownloadAdapter:
    """Implements :class:`ports.interfaces.DownloadPort`."""

    def __init__(
        self,
        *,
        torrent_manager: Any,
        file_manager: Any,
        db_manager: DatabaseManager,
        scanner: LocalEpisodeScanner,
        user_actions: UserActionsRepository,
        repository: "AnimeRepositoryAdapter | None" = None,
    ) -> None:
        self._torrent_manager = torrent_manager
        self._file_manager = file_manager
        self._db_manager = db_manager
        self._user_actions = user_actions
        self._download_manager = DownloadManager()
        self._download_manager.set_torrent_manager(torrent_manager)
        self._download_manager.set_file_manager(file_manager)
        self._download_manager.set_watching_tag_callback(
            self._promote_watching_on_download_start
        )
        self._download_manager.set_database_manager(db_manager)
        self._scanner = scanner
        self._wire_libtorrent_restore(db_manager)

    def _wire_libtorrent_restore(self, db_manager: DatabaseManager) -> None:
        tm = self._torrent_manager
        if tm is None or getattr(tm, "name", None) != "LibTorrent":
            return
        setter = getattr(tm, "set_restore_callback", None)
        if not callable(setter):
            return

        def _rows() -> list[dict]:
            lister = getattr(db_manager, "list_torrents_for_restore", None)
            if not callable(lister):
                return []
            return lister()

        setter(_rows)

        status_setter = getattr(tm, "set_torrent_status_callback", None)
        if callable(status_setter):

            def _status(hash_value: str) -> str | None:
                getter = getattr(db_manager, "get_torrent_status", None)
                if not callable(getter):
                    return None
                return getter(hash_value)

            status_setter(_status)

        purge = getattr(tm, "purge_deleted_torrents", None)
        if callable(purge):
            try:
                purge()
            except Exception:
                pass

    def purge_deleted_torrents(self) -> int:
        tm = self._torrent_manager
        if tm is None or getattr(tm, "name", None) != "LibTorrent":
            return 0
        purge = getattr(tm, "purge_deleted_torrents", None)
        if not callable(purge):
            return 0
        try:
            return int(purge() or 0)
        except Exception:
            return 0

    def remove_torrents_from_client(self, hashes: list[str]) -> None:
        self._download_manager.remove_torrents_from_client(hashes, delete_files=False)

    def reconcile_deleted_torrents(self) -> int:
        return self._download_manager.reconcile_deleted_torrents(
            self._scanner.resolve_anime_folder
        )

    def consolidate_duplicate_anime_folders(self) -> int:
        """Merge on-disk library folders that share the same anime id."""
        anime_path = str(getattr(self._scanner, "_anime_path", "") or "").strip()
        return self._download_manager.consolidate_duplicate_anime_folders(anime_path)

    def apply_max_connections(self, value: int | str | None) -> int | None:
        """Apply LibTorrent peer connections limit when that client is active."""
        tm = self._torrent_manager
        if tm is None or getattr(tm, "name", None) != "LibTorrent":
            return None
        setter = getattr(tm, "set_max_connections", None)
        if not callable(setter):
            return None
        try:
            return int(setter(value))
        except Exception:
            return None

    def mark_torrents_deleted_for_removed_file(
        self, anime_id: int, deleted_path: str
    ) -> int:
        return self._download_manager.mark_torrents_deleted_for_removed_file(
            anime_id,
            deleted_path,
            self._scanner.resolve_anime_folder,
        )

    def mark_torrents_deleted_for_seen_anime(self, anime_id: int) -> int:
        anime_path = str(getattr(self._scanner, "_anime_path", "") or "")
        return self._download_manager.mark_torrents_deleted_for_seen_anime(
            anime_id,
            self._scanner.resolve_anime_folder,
            animes_root=anime_path,
        )

    def reconcile_seen_anime_torrents(self) -> int:
        """Mark/remove torrents and folders for every anime already tagged SEEN."""
        lister = getattr(self._user_actions, "list_anime_ids_with_tag", None)
        if not callable(lister):
            return 0
        try:
            anime_ids = list(lister("SEEN") or [])
        except Exception:
            return 0
        marked = 0
        for anime_id in anime_ids:
            try:
                marked += int(self.mark_torrents_deleted_for_seen_anime(int(anime_id)) or 0)
            except Exception:
                continue
        return marked

    def repair_torrent_index(self, *, dry_run: bool = False) -> str:
        from application.services.torrent_index_repair import TorrentIndexRepairService

        anime_path = getattr(self._scanner, "_anime_path", "") or ""
        service = TorrentIndexRepairService(
            db_manager=self._db_manager,
            scanner=self._scanner,
            torrent_manager=self._torrent_manager,
            file_manager=self._file_manager,
            anime_path=anime_path,
            log_fn=lambda cat, msg: self._download_manager.log(cat, msg),
        )
        result = service.repair_unindexed_torrents(dry_run=dry_run)
        if dry_run:
            return (
                f"would repair {result.repaired_index_rows} index row(s) "
                f"across {result.affected_anime} anime; "
                f"{len(result.issues)} issue(s) detected"
            )
        if result.repaired_index_rows == 0:
            return "no torrent index rows repaired"
        return (
            f"repaired {result.repaired_index_rows} index row(s) "
            f"across {result.affected_anime} anime"
        )

    def close(self) -> None:
        try:
            self._download_manager.close()
        except Exception:
            pass
        tm = self._torrent_manager
        if tm is not None:
            closer = getattr(tm, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception:
                    pass

    def _promote_watching_on_download_start(self, anime_id: int, user_id: int) -> None:
        try:
            state = self._user_actions.get_user_state(anime_id, user_id)
            tag = str(state.get("tag") or "NONE").upper()
            if tag in ("NONE", "WATCHLIST"):
                self._user_actions.set_tag(anime_id, "WATCHING", user_id)
        except Exception:  # noqa: BLE001
            return

    def start_download(
        self,
        anime_id: int,
        url: str | None = None,
        hash_value: str | None = None,
        user_id: int | None = None,
        source: str | None = None,
    ) -> bool:
        queue = self._download_manager.download_file(
            anime_id=anime_id,
            url=url,
            hash_value=hash_value,
            user_id=user_id,
            source=source,
        )
        return queue is not None

    def get_download_progress(self, anime_id: int) -> dict:
        return self._download_manager.get_download_status(anime_id) or {}

    def cancel_download(self, anime_id: int) -> bool:
        return self._download_manager.cancel_download(anime_id)

    def pause_torrent(self, hash_value: str) -> bool:
        return self._download_manager.pause_torrent(hash_value)

    def resume_torrent(self, hash_value: str) -> bool:
        return self._download_manager.resume_torrent(hash_value)

    def get_active_downloads(self) -> list[dict]:
        return self._download_manager.get_active_downloads()

    def get_torrents_overview(self) -> dict[str, list[dict]]:
        getter = getattr(self._download_manager, "get_torrents_overview", None)
        if not callable(getter):
            return {
                "active": [],
                "seeding": [],
                "completed": [],
                "error": [],
                "other": [],
            }
        return getter()

    def search_torrents(
        self,
        terms: list[str],
        profile: str = "interactive",
        limit: int | None = None,
        allow_nsfw: bool = False,
    ) -> list[dict]:
        facade = SearchFacade(profile=self._search_profile(profile, limit, allow_nsfw))
        rows = list(facade.search(terms))
        rows.sort(key=lambda row: int(row.get("seeds") or 0), reverse=True)
        return rows

    def stream_torrents(
        self,
        terms: list[str],
        profile: str = "interactive",
        limit: int | None = None,
        allow_nsfw: bool = False,
    ):
        facade = SearchFacade(profile=self._search_profile(profile, limit, allow_nsfw))
        yield from facade.search(terms)

    @staticmethod
    def _search_profile(
        profile: str, limit: int | None, allow_nsfw: bool
    ):
        """Build a request profile; ``limit`` overrides per-term row cap."""
        loaded = load_profile(profile)
        limits = loaded.limits
        if limit is not None:
            limits = replace(limits, max_results_per_term=max(1, int(limit)))
        return replace(loaded, allow_nsfw=allow_nsfw, limits=limits)
