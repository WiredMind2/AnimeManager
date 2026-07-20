"""Query planning stage.

Normalizes, deduplicates and ranks candidate search terms before they are
handed to subprocess workers. This is where the orchestration layer kills
combinatorial subprocess fan-out by capping the term set to the most
informative items.

The planner is intentionally pure: it has no I/O and is fully covered by
unit tests in ``tests/unit/search_engines/test_planner.py``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from .config import SearchLimits

_WHITESPACE_RE = re.compile(r"\s+")
_LATIN_RE = re.compile(r"[A-Za-z]")
_CJK_RE = re.compile(r"[\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
_PUNCT_CLUSTER_RE = re.compile(r"\.\s*:\s*")
_ROMANIZED_FIRST_WORD_RE = re.compile(r"^[A-Za-z]+-[A-Za-z]")


def _ascii_fold(text: str) -> str:
    """Strip combining marks so ``ū`` matches ``u`` on engines that index
    Latin-extended characters as distinct tokens (e.g. nyaa.si full-text).

    Uses Unicode NFD decomposition + filter on ``unicodedata.combining``
    which removes accents, macrons, umlauts, etc. without altering the
    base letter. Returns ``text`` unchanged when it is already ASCII.
    """
    decomposed = unicodedata.normalize("NFD", text)
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return folded


def _loosen_punctuation(text: str) -> str:
    """Normalize punctuation clusters that break nyaa full-text search."""
    loosened = _PUNCT_CLUSTER_RE.sub(". ", text)
    if loosened == text:
        return text
    return _WHITESPACE_RE.sub(" ", loosened).strip()


def _dehyphenate_words(text: str) -> str:
    """Remove intra-word hyphens in Latin text (``Ojou-sama`` -> ``Ojousama``).

    Preserves romanization syllable separators such as ``Tai-Ari`` (uppercase
    after the hyphen).
    """
    return re.sub(r"(?<=[a-z])-(?=[a-z])", "", text)


def _colon_subtitle_prefix(term: str) -> str | None:
    """Emit the Latin segment before a colon for long catalog titles.

    Releases are usually named after the short lead title (e.g.
    ``Saijo no Osewa``) rather than the full subtitle that follows
    the colon in API metadata.
    """
    if len(term) < 40 or ":" not in term:
        return None
    head = term.split(":", 1)[0].strip()
    if (
        len(head) < 6
        or head == term
        or _CJK_RE.search(head)
        or not _LATIN_RE.search(head)
    ):
        return None
    words = head.split()
    word_count = len(words)
    if word_count > 8:
        return None
    # Multi-word prefixes (``Saijo no Osewa``) and single-word release
    # nicknames (``Tenkosaki``) both appear on nyaa; the latter is common
    # for fansub naming when the API synonym includes an English subtitle.
    if word_count == 1:
        if len(head) < 6:
            return None
    elif word_count < 2:
        return None
    return head


def _romanized_prefix(term: str) -> str | None:
    """Emit a short prefix for long romanized titles (e.g. ``Tai-Ari deshita``)."""
    if len(term) < 40:
        return None

    colon_prefix = _colon_subtitle_prefix(term)
    if colon_prefix is not None:
        return colon_prefix

    words = term.split()
    if len(words) < 2 or not _ROMANIZED_FIRST_WORD_RE.match(words[0]):
        return None
    head: list[str] = []
    for word in words[:2]:
        cleaned = word.strip(".,:;!?\"'")
        if cleaned:
            head.append(cleaned)
    if len(head) < 2:
        return None
    prefix = " ".join(head)
    if len(prefix) < 6 or prefix == term:
        return None
    return prefix


_SEASON_WORD_RE = re.compile(r"\bSeason\s+(\d+)\b", re.IGNORECASE)
_SEASON_PART_RE = re.compile(r"\bPart\s+(\d+)\b", re.IGNORECASE)
# Catalog sequels often look like ``… 2nd Season`` / ``… S2`` / ``… 第2期``.
# SubsPlease frequently keeps the base title and continues episode numbers.
_SEASON_SUFFIX_RE = re.compile(
    r"""
    (?:
        \s+(?:
            (?:\d+)(?:st|nd|rd|th)\s+Season
            | Season\s+\d+
            | Part\s+\d+
            | S\d+
        )
        | \s*第\d+期
    )
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _season_alias_variants(term: str) -> Iterable[str]:
    """Emit ``S{n}`` forms used by groups like SubsPlease (``Grand Blue S3``)."""
    variants: list[str] = []
    for pattern, repl in (
        (_SEASON_WORD_RE, r"S\1"),
        (_SEASON_PART_RE, r"S\1"),
    ):
        if pattern.search(term):
            aliased = pattern.sub(repl, term)
            if aliased != term:
                variants.append(aliased)
    return variants


