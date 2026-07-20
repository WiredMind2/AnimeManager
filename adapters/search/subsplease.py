"""SubsPlease release-name parsing and catalog matching helpers."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_PUBLISHER = "SubsPlease"

# Weekly: [SubsPlease] Show Title - 02 (1080p) [CRC].mkv
_EPISODE_TAIL = re.compile(
    rf"^\s*\[{_PUBLISHER}\]\s+(?P<show>.+?)\s+-\s+(?P<ep>\d{{1,4}})\s+\(",
    re.IGNORECASE,
)

# Batch: [SubsPlease] Show Title (01-12) (1080p) [Batch]
_BATCH_TAIL = re.compile(
    rf"^\s*\[{_PUBLISHER}\]\s+(?P<show>.+?)\s+\((?P<batch>\d{{1,4}}-\d{{1,4}})\)\s+\(",
    re.IGNORECASE,
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class SubsPleaseRelease:
    """Parsed view of a SubsPlease torrent title."""

    raw_name: str
    show_title: str
    episode: int | None = None
    batch_range: tuple[int, int] | None = None


def parse_subsplease_release(name: str) -> SubsPleaseRelease | None:
    """Extract the show segment from a SubsPlease release name."""
    if not name or _PUBLISHER.lower() not in name.lower():
        return None

    match = _EPISODE_TAIL.match(name)
    if match:
        return SubsPleaseRelease(
            raw_name=name,
            show_title=match.group("show").strip(),
            episode=int(match.group("ep")),
        )

    batch = _BATCH_TAIL.match(name)
    if batch:
        start_s, end_s = batch.group("batch").split("-", 1)
        return SubsPleaseRelease(
            raw_name=name,
            show_title=batch.group("show").strip(),
            batch_range=(int(start_s), int(end_s)),
        )

    return None


def normalize_match_key(text: str) -> str:
    """Fold text for fuzzy catalog ↔ release comparisons."""
    folded = unicodedata.normalize("NFKD", text)
    asciiish = "".join(ch for ch in folded if not unicodedata.combining(ch))
    lowered = asciiish.lower()
    return _NON_ALNUM.sub("", lowered)


def release_matches_catalog(show_title: str, catalog_title: str) -> bool:
    """Return True when a catalog string plausibly names the same show."""
    rel = normalize_match_key(show_title)
    cat = normalize_match_key(catalog_title)
    if not rel or not cat:
        return False
    if rel == cat or rel in cat or cat in rel:
        return True
    rel_words = [w for w in re.split(r"\s+", show_title.lower()) if len(w) >= 4][:4]
    if len(rel_words) >= 2:
        cat_lower = catalog_title.lower()
        hits = sum(1 for w in rel_words if w in cat_lower)
        if hits >= 2:
            return True
    return False
