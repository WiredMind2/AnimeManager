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


def _romanized_prefix(term: str) -> str | None:
    """Emit a short prefix for long romanized titles (e.g. ``Tai-Ari deshita``)."""
    if len(term) < 40:
        return None
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
        kept = normalized[: self._limits.max_terms]
        dropped.extend(p.normalized for p in normalized[self._limits.max_terms :])
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

        prefix = _romanized_prefix(loose if loose != term else term)
        if prefix:
            add(prefix)

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
        """Score terms so the planner keeps the most discriminative ones.

        Heuristics:
          * Reward terms with more distinct alphanumeric characters.
          * Bonus when the term mixes scripts (e.g. Latin + CJK), which
            often signals an original title plus translated synonym.
          * Penalize extreme lengths (very short or very long).
        """
        alnum = [ch for ch in term if ch.isalnum()]
        distinct = len(set(alnum))
        if distinct == 0:
            return 0.0
        length = len(term)
        sweet_spot = 1.0 if 6 <= length <= 80 else 0.6
        script_bonus = 1.0
        if _LATIN_RE.search(term) and _CJK_RE.search(term):
            script_bonus = 1.4
        punct_penalty = 0.7 if _PUNCT_CLUSTER_RE.search(term) else 1.0
        hyphen_penalty = 0.95 if re.search(r"[a-z]-[a-z]", term) else 1.0
        return distinct * sweet_spot * script_bonus * punct_penalty * hyphen_penalty

    @staticmethod
    def _safe_preview(raw: object) -> str:
        text = repr(raw)
        return text if len(text) <= 80 else text[:77] + "..."


def _is_control(ch: str) -> bool:
    return unicodedata.category(ch).startswith("C")


def plan_terms(raw_terms: Sequence[str], limits: SearchLimits) -> PlanResult:
    """Functional helper used by the facade and tests."""
    return QueryPlanner(limits).plan(raw_terms)