def _season_base_title(term: str) -> str | None:
    """Strip a trailing season marker so sequel catalog titles hit base releases.

    Example: ``Seihantai na Kimi to Boku 2nd Season`` →
    ``Seihantai na Kimi to Boku`` (SubsPlease naming).
    """
    stripped = _SEASON_SUFFIX_RE.sub("", term).strip(" -–—:")
    if (
        not stripped
        or stripped == term
        or len(stripped) < 6
        or not any(ch.isalnum() for ch in stripped)
    ):
        return None
    return stripped


def _leading_words_prefix(term: str, *, max_words: int = 4) -> str | None:
    """Emit an early word run from long romanized titles.

    SubsPlease often uses the first several words of the JP title verbatim
    (``Suterare Seijo no Isekai Gohan Tabi``) while API metadata may only
    carry a longer or translated form.
    """
    if len(term) < 40 or _CJK_RE.search(term) or not _LATIN_RE.search(term):
        return None
    words = term.split()
    if len(words) < max_words + 1:
        return None
    head: list[str] = []
    for word in words[:max_words]:
        cleaned = word.strip(".,:;!?\"'")
        if cleaned:
            head.append(cleaned)
    if len(head) < 3:
        return None
    prefix = " ".join(head)
    if len(prefix) < 12 or prefix == term:
        return None
    return prefix


@dataclass(frozen=True)
class PlannedTerm:
    """A normalized search term with its derived metadata."""

    normalized: str
    canonical_key: str
    score: float


@dataclass(frozen=True)
class PlanResult:
    """Outcome of running the planner on raw caller input."""

    terms: List[PlannedTerm]
    dropped: List[str]


