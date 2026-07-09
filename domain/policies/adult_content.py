"""Heuristics for detecting adult torrent releases in search results."""

from __future__ import annotations

import re

# Case-insensitive markers commonly found in adult torrent titles.
_ADULT_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bhentai\b",
        r"\[18\+\]",
        r"\(18\+\)",
        r"\b18\+\b",
        r"\buncensored\b",
        r"\bdoujin(?:shi)?\b",
        r"\bxxx\b",
        r"\bporn\b",
        r"\badult\s+only\b",
        r"\boppai\b",
        r"\bloli\b",
        r"\bshotacon\b",
        r"\bshota\b",
    )
)

_NSFW_ENGINE_MARKERS: tuple[str, ...] = ("sukebei",)


def is_adult_torrent(name: str, engine_url: str = "") -> bool:
    """Return True when a torrent row looks like NSFW/hentai content."""
    title = (name or "").strip()
    if not title:
        return False

    for pattern in _ADULT_TITLE_PATTERNS:
        if pattern.search(title):
            return True

    engine = (engine_url or "").lower()
    return any(marker in engine for marker in _NSFW_ENGINE_MARKERS)
