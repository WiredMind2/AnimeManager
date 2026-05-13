"""Tests for `adapters.persistence.query_builder` whitelisted query construction."""

from __future__ import annotations

import pytest

from ....adapters.persistence.query_builder import (
    ALLOWED_CRITERIA,
    AnimeListQuery,
    build_anime_list_query,
)


class TestBuildAnimeListQuery:
    def test_unknown_criteria_collapses_to_default(self):
        q = build_anime_list_query("DROP TABLE", (0, 50), hide_rated=True, user_id=4)
        assert "anime.status != 'UPCOMING'" in q.filter_clause
        assert "DROP" not in q.filter_clause

    def test_user_id_int_is_embedded_safely(self):
        q = build_anime_list_query("DEFAULT", (0, 10), hide_rated=False, user_id=12)
        assert "user_id=12" in q.table
        # No leftover quotes / spaces / sql tokens
        assert "DROP" not in q.table.upper()

    def test_user_id_rejects_non_numeric_string(self):
        # Strings that cannot be coerced to int are rejected before SQL is built.
        with pytest.raises((TypeError, ValueError)):
            build_anime_list_query(
                "DEFAULT",
                (0, 10),
                hide_rated=False,
                user_id="9; DROP TABLE",
            )
        with pytest.raises((TypeError, ValueError)):
            build_anime_list_query("DEFAULT", (0, 10), hide_rated=False, user_id="abc")

    def test_negative_range_is_clamped(self):
        q = build_anime_list_query("DEFAULT", (-5, -1), hide_rated=False, user_id=1)
        assert q.range[0] == 0
        assert q.range[1] >= q.range[0] + 1

    def test_status_filter_uses_whitelisted_literal(self):
        for criteria in ("UPCOMING", "FINISHED", "AIRING"):
            q = build_anime_list_query(criteria, (0, 10), hide_rated=False, user_id=1)
            assert f"status = '{criteria}'" in q.filter_clause
            assert q.params.get("status") == criteria

    def test_upcoming_sorts_ascending(self):
        q = build_anime_list_query("UPCOMING", (0, 10), hide_rated=False, user_id=1)
        assert q.sort == "ASC"

    def test_random_uses_random_order(self):
        q = build_anime_list_query("RANDOM", (0, 10), hide_rated=False, user_id=1)
        assert q.order == "RANDOM()"

    def test_watching_uses_broadcasts_join(self):
        q = build_anime_list_query("WATCHING", (0, 10), hide_rated=False, user_id=1)
        assert "broadcasts" in q.table
        assert q.params.get("tag") == "WATCHING"

    def test_hide_rated_appends_rating_guard(self):
        q = build_anime_list_query("DEFAULT", (0, 10), hide_rated=True, user_id=1)
        assert "rating NOT IN" in q.filter_clause

    def test_to_args_shape_is_legacy_compatible(self):
        q = build_anime_list_query("DEFAULT", (0, 10), hide_rated=True, user_id=1)
        args = q.to_args()
        assert set(args) == {"table", "sort", "range", "order", "filter"}

    def test_no_user_input_text_in_default_filter(self):
        # Confirm injection attempts in criteria do not leak through.
        for bad in (
            "DEFAULT'; DROP TABLE users;--",
            "<script>",
            "UNION SELECT 1",
            "",
            None,
        ):
            q = build_anime_list_query(bad, (0, 10), hide_rated=True, user_id=1)  # type: ignore[arg-type]
            assert "DROP" not in q.filter_clause.upper() or "DROP TABLE" not in q.filter_clause

    def test_allowed_criteria_is_complete(self):
        # All criteria the manager promises to support must be in the allow-list.
        for criteria in (
            "DEFAULT", "LIKED", "NONE", "UPCOMING", "FINISHED", "AIRING",
            "RATED", "RANDOM", "WATCHING", "SEEN", "WATCHLIST",
        ):
            assert criteria in ALLOWED_CRITERIA

    def test_returns_animelistquery_instance(self):
        q = build_anime_list_query("DEFAULT", (0, 10), hide_rated=False, user_id=1)
        assert isinstance(q, AnimeListQuery)
