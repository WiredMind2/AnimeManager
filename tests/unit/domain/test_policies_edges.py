"""Edge case tests for ``domain.policies``.

Exercises ``derive_status`` and ``normalize_search_query`` against the
boundary conditions documented in ADR 0002.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from domain.policies import derive_status, normalize_search_query


# ---------------------------------------------------------------------------
# derive_status
# ---------------------------------------------------------------------------


class TestDeriveStatus:
    def test_explicit_status_passthrough(self):
        assert derive_status("AIRING", None, None, None) == "AIRING"
        assert derive_status("FINISHED", None, None, None) == "FINISHED"

    def test_update_status_normalises_to_unknown(self):
        assert derive_status("UPDATE", None, None, None) == "UNKNOWN"

    def test_no_status_and_no_date_from_is_unknown(self):
        assert derive_status(None, None, None, None) == "UNKNOWN"
        assert derive_status("", None, None, None) == "UNKNOWN"

    def test_upcoming_when_date_from_in_future(self):
        future = int(
            (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
        )
        assert derive_status(None, future, None, None) == "UPCOMING"

    def test_finished_for_single_episode_with_known_start(self):
        past = int(
            (datetime.now(timezone.utc) - timedelta(days=365)).timestamp()
        )
        assert derive_status(None, past, None, 1) == "FINISHED"

    def test_airing_when_started_but_no_end(self):
        past = int(
            (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
        )
        assert derive_status(None, past, None, 12) == "AIRING"

    def test_finished_when_end_in_past(self):
        date_from = int(
            (datetime.now(timezone.utc) - timedelta(days=400)).timestamp()
        )
        date_to = int(
            (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
        )
        assert derive_status(None, date_from, date_to, 12) == "FINISHED"

    def test_airing_when_end_in_future(self):
        date_from = int(
            (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
        )
        date_to = int(
            (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
        )
        assert derive_status(None, date_from, date_to, 12) == "AIRING"

    def test_at_epoch_dates(self):
        # date_from == 0 is in the distant past, so airing-or-finished branch
        # should pick a deterministic answer.
        result = derive_status(None, 0, None, 12)
        assert result in {"AIRING", "FINISHED"}


# ---------------------------------------------------------------------------
# normalize_search_query
# ---------------------------------------------------------------------------


class TestNormalizeSearchQuery:
    @pytest.mark.parametrize("value", ["", None])
    def test_returns_empty_for_empty_input(self, value):
        assert normalize_search_query(value) == ""

    def test_strips_punctuation(self):
        assert normalize_search_query("Hello, World!") == "Hello World"

    def test_collapses_whitespace(self):
        assert normalize_search_query("  foo   bar  ") == "foo bar"

    def test_strips_tabs_and_newlines(self):
        assert normalize_search_query("foo\tbar\nbaz") == "foo bar baz"

    def test_unicode_letters_are_preserved(self):
        assert normalize_search_query("ナルト Naruto") == "ナルト Naruto"

    def test_only_punctuation_becomes_empty(self):
        assert normalize_search_query("!!!,,,?!") == ""

    def test_zero_width_chars_replaced_with_space(self):
        # Zero-width joiner is not alnum.
        out = normalize_search_query("foo\u200dbar")
        assert "\u200d" not in out

    def test_control_chars_removed(self):
        out = normalize_search_query("foo\x00bar")
        assert "\x00" not in out

    def test_emoji_replaced_with_space(self):
        out = normalize_search_query("foo 🎉 bar")
        assert "🎉" not in out
        assert "foo" in out and "bar" in out

    def test_long_input(self):
        out = normalize_search_query("a " * 500)
        assert out.startswith("a ")
        assert out.endswith("a")
