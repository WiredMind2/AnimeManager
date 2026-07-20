"""Filesystem-safe anime folder naming."""

from __future__ import annotations

import os
from typing import Callable, Iterable, Optional


def format_anime_folder_title(title: Optional[str]) -> str:
    """Sanitize a title for use in an on-disk anime folder name."""
    if title is None:
        return " "
    chars: list[str] = []
    for char in title:
        if char.isalnum() or char == " ":
            chars.append(char)
        elif char == "-":
            chars.append(" ")
    return "".join(chars)


def format_anime_folder_name(title: Optional[str], anime_id: int) -> str:
    """Return ``<sanitized title> - <anime_id>`` for library folders."""
    if not title:
        return f"anime_{anime_id}"
    cleaned = format_anime_folder_title(title).strip()
    if not cleaned:
        return f"anime_{anime_id}"
    cleaned = " ".join(cleaned.split())
    return f"{cleaned} - {anime_id}"


def parse_anime_id_from_folder_name(name: str) -> Optional[int]:
    """Extract the anime id encoded in a library folder name."""
    token = str(name or "").strip()
    if not token:
        return None
    if token.startswith("anime_"):
        try:
            return int(token[6:])
        except ValueError:
            return None
    try:
        return int(token.rsplit(" ", 1)[-1])
    except (ValueError, IndexError):
        return None


def match_anime_folder_names(entries: Iterable[str], anime_id: int) -> list[str]:
    """Return folder entry names that belong to ``anime_id``."""
    matches: list[str] = []
    for entry in entries:
        if parse_anime_id_from_folder_name(entry) == anime_id:
            matches.append(entry)
    return matches


def _normalize_folder_path(path: str) -> str:
    try:
        return os.path.normcase(os.path.normpath(os.path.realpath(path)))
    except OSError:
        return os.path.normcase(os.path.normpath(path))


def choose_canonical_anime_folder_name(
    folder_names: list[str],
    *,
    animes_root: str,
    preferred_paths: Iterable[str] = (),
    has_video_files: Optional[Callable[[str], bool]] = None,
) -> str:
    """Pick one folder name when multiple on-disk folders share an anime id."""
    if not folder_names:
        raise ValueError("folder_names must not be empty")

    preferred_norm = {
        _normalize_folder_path(path)
        for path in preferred_paths
        if path and str(path).strip()
    }

    def sort_key(name: str) -> tuple[int, int, str]:
        full_path = os.path.join(animes_root, name)
        normalized = _normalize_folder_path(full_path)
        preferred_rank = 0 if normalized in preferred_norm else 1
        video_rank = 0
        if has_video_files is not None and has_video_files(full_path):
            video_rank = 0
        else:
            video_rank = 1
        return (preferred_rank, video_rank, name.casefold())

    return sorted(folder_names, key=sort_key)[0]
