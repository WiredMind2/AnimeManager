"""Local on-disk media library adapter."""

from __future__ import annotations

import os
from typing import Any

from adapters.file.local_episode_scanner import LocalEpisodeScanner
from application.playback.file_ids import episode_file_id_for_path, find_episode_by_file_id
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

    def list_episode_files(self, anime_id: int) -> list[dict[str, Any]]:
        folder = self._scanner.resolve_anime_folder(anime_id)
        episodes = self._scanner.scan_episodes(folder)
        out: list[dict[str, Any]] = []
        for item in episodes:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            if not path:
                continue
            title = str(item.get("title") or os.path.basename(path)).strip()
            file_id = episode_file_id_for_path(path)
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
        target = find_episode_by_file_id(self.list_episode_files(anime_id), file_id)
        if target is None:
            return False
        item = target
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
            return True
        except OSError:
            return False

    def delete_anime_folder(self, anime_id: int) -> bool:
        folder = self._scanner.resolve_anime_folder(anime_id)
        if not folder or self._fm is None:
            return False
        anime_path = str(getattr(self._scanner, "_anime_path", "") or "").strip()
        if not anime_path or not self._fm.exists(folder):
            return False
        try:
            folder_norm = os.path.normcase(os.path.realpath(os.path.normpath(folder)))
            root_norm = os.path.normcase(os.path.realpath(os.path.normpath(anime_path)))
        except OSError:
            return False
        if folder_norm == root_norm or not folder_norm.startswith(root_norm + os.sep):
            return False
        if not self._fm.isdir(folder):
            return False
        try:
            self._fm.delete(folder)
            return True
        except OSError:
            return False

    def get_stream_cache_root(self) -> str:
        data_path = ""
        if self._fm is not None:
            settings = getattr(self._fm, "settings", None)
            if isinstance(settings, dict):
                data_path = str(settings.get("dataPath") or "").strip()
        root = os.path.join(data_path, "streams") if data_path else os.path.abspath(".streams")
        os.makedirs(root, exist_ok=True)
        return root