class QueryPlanner:
    """Builds the term plan that the worker pool will execute against."""

    def __init__(self, limits: SearchLimits):
        self._limits = limits

    def plan(self, raw_terms: Iterable[str]) -> PlanResult:
        by_key: dict[str, PlannedTerm] = {}
        dropped: List[str] = []

        for raw in raw_terms:
            term = self._sanitize(raw)
            if term is None:
                dropped.append(self._safe_preview(raw))
                continue

            for variant in self._expand_variants(term):
                key = self._canonical_key(variant)
                if not key:
                    if variant is term:
                        dropped.append(variant)
                    continue

                scored = PlannedTerm(
                    normalized=variant,
                    canonical_key=key,
                    score=self._score(variant),
                )
                existing = by_key.get(key)
                if existing is None:
                    by_key[key] = scored
                elif scored.score > existing.score:
                    dropped.append(existing.normalized)
                    by_key[key] = scored
                else:
                    dropped.append(variant)

        normalized = sorted(by_key.values(), key=lambda p: (-p.score, p.normalized))
        pinned_keys: set[str] = set()
        for raw in raw_terms:
            cleaned = self._sanitize(raw)
            if cleaned:
                key = self._canonical_key(cleaned)
                if key:
                    pinned_keys.add(key)

        pinned = [p for p in normalized if p.canonical_key in pinned_keys]
        variants = [p for p in normalized if p.canonical_key not in pinned_keys]
        budget = max(self._limits.max_terms, len(pinned))
        # Pinning only decides retention: caller catalog titles are never
        # dropped when under budget. Execution order is by score so
        # release-like nicknames run in the first worker wave.
        kept = pinned + variants[: max(0, budget - len(pinned))]
        kept.sort(key=lambda p: (-p.score, p.normalized))
        kept_keys = {p.canonical_key for p in kept}
        dropped.extend(p.normalized for p in normalized if p.canonical_key not in kept_keys)
        return PlanResult(terms=kept, dropped=dropped)

    @staticmethod
    def _expand_variants(term: str) -> Iterable[str]:
        """Yield the term plus search-effective variants when needed.

        Many torrent engines (notably nyaa.si full-text search) index
        Latin-extended characters as distinct tokens, so romanized
        Japanese titles like ``Shimetsu Kaiyū Zenpen`` never match
        torrents named ``Shimetsu Kaiyu Zenpen``. Emitting both
        variants keeps the user-supplied form intact (for engines that
        do match exact unicode) while broadening matches on engines
        that do not.

        Punctuation-loosened, dehyphenated, and shortened romanized
        prefixes recover releases named differently from catalog titles
        (e.g. ``Tai-Ari deshita.: Ojou-sama`` vs ``Tai-Ari deshita.
        Ojousama``).
        """
        variants: list[str] = []
        seen: set[str] = set()

        def add(text: str) -> None:
            if text and text not in seen:
                seen.add(text)
                variants.append(text)

        add(term)

        folded = _ascii_fold(term)
        if folded != term and any(ch.isalnum() for ch in folded):
            add(folded)

        loose = _loosen_punctuation(term)
        if loose != term:
            add(loose)
            folded_loose = _ascii_fold(loose)
            if folded_loose != loose and any(ch.isalnum() for ch in folded_loose):
                add(folded_loose)

        dehyphen_base = loose if loose != term else term
        dehyphenated = _dehyphenate_words(dehyphen_base)
        if dehyphenated != dehyphen_base:
            add(dehyphenated)

        if term.endswith(".") and len(term) > 2:
            add(term[:-1].rstrip())

        prefix = _romanized_prefix(loose if loose != term else term)
        if prefix:
            add(prefix)

        base = loose if loose != term else term
        lead = _leading_words_prefix(base)
        if lead:
            add(lead)

        for season_variant in _season_alias_variants(base):
            add(season_variant)
            folded_season = _ascii_fold(season_variant)
            if folded_season != season_variant:
                add(folded_season)

        season_base = _season_base_title(base)
        if season_base:
            add(season_base)
            folded_base = _ascii_fold(season_base)
            if folded_base != season_base:
                add(folded_base)

        return variants

    def _sanitize(self, raw: object) -> str | None:
        if not isinstance(raw, str):
            return None
        cleaned = unicodedata.normalize("NFKC", raw)
        cleaned = "".join(
            ch for ch in cleaned if ch == " " or not _is_control(ch)
        )
        cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
        if not cleaned:
            return None
        if len(cleaned) > self._limits.max_term_length:
            return None
        # Reject degenerate terms (only symbols/punctuation).
        if not any(ch.isalnum() for ch in cleaned):
            return None
        return cleaned

    @staticmethod
    def _canonical_key(term: str) -> str:
        lowered = term.lower()
        return "".join(ch for ch in lowered if ch.isalnum() or ch == " ").strip()

    @staticmethod
    def _score(term: str) -> float:
        """Score terms by likelihood of matching fansub release names.

        Short Latin nicknames (SubsPlease-style show segments such as
        ``Tenkosaki``) outrank long English marketing titles and CJK
        catalog dumps, so the worker pool searches high-precision terms
        in the first concurrent wave.
        """
        alnum = [ch for ch in term if ch.isalnum()]
        if not alnum:
            return 0.0
        # Cap distinct-char weight so long CJK strings cannot dominate.
        distinct_score = min(len(set(alnum)), 18)
        length = len(term)
        words = [w for w in term.split() if w]
        word_count = len(words)

        has_latin = bool(_LATIN_RE.search(term))
        has_cjk = bool(_CJK_RE.search(term))
        if has_latin and not has_cjk:
            if 6 <= length <= 32 and 1 <= word_count <= 3:
                # Compact release nicknames / season aliases.
                script_bonus = 3.2
            elif length <= 42 and word_count <= 5:
                script_bonus = 2.0
            elif length <= 60:
                script_bonus = 1.2
            else:
                script_bonus = 0.85
        elif has_latin and has_cjk:
            script_bonus = 1.1
        elif has_cjk and not has_latin:
            # Pure CJK catalog titles rarely match Latin-indexed nyaa names.
            script_bonus = 0.55 if length > 20 else 0.9
        else:
            script_bonus = 1.0

        sweet_spot = 1.0 if 6 <= length <= 40 else (0.75 if length <= 50 else 0.5)
        if length < 6:
            sweet_spot = 0.6

        punct_penalty = 0.7 if _PUNCT_CLUSTER_RE.search(term) else 1.0
        hyphen_penalty = 0.95 if re.search(r"[a-z]-[a-z]", term) else 1.0
        length_penalty = 0.35 if length > 70 else (0.55 if length > 50 else 1.0)
        paren_penalty = 0.65 if "(" in term or ")" in term else 1.0
        season_bonus = 1.15 if re.search(r"\bS\d{1,2}\b", term) else 1.0

        return (
            distinct_score
            * sweet_spot
            * script_bonus
            * punct_penalty
            * hyphen_penalty
            * length_penalty
            * paren_penalty
            * season_bonus
        )

    @staticmethod
    def _safe_preview(raw: object) -> str:
        text = repr(raw)
        return text if len(text) <= 80 else text[:77] + "..."


def _is_control(ch: str) -> bool:
    return unicodedata.category(ch).startswith("C")


def plan_terms(raw_terms: Sequence[str], limits: SearchLimits) -> PlanResult:
    """Functional helper used by the facade and tests."""
    return QueryPlanner(limits).plan(raw_terms)
