"""Additional edge case tests for ``adapters.search.planner``."""

from __future__ import annotations

import pytest

from search_engines.config import SearchLimits
from search_engines.planner import QueryPlanner, plan_terms


@pytest.fixture
def limits():
    return SearchLimits(max_terms=5, max_term_length=80)


class TestSanitisation:
    @pytest.mark.parametrize(
        "raw",
        [None, 12345, 1.5, True, False, object()],
    )
    def test_non_string_inputs_rejected(self, raw, limits):
        plan = plan_terms([raw], limits)
        assert plan.terms == []
        assert plan.dropped  # something was dropped

    def test_empty_string_dropped(self, limits):
        plan = plan_terms([""], limits)
        assert plan.terms == []

    def test_whitespace_only_dropped(self, limits):
        plan = plan_terms(["    \t\n   "], limits)
        assert plan.terms == []

    def test_symbol_only_dropped(self, limits):
        plan = plan_terms(["!!!???..."], limits)
        assert plan.terms == []

    def test_term_exactly_at_max_length_kept(self):
        limits = SearchLimits(max_terms=5, max_term_length=5)
        plan = plan_terms(["abcde"], limits)
        assert [t.normalized for t in plan.terms] == ["abcde"]

    def test_term_above_max_length_dropped(self):
        limits = SearchLimits(max_terms=5, max_term_length=5)
        plan = plan_terms(["abcdef"], limits)
        assert plan.terms == []

    def test_control_chars_stripped(self, limits):
        plan = plan_terms(["fo\x00o ba\x01r"], limits)
        assert plan.terms
        assert "\x00" not in plan.terms[0].normalized

    def test_nfkc_normalisation_applied(self, limits):
        plan = plan_terms(["ﬁle"], limits)  # ligature
        assert plan.terms
        assert plan.terms[0].normalized.startswith("fi")


class TestDeduplication:
    def test_duplicates_with_different_case_collapse(self, limits):
        plan = plan_terms(["Naruto", "naruto", "NARUTO"], limits)
        assert len(plan.terms) == 1
        assert plan.dropped

    def test_duplicates_with_different_whitespace_collapse(self, limits):
        plan = plan_terms(["Tokyo Revengers", "  Tokyo   Revengers  "], limits)
        assert len(plan.terms) == 1

    def test_distinct_terms_preserved(self, limits):
        plan = plan_terms(["Alpha", "Beta", "Gamma"], limits)
        assert len(plan.terms) == 3


class TestMaxTermsCap:
    def test_zero_max_terms_keeps_nothing(self):
        limits = SearchLimits(max_terms=0, max_term_length=20)
        plan = plan_terms(["a", "b", "c"], limits)
        assert plan.terms == []
        # The dropped list should mirror what got cut.
        assert len(plan.dropped) >= 3

    def test_keeps_highest_scored_first(self):
        limits = SearchLimits(max_terms=1, max_term_length=80)
        plan = plan_terms(["a", "Naruto X Bleach"], limits)
        assert len(plan.terms) == 1
        # The longer mixed-content term should outrank the single character
        assert plan.terms[0].normalized == "Naruto X Bleach"


class TestScoreBranches:
    def test_score_zero_when_no_alphanumerics_after_normalisation(self):
        planner = QueryPlanner(SearchLimits(max_terms=5, max_term_length=80))
        assert planner._score("") == 0.0

    def test_planresult_dropped_is_list(self):
        plan = plan_terms(["valid"], SearchLimits(max_terms=5, max_term_length=80))
        assert isinstance(plan.dropped, list)
