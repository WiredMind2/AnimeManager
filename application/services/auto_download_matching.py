"""Pure helpers for auto-download preference and candidate matching."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence


ParseTitleFn = Callable[[str], Any]


@dataclass(frozen=True, slots=True)
class ReleasePreference:
    """Preferred release group + quality for an anime."""

    publisher: str
    resolution: str


def _parsed_as_dict(parsed: Any) -> dict[str, Any]:
    if parsed is None:
        return {}
    if isinstance(parsed, Mapping):
        return dict(parsed)
    as_dict = getattr(parsed, "as_dict", None)
    if callable(as_dict):
        try:
            data = as_dict()
            if isinstance(data, Mapping):
                return dict(data)
        except Exception:  # noqa: BLE001
            pass
    out: dict[str, Any] = {}
    for key in (
        "publisher",
        "resolution",
        "episode_kind",
        "episode",
        "is_batch",
        "episode_start",
        "episode_end",
    ):
        if hasattr(parsed, key):
            out[key] = getattr(parsed, key)
    return out


def _norm_publisher(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    return text or None


def _norm_resolution(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    return text or None


def _episode_kind(value: Any) -> str:
    if value is None:
        return "none"
    raw = getattr(value, "value", value)
    return str(raw or "none").strip().lower()


def _as_int(value: Any) -> Optional[int]:
    if value is None or value is False:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def infer_preference(
    torrent_rows: Sequence[Mapping[str, Any]],
    *,
    parse_title: ParseTitleFn,
) -> Optional[ReleasePreference]:
    """Majority vote on ``(publisher, resolution)`` among completed torrents.

    Ties prefer the most recent tied pair (later rows win when counts equal).
    Deleted torrents and rows missing either facet are ignored.
    """
    votes: Counter[tuple[str, str]] = Counter()
    order: list[tuple[str, str]] = []
    for row in torrent_rows:
        status = str(row.get("status") or "").strip().lower()
        if status == "deleted":
            continue
        # Prefer completed history; allow status-less saved rows when present.
        if status and status not in ("complete", "completed", ""):
            # Still counting actively saved/downloading history is useful when
            # the user has not finished a season yet — include non-deleted.
            pass
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        try:
            parsed = _parsed_as_dict(parse_title(name))
        except Exception:  # noqa: BLE001
            continue
        publisher = _norm_publisher(parsed.get("publisher"))
        resolution = _norm_resolution(parsed.get("resolution"))
        if not publisher or not resolution:
            continue
        key = (publisher, resolution)
        votes[key] += 1
        order.append(key)
    if not votes:
        return None
    best_count = max(votes.values())
    tied = [key for key, count in votes.items() if count == best_count]
    if len(tied) == 1:
        publisher, resolution = tied[0]
        return ReleasePreference(publisher=publisher, resolution=resolution)
    # Most recent among tied: last occurrence in order.
    chosen = None
    for key in order:
        if key in tied:
            chosen = key
    if chosen is None:
        return None
    return ReleasePreference(publisher=chosen[0], resolution=chosen[1])


def owned_episodes_from_torrents(
    torrent_rows: Sequence[Mapping[str, Any]],
    *,
    parse_title: ParseTitleFn,
) -> set[int]:
    """Collect single-episode numbers from non-deleted library torrents."""
    owned: set[int] = set()
    for row in torrent_rows:
        status = str(row.get("status") or "").strip().lower()
        if status == "deleted":
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        try:
            parsed = _parsed_as_dict(parse_title(name))
        except Exception:  # noqa: BLE001
            continue
        if bool(parsed.get("is_batch")):
            continue
        if _episode_kind(parsed.get("episode_kind")) != "single":
            continue
        episode = _as_int(parsed.get("episode"))
        if episode is not None and episode > 0:
            owned.add(episode)
    return owned


def owned_episodes_from_files(episode_files: Iterable[Mapping[str, Any]]) -> set[int]:
    """Collect episode numbers from on-disk episode file metadata."""
    owned: set[int] = set()
    for row in episode_files:
        episode = _as_int(row.get("episode"))
        if episode is None:
            episode = _as_int(row.get("ep"))
        if episode is not None and episode > 0:
            owned.add(episode)
    return owned


def next_episode(owned: Iterable[int]) -> Optional[int]:
    """Return ``max(owned) + 1``, or ``None`` when there is no history."""
    numbers = [int(n) for n in owned if int(n) > 0]
    if not numbers:
        return None
    return max(numbers) + 1


def indexed_hashes(torrent_rows: Sequence[Mapping[str, Any]]) -> set[str]:
    """Lowercased torrent hashes already associated with the anime."""
    out: set[str] = set()
    for row in torrent_rows:
        status = str(row.get("status") or "").strip().lower()
        if status == "deleted":
            continue
        hash_value = str(row.get("hash") or row.get("infohash") or "").strip().lower()
        if hash_value:
            out.add(hash_value)
    return out


def find_matching_candidate(
    search_results: Sequence[Mapping[str, Any]],
    *,
    preference: ReleasePreference,
    episode: int,
    exclude_hashes: set[str] | None = None,
) -> Optional[dict[str, Any]]:
    """Pick the best single-episode torrent matching preference + episode.

    Batches are skipped. Among matches, highest seed count wins.
    """
    excluded = {h.lower() for h in (exclude_hashes or set()) if h}
    best: Optional[dict[str, Any]] = None
    best_seeds = -1
    for row in search_results:
        if not isinstance(row, Mapping):
            continue
        hash_value = str(row.get("infohash") or row.get("hash") or "").strip().lower()
        if hash_value and hash_value in excluded:
            continue
        parsed = _parsed_as_dict(row.get("parsed"))
        if not parsed and row.get("name"):
            # Search rows normally include ``parsed``; tolerate bare names.
            continue
        if bool(parsed.get("is_batch")):
            continue
        if _episode_kind(parsed.get("episode_kind")) != "single":
            continue
        if _as_int(parsed.get("episode")) != int(episode):
            continue
        publisher = _norm_publisher(parsed.get("publisher"))
        resolution = _norm_resolution(parsed.get("resolution"))
        if publisher != preference.publisher:
            continue
        if resolution != preference.resolution:
            continue
        try:
            seeds = int(row.get("seeds") or 0)
        except (TypeError, ValueError):
            seeds = 0
        if best is None or seeds > best_seeds:
            best = dict(row)
            best_seeds = seeds
    return best
