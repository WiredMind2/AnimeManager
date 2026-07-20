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
    # Raw catalog strings are always kept; variants fill remaining budget.
    assert len(plan.terms) >= len(raw)
    assert "Alpha Series" in [term.normalized for term in plan.terms]


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


def test_planner_score_prefers_short_latin_nickname(limits):
    """Release-style nicknames outrank mixed-script catalog forms."""
    raw = ["Naruto", "ナルト Naruto"]

    planner = QueryPlanner(limits)
    plan = planner.plan(raw)
    assert plan.terms[0].normalized == "Naruto"


def test_planner_orders_release_nickname_ahead_of_noisy_catalog_titles():
    """Tenkosaki-style expansions must run before long JP/EN marketing titles."""
    limits = SearchLimits(max_terms=12, max_term_length=200)
    jp = "転校先の清楚可憐な美少女が、昔男子と思って一緒に遊んだ幼馴染だった件"
    raw = [
        "Oh Boy, Was I Wrong About Her",
        "Tenbin",
        jp,
        TENKOSAKI_SYNONYM,
        "Tenkousaki no Seiso Karen na Bishoujo ga, Mukashi Danshi to Omotte "
        "Issho ni Asonda Osananajimi datta Ken",
    ]
    plan = plan_terms(raw, limits)
    normalized = [term.normalized for term in plan.terms]

    # Retention: every caller catalog title survives under budget.
    for title in raw:
        assert title in normalized

    # Execution order: short release nicknames ahead of long JP/EN strings.
    assert "Tenkosaki" in normalized
    tenkosaki_idx = normalized.index("Tenkosaki")
    assert tenkosaki_idx < normalized.index(jp)
    assert tenkosaki_idx < normalized.index("Oh Boy, Was I Wrong About Her")
    assert tenkosaki_idx <= 2


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


SAIJO_PRIMARY = (
    "Saijo no Osewa: Takane no Hanadarake na Meimonkou de, "
    "Gakuin Ichi no Ojousama (Seikatsu Nouryoku Kaimu) wo "
    "Kagenagara Osewa suru Koto ni Narimashita"
)


def test_planner_emits_colon_prefix_for_long_romanized_catalog_title():
    """Long API titles must search the short release name before the colon."""
    limits = SearchLimits(max_terms=10, max_term_length=200)
    plan = plan_terms([SAIJO_PRIMARY], limits)
    normalized = [term.normalized for term in plan.terms]
    assert "Saijo no Osewa" in normalized


TENKOSAKI_SYNONYM = (
    "Tenkosaki: The Neat and Pretty Girl at My New School Is a Childhood "
    "Friend of Mine Who I Thought Was a Boy"
)


def test_planner_emits_single_word_colon_prefix_for_release_nickname():
    """Fansub groups often use a one-word nyaa title before the colon."""
    limits = SearchLimits(max_terms=10, max_term_length=200)
    plan = plan_terms([TENKOSAKI_SYNONYM], limits)
    normalized = [term.normalized for term in plan.terms]
    assert "Tenkosaki" in normalized


def test_planner_emits_season_alias_for_catalog_title():
    limits = SearchLimits(max_terms=10, max_term_length=200)
    plan = plan_terms(["Grand Blue Season 3"], limits)
    normalized = [term.normalized for term in plan.terms]
    assert "Grand Blue S3" in normalized


def test_planner_emits_base_title_when_catalog_has_nth_season():
    """SubsPlease often keeps the S1 title and continues episode numbers."""
    limits = SearchLimits(max_terms=12, max_term_length=200)
    plan = plan_terms(["Seihantai na Kimi to Boku 2nd Season"], limits)
    normalized = [term.normalized for term in plan.terms]
    assert "Seihantai na Kimi to Boku" in normalized


def test_planner_emits_base_title_for_english_season_suffix():
    limits = SearchLimits(max_terms=12, max_term_length=200)
    plan = plan_terms(["You and I Are Polar Opposites Season 2"], limits)
    normalized = [term.normalized for term in plan.terms]
    assert "You and I Are Polar Opposites" in normalized
    assert "You and I Are Polar Opposites S2" in normalized


def test_planner_emits_leading_words_for_long_romanized_title():
    limits = SearchLimits(max_terms=10, max_term_length=200)
    title = "Suterare Seijo no Isekai Gohan Tabi: The Journey of a Discarded Saint"
    plan = plan_terms([title], limits)
    normalized = [term.normalized for term in plan.terms]
    assert "Suterare Seijo no Isekai Gohan Tabi" in normalized
