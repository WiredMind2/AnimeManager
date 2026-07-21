"""Detect whether completed torrent payloads still exist on disk."""

from __future__ import annotations

import os
import re
from enum import Enum
from typing import Optional, Tuple

VIDEO_SUFFIXES = ("mkv", "mp4", "avi")

_RE_EP_RANGE_PAREN = re.compile(r"\(\s*(\d{1,3})\s*[-~]\s*(\d{1,3})\s*\)")
_RE_EP_RANGE_PLAIN = re.compile(r"(?<![\d.])(\d{1,3})\s*[-~]\s*(\d{1,3})(?![\d.])")

_EPISODE_PATTERNS = (
    re.compile(r"-\s(\d+)"),
    re.compile(r"(?:E|Episode|Ep|Eps)(\d+)", re.IGNORECASE),
    re.compile(r" (\d+) "),
)

_ACTIVE_DOWNLOAD_STATES = frozenset({
    "downloading",
    "downloading_metadata",
    "metadl",
    "queueddl",
    "stalleddl",
    "forceddl",
    "checkingdl",
    "checking",
    "checking_files",
    "checking_resume",
    "checking_resume_data",
    "allocating",
    "queued",
    "queued_for_checking",
})

_ERROR_STATES = frozenset({
    "error",
    "missingfiles",
})


class TorrentReconcileAction(str, Enum):
    """Action for a torrent during missing-file reconciliation."""

    SKIP = "skip"
    REMOVE_FROM_CLIENT = "remove_from_client"
    MARK_DELETED = "mark_deleted"


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


def normalize_media_path(path: Optional[str]) -> str:
    if not path or not str(path).strip():
        return ""
    try:
        return os.path.normcase(os.path.normpath(os.path.realpath(str(path).strip())))
    except OSError:
        return os.path.normcase(os.path.normpath(str(path).strip()))


def deleted_path_matches_torrent_file(
    deleted_path: str,
    candidate_path: str,
    *,
    save_path: Optional[str] = None,
) -> bool:
    """Return True when ``candidate_path`` refers to the deleted on-disk file."""
    deleted_norm = normalize_media_path(deleted_path)
    candidate_norm = normalize_media_path(candidate_path)
    if deleted_norm and candidate_norm and deleted_norm == candidate_norm:
        return True
    deleted_base = os.path.basename(deleted_norm or str(deleted_path))
    candidate_base = os.path.basename(candidate_norm or str(candidate_path))
    if deleted_base and candidate_base and deleted_base == candidate_base:
        if save_path:
            save_norm = normalize_media_path(save_path)
            if candidate_norm.startswith(save_norm + os.sep):
                return True
        return True
    if save_path and candidate_path and not os.path.isabs(str(candidate_path)):
        joined = os.path.join(str(save_path), str(candidate_path))
        if normalize_media_path(joined) == deleted_norm:
            return True
    return False


def parse_episode_range_from_name(torrent_name: Optional[str]) -> Optional[Tuple[int, int]]:
    """Extract an inclusive episode range from a torrent release name."""
    text = str(torrent_name or "").strip()
    if not text:
        return None
    for pattern in (_RE_EP_RANGE_PAREN, _RE_EP_RANGE_PLAIN):
        match = pattern.search(text)
        if not match:
            continue
        try:
            start = int(match.group(1))
            end = int(match.group(2))
        except (TypeError, ValueError):
            continue
        if start <= 0 or end <= 0:
            continue
        if start > end:
            start, end = end, start
        return start, end
    return None


def _episode_number_from_filename(filename: str) -> Optional[int]:
    for pattern in _EPISODE_PATTERNS:
        match = pattern.search(filename)
        if not match:
            continue
        try:
            return int(match.group(1))
        except (TypeError, ValueError):
            continue
    return None


def _collect_episode_numbers(folder: Optional[str]) -> set[int]:
    numbers: set[int] = set()
    if not folder or not os.path.isdir(folder):
        return numbers
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if not _is_video_file(os.path.join(root, name)):
                continue
            episode = _episode_number_from_filename(name)
            if episode is not None:
                numbers.add(episode)
    return numbers


def episodes_in_range_present(
    folder: Optional[str],
    episode_start: int,
    episode_end: int,
) -> bool:
    """Return True when at least one episode in ``[start, end]`` exists on disk."""
    if episode_start > episode_end:
        episode_start, episode_end = episode_end, episode_start
    present = _collect_episode_numbers(folder)
    return any(episode_start <= episode <= episode_end for episode in present)


