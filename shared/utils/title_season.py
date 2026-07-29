"""Season markers in anime / release titles for auto-download matching."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional

_RE_SEASON_SXX = re.compile(r"\bS(\d{1,2})\b", re.IGNORECASE)
_RE_SEASON_WORD = re.compile(r"\bSeason[\s._-]*(\d{1,2})\b", re.IGNORECASE)
_RE_SEASON_NTH = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)[\s._-]*Season\b", re.IGNORECASE
)
_RE_SEASON_TRAILING_ROMAN = re.compile(
    r"(?<![A-Za-z])([IVX]{1,4}|[ⅡⅢⅣⅤⅥⅦⅧⅨⅩ])\s*$",
    re.IGNORECASE,
)
_RE_SEASON_TRAILING_DIGIT = re.compile(r"(?<![\w])(\d{1,2})\s*$")

_ROMAN: dict[str, int] = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
    "Ⅱ": 2,
    "Ⅲ": 3,
    "Ⅳ": 4,
    "Ⅴ": 5,
    "Ⅵ": 6,
    "Ⅶ": 7,
    "Ⅷ": 8,
    "Ⅸ": 9,
    "Ⅹ": 10,
}


def _roman_to_int(token: str) -> Optional[int]:
    key = str(token or "").strip().upper()
    if key in _ROMAN:
        return _ROMAN[key]
    folded = unicodedata.normalize("NFKC", key)
    return _ROMAN.get(folded)


def extract_title_season(text: str) -> Optional[int]:
    """Return an explicit season number from a show/catalog title, if any."""
    raw = str(text or "").strip()
    if not raw:
        return None

    m = _RE_SEASON_SXX.search(raw)
    if m:
        return int(m.group(1))
    m = _RE_SEASON_WORD.search(raw)
    if m:
        return int(m.group(1))
    m = _RE_SEASON_NTH.search(raw)
    if m:
        return int(m.group(1))

    m = _RE_SEASON_TRAILING_ROMAN.search(raw)
    if m:
        value = _roman_to_int(m.group(1))
        if value is not None and value >= 2:
            return value

    m = _RE_SEASON_TRAILING_DIGIT.search(raw)
    if m:
        value = int(m.group(1))
        if 2 <= value <= 20:
            return value
    return None


def strip_title_season(text: str) -> str:
    """Remove season markers so base titles can be compared."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    cleaned = _RE_SEASON_SXX.sub(" ", raw)
    cleaned = _RE_SEASON_WORD.sub(" ", cleaned)
    cleaned = _RE_SEASON_NTH.sub(" ", cleaned)
    cleaned = _RE_SEASON_TRAILING_ROMAN.sub(" ", cleaned)
    m = _RE_SEASON_TRAILING_DIGIT.search(cleaned)
    if m and 2 <= int(m.group(1)) <= 20:
        cleaned = cleaned[: m.start()] + " " + cleaned[m.end() :]
    return " ".join(cleaned.split()).strip(" -–—,;:")


def expected_catalog_season(search_terms: Iterable[str]) -> int:
    """Highest explicit season across catalog terms, or ``1`` when unmarked."""
    best = 1
    for term in search_terms:
        season = extract_title_season(str(term or ""))
        if season is not None and season > best:
            best = season
    return best
