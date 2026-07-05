"""Detect whether completed torrent payloads still exist on disk."""

from __future__ import annotations

import os
from typing import Optional

VIDEO_SUFFIXES = ("mkv", "mp4", "avi")


def _is_video_file(path: str) -> bool:
    _base, ext = os.path.splitext(path)
    return ext.lstrip(".").lower() in VIDEO_SUFFIXES


def folder_has_video_files(path: Optional[str]) -> bool:
    """Return True when ``path`` contains at least one video file."""
    if not path or not str(path).strip():
        return False
    root_path = str(path).strip()
    if not os.path.isdir(root_path):
        return False
    for root, _dirs, files in os.walk(root_path):
        for name in files:
            if _is_video_file(os.path.join(root, name)):
                return True
    return False


def paths_have_video_files(*paths: Optional[str]) -> bool:
    """Return True when any provided path contains video files."""
    for path in paths:
        if folder_has_video_files(path):
            return True
    return False


def should_mark_deleted(
    *,
    status: Optional[str],
    save_path: Optional[str],
    anime_folder: Optional[str],
) -> bool:
    """True when a torrent was complete but its video files are gone."""
    if str(status or "").lower() != "complete":
        return False
    return not paths_have_video_files(save_path, anime_folder)
