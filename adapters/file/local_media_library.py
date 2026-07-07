"""Local on-disk media library adapter."""

from __future__ import annotations

import hashlib
import os
from typing import Any

from adapters.file.local_episode_scanner import LocalEpisodeScanner
from application.services.database_manager import DatabaseManager


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class LocalMediaLibraryAdapter:
    """Implements :class:`ports.interfaces.MediaLibraryPort`."""

    def __init__(
        self,
        *,
        scanner: LocalEpisodeScanner,
        file_manager: Any,
        db_manager: DatabaseManager,
    ) -> None:
        self._scanner = scanner
        self._fm = file_manager
        self._db_manager = db_manager

    @property
    def _database(self):
        return self._db_manager.get_database()

    def list_episode_files(self, anime_id: int) -> list[dict[str, Any]]:
        folder = self._scanner.resolve_anime_folder(anime_id)
        episodes = self._scanner.scan_episodes(folder)
        out: list[dict[str, Any]] = []
        for idx, item in enumerate(episodes):
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            if not path:
                continue
            title = str(item.get("title") or os.path.basename(path)).strip()
            digest = hashlib.sha1(path.encode("utf-8")).hexdigest()[:16]
            file_id = f"ep-{idx:04d}-{digest}"
            try:
                size_bytes = os.path.getsize(path)
            except OSError:
                size_bytes = None
            out.append(
                {
                    "file_id": file_id,
                    "path": path,
                    "title": title,
                    "size_bytes": size_bytes,
                    "season": _safe_int(item.get("season")),
                    "episode": _safe_int(item.get("episode")),
                }
            )
        return out

    def delete_episode_file(self, anime_id: int, file_id: str) -> bool:
        folder = self._scanner.resolve_anime_folder(anime_id)
        if not folder or not str(file_id).strip():
            return False
        if self._fm is None or not self._fm.exists(folder):
            return False

        folder_norm = os.path.normcase(os.path.realpath(os.path.normpath(folder)))
        removed = False
        for item in self.list_episode_files(anime_id):
            if str(item.get("file_id") or "") != str(file_id).strip():
                continue
            path = str(item.get("path") or "").strip()
            if not path:
                return False
            try:
                path_norm = os.path.normcase(os.path.realpath(os.path.normpath(path)))
            except OSError:
                return False
            if path_norm == folder_norm or not path_norm.startswith(folder_norm + os.sep):
                return False
            if not os.path.isfile(path):
                return False
            try:
                os.remove(path)
                removed = True
            except OSError:
                return False
            break

        if removed:
            self._mark_completed_torrents_deleted_if_folder_empty(anime_id, folder)
        return removed

    def _mark_completed_torrents_deleted_if_folder_empty(
        self, anime_id: int, folder: str
    ) -> None:
        from application.services.torrent_file_presence import folder_has_video_files

        if folder_has_video_files(folder):
            return
        db = self._database
        if db is None:
            return
        try:
            rows = db.sql(
                (
                    "SELECT t.hash, t.status FROM torrents AS t "
                    "JOIN torrentsIndex AS i ON i.value = t.hash "
                    "WHERE i.id=?"
                ),
                (anime_id,),
            )
        except Exception:
            return
        for row in rows or []:
            if not row:
                continue
            try:
                hash_val = row[0]
                status = row[1] if len(row) > 1 else None
            except (TypeError, IndexError):
                continue
            if str(status or "").lower() != "complete":
                continue
            try:
                db.sql(
                    "UPDATE torrents SET status=? WHERE hash=?",
                    ("deleted", hash_val),
                    save=True,
                )
            except Exception:
                pass

    def get_stream_cache_root(self) -> str:
        data_path = ""
        if self._fm is not None:
            settings = getattr(self._fm, "settings", None)
            if isinstance(settings, dict):
                data_path = str(settings.get("dataPath") or "").strip()
        root = os.path.join(data_path, "streams") if data_path else os.path.abspath(".streams")
        os.makedirs(root, exist_ok=True)
        return root
