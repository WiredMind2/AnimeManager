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
        normalized: List[PlannedTerm] = []
        seen_keys: set[str] = set()
        dropped: List[str] = []

        for raw in raw_terms:
            term = self._sanitize(raw)
            if term is None:
                dropped.append(self._safe_preview(raw))
                continue

            for variant in self._expand_variants(term):
                key = self._canonical_key(variant)
                if not key or key in seen_keys:
                    if variant is term:
                        dropped.append(variant)
                    continue

                seen_keys.add(key)
                normalized.append(
                    PlannedTerm(
                        normalized=variant,
                        canonical_key=key,
                        score=self._score(variant),
                    )
                )

        normalized.sort(key=lambda p: (-p.score, p.normalized))
        kept = normalized[: self._limits.max_terms]
        dropped.extend(p.normalized for p in normalized[self._limits.max_terms :])
        return PlanResult(terms=kept, dropped=dropped)

    @staticmethod
    def _expand_variants(term: str) -> Iterable[str]:
        """Yield the term plus an ASCII-folded synonym when needed.

        Many torrent engines (notably nyaa.si full-text search) index
        Latin-extended characters as distinct tokens, so romanized
        Japanese titles like ``Shimetsu Kaiyū Zenpen`` never match
        torrents named ``Shimetsu Kaiyu Zenpen``. Emitting both
        variants keeps the user-supplied form intact (for engines that
        do match exact unicode) while broadening matches on engines
        that do not.
        """
        yield term
        folded = _ascii_fold(term)
        if folded != term and any(ch.isalnum() for ch in folded):
            yield folded

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
        return distinct * sweet_spot * script_bonus

    @staticmethod
    def _safe_preview(raw: object) -> str:
        text = repr(raw)
        return text if len(text) <= 80 else text[:77] + "..."


def _is_control(ch: str) -> bool:
    return unicodedata.category(ch).startswith("C")


def plan_terms(raw_terms: Sequence[str], limits: SearchLimits) -> PlanResult:
    """Functional helper used by the facade and tests."""
    return QueryPlanner(limits).plan(raw_terms)
