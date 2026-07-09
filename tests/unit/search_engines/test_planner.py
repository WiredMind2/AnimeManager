"""Unit tests for ``search_engines.planner``."""

from __future__ import annotations

import pytest

from search_engines.config import SearchLimits
from search_engines.planner import QueryPlanner, plan_terms


@pytest.fixture
def limits() -> SearchLimits:
    return SearchLimits(max_terms=3, max_term_length=50)


def test_planner_normalizes_and_dedupes(limits):
    raw = [
        "  Tokyo  Revengers  ",
        "tokyo revengers",
        "TOKYO\u3000REVENGERS",  # ideographic space, NFKC collapses to regular
        "Bleach",
    ]

    plan = plan_terms(raw, limits)

    normalized = [term.normalized for term in plan.terms]
    # First three keep only one canonical form, the second slot is "Bleach".
    assert "Tokyo Revengers" in normalized
    assert "Bleach" in normalized
    assert len(plan.terms) == 2
    assert plan.dropped  # at least one duplicate dropped


def test_planner_caps_to_max_terms():
    limits = SearchLimits(max_terms=2, max_term_length=80)
    raw = ["Alpha Series", "Beta Saga", "Gamma Adventures", "Delta Tales"]

    plan = plan_terms(raw, limits)
    assert len(plan.terms) == 2
    assert len(plan.dropped) >= 2


def test_planner_strips_control_chars_and_drops_empty_or_symbolic_terms(limits):
    raw = ["", "   ", "\x00\nmalicious\t\r", "!!!", "ValidTitle"]

    plan = plan_terms(raw, limits)
    normalized = [term.normalized for term in plan.terms]
    # ``ValidTitle`` and the sanitized form of the control-char string both
    # survive. The empty/whitespace/symbol-only inputs are dropped.
    assert "ValidTitle" in normalized
    assert "malicious" in normalized
    # No surviving term contains control characters.
    for term in normalized:
        assert "\x00" not in term
        assert "\n" not in term
        assert "\t" not in term
        assert "\r" not in term


def test_planner_rejects_oversize_terms():
    limits = SearchLimits(max_terms=4, max_term_length=10)
    raw = ["abcdefghij", "abcdefghijk"]

    plan = plan_terms(raw, limits)
    assert [term.normalized for term in plan.terms] == ["abcdefghij"]


def test_planner_score_prefers_mixed_script(limits):
    raw = ["Naruto", "ナルト Naruto"]

    planner = QueryPlanner(limits)
    plan = planner.plan(raw)
    # Mixed-script term should outrank single-script.
    assert plan.terms[0].normalized == "ナルト Naruto"


def test_planner_handles_non_string_inputs(limits):
    raw = ["Valid Title", 12345, None]
    plan = plan_terms(raw, limits)
    assert [term.normalized for term in plan.terms] == ["Valid Title"]


def test_planner_emits_ascii_fold_for_diacritics(limits):
    """Romanized Japanese titles with macrons need an ASCII synonym.

    Engines such as nyaa.si index ``ū`` as a distinct token from
    ``u``, so the unmodified API title (e.g. ``Shimetsu Kaiyū Zenpen``)
    never matches torrents named ``Shimetsu Kaiyu Zenpen``. The planner
    must therefore emit both the original term and a folded variant.
    """
    plan = plan_terms(["Jujutsu Kaisen: Shimetsu Kaiyū Zenpen"], limits)
    normalized = [term.normalized for term in plan.terms]
    assert "Jujutsu Kaisen: Shimetsu Kaiyū Zenpen" in normalized
    assert "Jujutsu Kaisen: Shimetsu Kaiyu Zenpen" in normalized


def test_planner_does_not_duplicate_ascii_terms(limits):
    """ASCII-only terms must not generate a redundant folded variant."""
    plan = plan_terms(["Bleach"], limits)
    assert [term.normalized for term in plan.terms] == ["Bleach"]


TAI_ARI_PRIMARY = "Tai-Ari deshita.: Ojou-sama wa Kakutou Game nante Shinai"
TAI_ARI_SYNONYM = "Tai-Ari deshita. Ojousama wa Kakutou Game nante Shinai"


def test_planner_expands_punctuation_and_hyphen_variants_for_romanized_title():
    """Catalog titles with ``.: `` and hyphens must search the nyaa-friendly form."""
    limits = SearchLimits(max_terms=10, max_term_length=200)
    plan = plan_terms([TAI_ARI_PRIMARY, TAI_ARI_SYNONYM], limits)
    normalized = [term.normalized for term in plan.terms]
    assert TAI_ARI_SYNONYM in normalized
    assert TAI_ARI_PRIMARY not in normalized


def test_planner_emits_romanized_prefix_for_long_title():
    limits = SearchLimits(max_terms=10, max_term_length=200)
    plan = plan_terms([TAI_ARI_PRIMARY], limits)
    normalized = [term.normalized for term in plan.terms]
    assert "Tai-Ari deshita" in normalized


def test_planner_does_not_emit_prefix_for_short_english_title():
    limits = SearchLimits(max_terms=10, max_term_length=200)
    plan = plan_terms(["Young Ladies Don't Play Fighting Games"], limits)
    normalized = [term.normalized for term in plan.terms]
    assert "Young Ladies" not in normalized
