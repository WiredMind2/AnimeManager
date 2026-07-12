"""Stable episode file identifiers and legacy ID resolution."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable
from typing import Any

_HEX16 = re.compile(r"^[0-9a-f]{16}$")


def episode_path_digest(path: str) -> str:
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:16]


def episode_file_id_for_path(path: str) -> str:
    """Path-derived ID that does not change when scan order changes."""
    return f"ep-{episode_path_digest(path)}"


def episode_file_id_digest(file_id: str) -> str | None:
    raw = str(file_id or "").strip().lower()
    if not raw.startswith("ep-"):
        return None
    tail = raw.rsplit("-", 1)[-1]
    if _HEX16.match(tail):
        return tail
    return None


def episode_file_ids_match(requested: str, candidate: str) -> bool:
    req = str(requested or "").strip()
    cand = str(candidate or "").strip()
    if not req or not cand:
        return False
    if req == cand:
        return True
    req_digest = episode_file_id_digest(req)
    cand_digest = episode_file_id_digest(cand)
    return bool(req_digest and cand_digest and req_digest == cand_digest)


def _default_file_id_getter(episode: Any) -> str:
    if isinstance(episode, dict):
        return str(episode.get("file_id") or "").strip()
    return str(getattr(episode, "file_id", "") or "").strip()


def find_episode_by_file_id(
    episodes: Iterable[Any],
    file_id: str,
    *,
    get_file_id: Callable[[Any], str] | None = None,
) -> Any | None:
    getter = get_file_id or _default_file_id_getter
    requested = str(file_id or "").strip()
    if not requested:
        return None
    for episode in episodes:
        if episode_file_ids_match(requested, getter(episode)):
            return episode
    return None


def progress_for_file_id(progress: dict[str, Any], file_id: str) -> dict[str, Any]:
    direct = progress.get(file_id)
    if isinstance(direct, dict):
        return direct
    req_digest = episode_file_id_digest(file_id)
    if not req_digest:
        return {}
    for stored_id, row in progress.items():
        if episode_file_id_digest(str(stored_id)) == req_digest and isinstance(row, dict):
            return row
    return {}
