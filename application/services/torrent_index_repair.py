"""Detect and repair missing torrentsIndex rows for on-disk anime libraries."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from application.services.torrent_file_presence import (
    VIDEO_SUFFIXES,
    _episode_number_from_filename,
    folder_has_video_files,
)

_FOLDER_ID_RE = re.compile(r" - (\d+)$")


@dataclass(frozen=True)
class LibraryIssue:
    anime_id: int
    folder: str
    kind: str
    detail: str = ""


@dataclass
class TorrentIndexRepairResult:
    issues: list[LibraryIssue] = field(default_factory=list)
    repaired_index_rows: int = 0
    upserted_torrent_rows: int = 0
    affected_anime: int = 0


def _normalize_folder(path: Optional[str]) -> str:
    if not path or not str(path).strip():
        return ""
    try:
        return os.path.normcase(os.path.normpath(os.path.realpath(str(path).strip())))
    except OSError:
        return os.path.normcase(os.path.normpath(str(path).strip()))


def _parse_anime_id_from_folder_name(name: str) -> Optional[int]:
    match = _FOLDER_ID_RE.search(str(name or "").strip())
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _is_video_file(path: str) -> bool:
    _base, ext = os.path.splitext(path)
    return ext.lstrip(".").lower() in VIDEO_SUFFIXES


class TorrentIndexRepairService:
    """Backfill torrentsIndex rows for libraries with on-disk episodes."""

    def __init__(
        self,
        *,
        db_manager: Any,
        scanner: Any,
        torrent_manager: Any = None,
        file_manager: Any = None,
        anime_path: str = "",
        log_fn: Callable[[str, str], None] | None = None,
    ) -> None:
        self._db_manager = db_manager
        self._scanner = scanner
        self._torrent_manager = torrent_manager
        self._file_manager = file_manager
        self._anime_path = str(anime_path or "").strip()
        self._log = log_fn or (lambda _cat, _msg: None)

    def detect_issues(self) -> list[LibraryIssue]:
        issues: list[LibraryIssue] = []
        for anime_id, folder in self._iter_library_folders():
            if not folder_has_video_files(folder):
                continue
            index_count = self._count_index_rows(anime_id)
            if index_count == 0:
                issues.append(
                    LibraryIssue(
                        anime_id=anime_id,
                        folder=folder,
                        kind="missing_index",
                        detail="on-disk videos but no torrentsIndex rows",
                    )
                )
            if self._has_multi_release_episode_one(folder):
                issues.append(
                    LibraryIssue(
                        anime_id=anime_id,
                        folder=folder,
                        kind="multi_release",
                        detail="multiple episode-1 files from different releases",
                    )
                )
            for orphan in self._orphan_db_torrents(anime_id, folder):
                issues.append(
                    LibraryIssue(
                        anime_id=anime_id,
                        folder=folder,
                        kind="orphan_db_torrent",
                        detail=f"unindexed hash {orphan.get('hash', '')[:12]}",
                    )
                )
            for live in self._orphan_live_torrents(anime_id, folder):
                issues.append(
                    LibraryIssue(
                        anime_id=anime_id,
                        folder=folder,
                        kind="orphan_live_torrent",
                        detail=f"live session {live.get('hash', '')[:12]}",
                    )
                )
        return issues

    def repair_unindexed_torrents(self, *, dry_run: bool = False) -> TorrentIndexRepairResult:
        result = TorrentIndexRepairResult(issues=self.detect_issues())
        touched_anime: set[int] = set()

        for anime_id, folder in self._iter_library_folders():
            if not folder_has_video_files(folder):
                continue
            candidates = []
            candidates.extend(self._orphan_db_torrents(anime_id, folder))
            candidates.extend(self._orphan_live_torrents(anime_id, folder))
            if not candidates and self._count_index_rows(anime_id) == 0:
                candidates.extend(self._live_torrents_for_folder(folder))

            seen_hashes: set[str] = set()
            for row in candidates:
                hash_val = str(row.get("hash") or "").strip()
                if not hash_val:
                    continue
                key = hash_val.lower()
                if key in seen_hashes:
                    continue
                seen_hashes.add(key)
                if dry_run:
                    result.repaired_index_rows += 1
                    touched_anime.add(anime_id)
                    continue
                linker = getattr(self._db_manager, "ensure_torrent_index", None)
                if not callable(linker):
                    continue
                linked = bool(
                    linker(
                        anime_id,
                        hash_val,
                        name=row.get("name"),
                        save_path=row.get("save_path") or folder,
                    )
                )
                if linked:
                    result.repaired_index_rows += 1
                    touched_anime.add(anime_id)

        result.affected_anime = len(touched_anime)
        if not dry_run:
            self._log(
                "TORRENT_INDEX_REPAIR",
                (
                    f"repaired {result.repaired_index_rows} index row(s) "
                    f"across {result.affected_anime} anime"
                ),
            )
        return result

    def _iter_library_folders(self) -> list[tuple[int, str]]:
        root = self._anime_path
        if not root:
            root = getattr(self._scanner, "_anime_path", "") or ""
        if not root or not os.path.isdir(root):
            return []
        out: list[tuple[int, str]] = []
        try:
            names = os.listdir(root)
        except OSError:
            return []
        for name in sorted(names):
            anime_id = _parse_anime_id_from_folder_name(name)
            if anime_id is None:
                continue
            folder = os.path.join(root, name)
            if os.path.isdir(folder):
                out.append((anime_id, folder))
        return out

    def _count_index_rows(self, anime_id: int) -> int:
        counter = getattr(self._db_manager, "count_torrent_index_for_anime", None)
        if not callable(counter):
            return 0
        try:
            return int(counter(anime_id) or 0)
        except Exception:
            return 0

    def _folder_matches(self, candidate_path: Optional[str], folder: str) -> bool:
        folder_norm = _normalize_folder(folder)
        candidate_norm = _normalize_folder(candidate_path)
        if not folder_norm or not candidate_norm:
            return False
        return (
            candidate_norm == folder_norm
            or candidate_norm.startswith(folder_norm + os.sep)
        )

    def _orphan_db_torrents(self, anime_id: int, folder: str) -> list[dict[str, Any]]:
        lister = getattr(self._db_manager, "list_orphan_torrents_for_folder", None)
        if not callable(lister):
            return []
        try:
            return list(lister(anime_id, folder) or [])
        except Exception:
            return []

    def _live_torrents_for_folder(self, folder: str) -> list[dict[str, Any]]:
        tm = self._torrent_manager
        if tm is None:
            return []
        lister = getattr(tm, "list", None)
        if not callable(lister):
            return []
        try:
            rows = lister() or []
        except Exception:
            return []
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            save_path = row.get("path") or row.get("save_path")
            if not self._folder_matches(save_path, folder):
                continue
            hash_val = row.get("hash")
            if hash_val:
                out.append(
                    {
                        "hash": str(hash_val),
                        "name": row.get("name"),
                        "save_path": str(save_path) if save_path else folder,
                    }
                )
        return out

    def _orphan_live_torrents(self, anime_id: int, folder: str) -> list[dict[str, Any]]:
        indexed = {
            str(row.get("hash") or "").lower()
            for row in self._indexed_torrents(anime_id)
            if row.get("hash")
        }
        out: list[dict[str, Any]] = []
        for row in self._live_torrents_for_folder(folder):
            key = str(row.get("hash") or "").lower()
            if key and key not in indexed:
                out.append(row)
        return out

    def _indexed_torrents(self, anime_id: int) -> list[dict[str, Any]]:
        lister = getattr(self._db_manager, "list_torrents_for_anime", None)
        if not callable(lister):
            return []
        try:
            return list(lister(anime_id) or [])
        except Exception:
            return []

    def _has_multi_release_episode_one(self, folder: str) -> bool:
        ep_one = 0
        for root, _dirs, files in os.walk(folder):
            for name in files:
                path = os.path.join(root, name)
                if not _is_video_file(path):
                    continue
                if _episode_number_from_filename(name) == 1:
                    ep_one += 1
                    if ep_one > 1:
                        return True
        return False