def _episode_range_token(torrent_name: Optional[str]) -> Optional[str]:
    """Return a normalized ``(start-end)`` token from a batch release name."""
    text = str(torrent_name or "").strip()
    if not text:
        return None
    for pattern in (_RE_EP_RANGE_PAREN, _RE_EP_RANGE_PLAIN):
        match = pattern.search(text)
        if not match:
            continue
        try:
            start = int(match.group(1))
            end = int(match.group(2))
        except (TypeError, ValueError):
            continue
        if start <= 0 or end <= 0:
            continue
        if start > end:
            start, end = end, start
        return f"({start}-{end})"
    return None


def _dirname_has_range_token(dirname: str, range_token: str) -> bool:
    """True when ``dirname`` contains the same episode range as ``range_token``."""
    token_match = _RE_EP_RANGE_PAREN.search(range_token)
    if not token_match:
        return False
    try:
        start = int(token_match.group(1))
        end = int(token_match.group(2))
    except (TypeError, ValueError):
        return False
    for pattern in (_RE_EP_RANGE_PAREN, _RE_EP_RANGE_PLAIN):
        match = pattern.search(dirname)
        if not match:
            continue
        try:
            found_start = int(match.group(1))
            found_end = int(match.group(2))
        except (TypeError, ValueError):
            continue
        if found_start > found_end:
            found_start, found_end = found_end, found_start
        if found_start == start and found_end == end:
            return True
    return False


def batch_payload_present(
    folder: Optional[str],
    torrent_name: Optional[str],
) -> bool:
    """Return True when a batch-specific directory payload still exists.

    Weekly single-episode files in the anime root do **not** count as the
    batch still being present — only a directory whose name carries the
    same ``(start-end)`` range token (and contains video) does.
    """
    range_token = _episode_range_token(torrent_name)
    if not range_token:
        return False
    if not folder or not str(folder).strip():
        return False
    root_path = str(folder).strip()
    if not os.path.isdir(root_path):
        return False

    candidates = [root_path]
    try:
        for entry in os.listdir(root_path):
            child = os.path.join(root_path, entry)
            if os.path.isdir(child):
                candidates.append(child)
    except OSError:
        return False

    for candidate in candidates:
        basename = os.path.basename(candidate.rstrip("\\/"))
        if not _dirname_has_range_token(basename, range_token):
            continue
        if folder_has_video_files(candidate):
            return True
    return False


def _normalise_live_state(live_state: Optional[str]) -> str:
    return str(live_state or "").strip().lower().replace(" ", "_")


def parse_single_episode_from_name(
    torrent_name: Optional[str],
) -> Optional[int]:
    """Extract a single episode number from a torrent release name."""
    text = str(torrent_name or "").strip()
    if not text:
        return None
    if parse_episode_range_from_name(text) is not None:
        return None
    return _episode_number_from_filename(text)


def should_reconcile_torrent(
    *,
    status: Optional[str],
    save_path: Optional[str],
    anime_folder: Optional[str],
    torrent_name: Optional[str] = None,
    live_state: Optional[str] = None,
    live_progress: Optional[float] = None,
) -> TorrentReconcileAction:
    """Decide how a torrent row should be handled during reconciliation."""
    del live_progress  # reserved for future heuristics; active states gate removal

    status_token = str(status or "").lower()
    if status_token == "deleted":
        return TorrentReconcileAction.REMOVE_FROM_CLIENT

    state_token = _normalise_live_state(live_state)
    is_active = state_token in _ACTIVE_DOWNLOAD_STATES
    # Protect in-progress first downloads; previously-complete torrents that
    # are re-downloading missing payloads must still be marked deleted.
    protect_active = is_active and status_token != "complete"

    folder = anime_folder or save_path
    episode_range = parse_episode_range_from_name(torrent_name)
    if episode_range is not None:
        if not batch_payload_present(folder, torrent_name):
            if not protect_active:
                return TorrentReconcileAction.MARK_DELETED

    single_episode = parse_single_episode_from_name(torrent_name)
    if single_episode is not None and not episodes_in_range_present(
        folder, single_episode, single_episode
    ):
        if not protect_active:
            return TorrentReconcileAction.MARK_DELETED

    if protect_active:
        return TorrentReconcileAction.SKIP

    if status_token == "complete" and not paths_have_video_files(save_path, anime_folder):
        return TorrentReconcileAction.MARK_DELETED

    if state_token in _ERROR_STATES and not paths_have_video_files(save_path, anime_folder):
        return TorrentReconcileAction.MARK_DELETED

    return TorrentReconcileAction.SKIP


def should_mark_deleted(
    *,
    status: Optional[str],
    save_path: Optional[str],
    anime_folder: Optional[str],
) -> bool:
    """True when a torrent was complete but its video files are gone."""
    return (
        should_reconcile_torrent(
            status=status,
            save_path=save_path,
            anime_folder=anime_folder,
        )
        == TorrentReconcileAction.MARK_DELETED
    )
