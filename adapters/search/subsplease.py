"""SubsPlease release-name parsing and catalog matching helpers."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from shared.utils.title_season import (
    expected_catalog_season,
    extract_title_season,
    strip_title_season,
)

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

# Re-export season helpers for existing call sites.
__all__ = [
    "SubsPleaseRelease",
    "parse_subsplease_release",
    "normalize_match_key",
    "release_matches_catalog",
    "extract_title_season",
    "strip_title_season",
    "expected_catalog_season",
]


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
    """Return True when a catalog string plausibly names the same show.

    Season markers are stripped for base-title comparison. When the catalog
    title has an explicit season, the release must resolve to the same season
    (unmarked release counts as season 1).
    """
    cat_season = extract_title_season(catalog_title)
    rel_season = extract_title_season(show_title) or 1
    if cat_season is not None and rel_season != cat_season:
        return False

    rel_base = strip_title_season(show_title)
    cat_base = strip_title_season(catalog_title)
    rel = normalize_match_key(rel_base)
    cat = normalize_match_key(cat_base)
    # Reject tiny keys (e.g. Japanese titles that fold to a lone ``s`` from
    # ``S-Rank``) — they false-positive against almost every Latin title.
    if not rel or not cat or len(rel) < 4 or len(cat) < 4:
        return False
    if rel == cat or rel in cat or cat in rel:
        return True
    rel_words = [w for w in re.split(r"\s+", rel_base.lower()) if len(w) >= 4][:4]
    if len(rel_words) >= 2:
        cat_lower = cat_base.lower()
        hits = sum(1 for w in rel_words if w in cat_lower)
        if hits >= 2:
            return True
    return False
