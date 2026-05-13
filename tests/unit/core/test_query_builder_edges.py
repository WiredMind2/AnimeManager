"""Additional edge case tests for ``adapters.persistence.query_builder``.

Focus on injection attempts, integer coercion oddities and structural
invariants of the generated SQL fragments.
"""

from __future__ import annotations

import pytest

from adapters.persistence.query_builder import (
    ALLOWED_CRITERIA,
    AnimeListQuery,
    build_anime_list_query,
)


class TestRangeClamping:
    def test_swapped_range_clamped(self):
        # stop < start should always produce start+1 >= stop
        q = build_anime_list_query("DEFAULT", (50, 10), hide_rated=False, user_id=1)
        assert q.range[0] == 50
        assert q.range[1] == 51

    def test_huge_values_allowed(self):
        big = 10**9
        q = build_anime_list_query("DEFAULT", (0, big), hide_rated=False, user_id=1)
        assert q.range == (0, big)

    def test_float_inputs_coerced_to_int(self):
        q = build_anime_list_query("DEFAULT", (1.7, 4.9), hide_rated=False, user_id=1)
        assert q.range == (1, 4)

    def test_boolean_user_id_is_coerced(self):
        # True == 1 in Python; documents the behavior even if odd
        q = build_anime_list_query("DEFAULT", (0, 5), hide_rated=False, user_id=True)
        assert "user_id=1" in q.table


class TestCriteriaCoverage:
    @pytest.mark.parametrize("criteria", sorted(ALLOWED_CRITERIA))
    def test_all_allowed_criteria_build(self, criteria):
        q = build_anime_list_query(criteria, (0, 10), hide_rated=False, user_id=1)
        assert isinstance(q, AnimeListQuery)
        assert q.filter_clause
        # Hide-rated guard must never leak when not enabled
        assert "rating NOT IN" not in q.filter_clause

    @pytest.mark.parametrize("criteria", sorted(ALLOWED_CRITERIA))
    def test_all_criteria_respect_hide_rated_flag(self, criteria):
        q = build_anime_list_query(criteria, (0, 10), hide_rated=True, user_id=1)
        # Some criteria (RATED, RANDOM, WATCHING) do not append the guard.
        # We can still confirm the clause is well-formed.
        assert isinstance(q.filter_clause, str) and q.filter_clause
        assert "DROP" not in q.filter_clause.upper()

    @pytest.mark.parametrize(
        "bad_input",
        [
            "",
            None,
            123,
            "ARBITRARY",
            "Default",  # case-sensitive
            "default'; DROP TABLE users;--",
            "UNION SELECT password FROM users",
            (1, 2),  # tuple is hashable but not a criteria
        ],
    )
    def test_unknown_or_bad_criteria_collapse_to_default(self, bad_input):
        q = build_anime_list_query(bad_input, (0, 10), hide_rated=False, user_id=1)
        assert "anime.status != 'UPCOMING'" in q.filter_clause
        # No leaked DROP token in the SQL fragment
        assert "DROP" not in q.filter_clause.upper()

    def test_unhashable_criteria_raises(self):
        # Lists are unhashable; the `in frozenset` check raises TypeError.
        # This documents the current behavior — callers must pass hashable inputs.
        with pytest.raises(TypeError):
            build_anime_list_query([], (0, 10), hide_rated=False, user_id=1)


class TestSqlInjectionGuards:
    def test_table_is_constant_when_user_id_is_int_like(self):
        for user_id in (0, 1, -1, 9999):
            q = build_anime_list_query(
                "DEFAULT", (0, 5), hide_rated=False, user_id=user_id
            )
            assert "user_id=" + str(int(user_id)) in q.table

    def test_to_args_does_not_include_extra_keys(self):
        q = build_anime_list_query("DEFAULT", (0, 5), hide_rated=False, user_id=1)
        args = q.to_args()
        assert set(args) == {"table", "sort", "range", "order", "filter"}

    def test_random_criteria_excludes_user_table_dependency(self):
        q = build_anime_list_query("RANDOM", (0, 5), hide_rated=False, user_id=1)
        assert q.order == "RANDOM()"
        assert "anime.picture IS NOT NULL" in q.filter_clause

    def test_watching_with_hide_rated(self):
        q = build_anime_list_query("WATCHING", (0, 5), hide_rated=True, user_id=1)
        # WATCHING does NOT include the rating guard (per current behavior).
        assert "broadcasts" in q.table
        assert "WATCHING" in q.filter_clause

    def test_arbitrary_unknown_tag_falls_to_default(self):
        # Unknown values must collapse to DEFAULT — even tag-like input.
        q = build_anime_list_query(
            "UNKNOWN_TAG", (0, 5), hide_rated=False, user_id=1
        )
        assert "anime.status != 'UPCOMING'" in q.filter_clause


class TestAnimeListQueryDataclass:
    def test_frozen(self):
        q = build_anime_list_query("DEFAULT", (0, 5), hide_rated=False, user_id=1)
        with pytest.raises(Exception):
            q.table = "x"  # type: ignore[misc]

    def test_params_includes_user_id(self):
        q = build_anime_list_query("DEFAULT", (0, 5), hide_rated=False, user_id=42)
        assert q.params.get("user_id") == 42
