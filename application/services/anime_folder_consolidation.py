"""Merge on-disk library folders that share the same anime id.

When the catalogue title changes between downloads, ``DownloadManager``
historically created a new ``<Title> - <id>`` folder without reusing the
old one. This module consolidates those siblings into one canonical
folder and removes the emptied duplicates.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from application.services.torrent_file_presence import folder_has_video_files
from shared.utils.folder_names import (
    choose_canonical_anime_folder_name,
    match_anime_folder_names,
    parse_anime_id_from_folder_name,
)


@dataclass(frozen=True)
class ConsolidationResult:
    """Outcome of merging duplicate folders for one anime id."""

    anime_id: int
    canonical_path: str
    merged_from: list[str] = field(default_factory=list)
    moved_files: int = 0


def consolidate_duplicate_folders_for_anime(
    animes_root: str,
    anime_id: int,
    *,
    entries: Optional[Iterable[str]] = None,
    preferred_paths: Iterable[str] = (),
    redirect_save_paths: Optional[Callable[[str, str], None]] = None,
    log: Optional[Callable[[str], None]] = None,
) -> Optional[ConsolidationResult]:
    """Merge every on-disk folder for ``anime_id`` into one canonical path.

    Returns ``None`` when fewer than two folders exist for the id.
    """
    root = str(animes_root or "").strip()
    if not root or not os.path.isdir(root):
        return None

    names = list(entries) if entries is not None else os.listdir(root)
    matches = [
        name
        for name in match_anime_folder_names(names, anime_id)
        if os.path.isdir(os.path.join(root, name))
    ]
    if len(matches) < 2:
        return None

    canonical_name = choose_canonical_anime_folder_name(
        matches,
        animes_root=root,
        preferred_paths=preferred_paths,
        has_video_files=folder_has_video_files,
    )
    canonical_path = os.path.join(root, canonical_name)
    os.makedirs(canonical_path, exist_ok=True)

    merged_from: list[str] = []
    moved_files = 0
    for name in matches:
        if name == canonical_name:
            continue
        source_path = os.path.join(root, name)
        moved_files += _merge_directory_into(source_path, canonical_path)
        if redirect_save_paths is not None:
            try:
                redirect_save_paths(source_path, canonical_path)
            except Exception as exc:
                if log is not None:
                    log(
                        f"Could not redirect save paths from {source_path!r} "
                        f"to {canonical_path!r}: {exc}"
                    )
        _remove_empty_tree(source_path)
        merged_from.append(source_path)
        if log is not None:
            log(
                f"Merged anime {anime_id} folder {source_path!r} "
                f"into {canonical_path!r}"
            )

    return ConsolidationResult(
        anime_id=anime_id,
        canonical_path=canonical_path,
        merged_from=merged_from,
        moved_files=moved_files,
    )


def consolidate_all_duplicate_anime_folders(
    animes_root: str,
    *,
    list_entries: Optional[Callable[[], Iterable[str]]] = None,
    preferred_paths_for: Optional[Callable[[int], Iterable[str]]] = None,
    redirect_save_paths: Optional[Callable[[str, str], None]] = None,
    log: Optional[Callable[[str], None]] = None,
) -> list[ConsolidationResult]:
    """Consolidate every anime id that has more than one library folder."""
    root = str(animes_root or "").strip()
    if not root or not os.path.isdir(root):
        return []

    if list_entries is not None:
        try:
            entries = list(list_entries() or [])
        except Exception:
            entries = os.listdir(root)
    else:
        entries = os.listdir(root)

    by_id: dict[int, list[str]] = {}
    for name in entries:
        anime_id = parse_anime_id_from_folder_name(name)
        if anime_id is None:
            continue
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        by_id.setdefault(anime_id, []).append(name)

    results: list[ConsolidationResult] = []
    for anime_id, names in sorted(by_id.items()):
        if len(names) < 2:
            continue
        preferred: Iterable[str] = ()
        if preferred_paths_for is not None:
            try:
                preferred = preferred_paths_for(anime_id) or ()
            except Exception:
                preferred = ()
        merged = consolidate_duplicate_folders_for_anime(
            root,
            anime_id,
            entries=names,
            preferred_paths=preferred,
            redirect_save_paths=redirect_save_paths,
            log=log,
        )
        if merged is not None:
            results.append(merged)
    return results


def _merge_directory_into(source: str, destination: str) -> int:
    """Move files from ``source`` into ``destination``. Returns files moved."""
    if not os.path.isdir(source):
        return 0

    moved = 0
    for root, _dirs, files in os.walk(source, topdown=False):
        rel = os.path.relpath(root, source)
        target_dir = destination if rel in (".", "") else os.path.join(destination, rel)
        os.makedirs(target_dir, exist_ok=True)

        for filename in files:
            src_file = os.path.join(root, filename)
            dest_file = os.path.join(target_dir, filename)
            if os.path.exists(dest_file):
                try:
                    if os.path.getsize(src_file) == os.path.getsize(dest_file):
                        os.remove(src_file)
                        continue
                except OSError:
                    pass
                dest_file = _unique_destination(dest_file)
            try:
                shutil.move(src_file, dest_file)
                moved += 1
            except OSError:
                continue

        # Drop empty directories as we unwind the walk.
        try:
            if not os.listdir(root):
                os.rmdir(root)
        except OSError:
            pass

    return moved


def _unique_destination(path: str) -> str:
    """Return ``path`` with a numeric suffix before the extension if needed."""
    base, ext = os.path.splitext(path)
    index = 2
    candidate = f"{base} ({index}){ext}"
    while os.path.exists(candidate):
        index += 1
        candidate = f"{base} ({index}){ext}"
    return candidate


def _remove_empty_tree(path: str) -> None:
    """Remove ``path`` when it is an empty directory tree."""
    if not os.path.isdir(path):
        return
    try:
        for root, dirs, files in os.walk(path, topdown=False):
            if files:
                return
            for dirname in dirs:
                child = os.path.join(root, dirname)
                try:
                    os.rmdir(child)
                except OSError:
                    return
        os.rmdir(path)
    except OSError:
        return
