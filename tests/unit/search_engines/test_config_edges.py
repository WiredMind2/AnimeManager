"""Edge case tests for ``adapters.search.config`` profile/env loading."""

from __future__ import annotations

import os

import pytest

from search_engines.config import (
    DEFAULT_PROFILES,
    INTERACTIVE_PROFILE,
    SearchLimits,
    SearchProfile,
    STRICT_PROFILE,
    load_profile,
)


class TestDefaults:
    def test_interactive_profile_present(self):
        assert "interactive" in DEFAULT_PROFILES

    def test_strict_profile_present(self):
        assert "strict" in DEFAULT_PROFILES

    def test_profiles_are_frozen_dataclasses(self):
        with pytest.raises(Exception):
            INTERACTIVE_PROFILE.name = "x"  # type: ignore[misc]

    def test_default_limits_reasonable(self):
        limits = SearchLimits()
        assert limits.max_terms > 0
        assert limits.max_term_length > 0
        assert limits.queue_capacity > 0


class TestLoadProfile:
    def test_unknown_profile_falls_back_to_interactive(self):
        prof = load_profile("nonexistent")
        assert prof.name == "interactive"

    def test_default_loads_interactive(self):
        prof = load_profile()
        assert prof.name == "interactive"

    def test_strict_profile_loads(self):
        prof = load_profile("strict")
        assert prof.name == "strict"
        assert prof.rank_results is True

    def test_env_overrides_int_limits(self, monkeypatch):
        monkeypatch.setenv("ANIME_SEARCH_INTERACTIVE_MAX_TERMS", "42")
        prof = load_profile("interactive")
        assert prof.limits.max_terms == 42

    def test_env_overrides_float_limits(self, monkeypatch):
        monkeypatch.setenv("ANIME_SEARCH_INTERACTIVE_PER_JOB_TIMEOUT_S", "7.5")
        prof = load_profile("interactive")
        assert prof.limits.per_job_timeout_s == 7.5

    def test_invalid_int_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("ANIME_SEARCH_INTERACTIVE_MAX_TERMS", "garbage")
        prof = load_profile("interactive")
        # Should use the default value when env is malformed.
        assert prof.limits.max_terms == INTERACTIVE_PROFILE.limits.max_terms

    def test_invalid_float_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv(
            "ANIME_SEARCH_INTERACTIVE_PER_JOB_TIMEOUT_S", "not-a-float"
        )
        prof = load_profile("interactive")
        assert (
            prof.limits.per_job_timeout_s
            == INTERACTIVE_PROFILE.limits.per_job_timeout_s
        )

    def test_strict_env_prefix_does_not_affect_interactive(self, monkeypatch):
        # If user sets STRICT env keys, interactive profile must be unchanged.
        monkeypatch.setenv("ANIME_SEARCH_STRICT_MAX_TERMS", "99")
        prof = load_profile("interactive")
        assert prof.limits.max_terms == INTERACTIVE_PROFILE.limits.max_terms

    def test_all_env_keys_supported(self, monkeypatch):
        keys = [
            ("MAX_TERMS", "1"),
            ("MAX_TERM_LENGTH", "1"),
            ("MAX_CONCURRENT_JOBS", "1"),
            ("PER_JOB_TIMEOUT_S", "1"),
            ("REQUEST_DEADLINE_S", "1"),
            ("MAX_RESULTS_PER_TERM", "1"),
            ("MAX_OUTPUT_BYTES", "1"),
            ("MAX_LINE_BYTES", "1"),
            ("QUEUE_CAPACITY", "1"),
        ]
        for k, v in keys:
            monkeypatch.setenv(f"ANIME_SEARCH_INTERACTIVE_{k}", v)
        prof = load_profile("interactive")
        for attr in (
            "max_terms",
            "max_term_length",
            "max_concurrent_jobs",
            "per_job_timeout_s",
            "request_deadline_s",
            "max_results_per_term",
            "max_output_bytes",
            "max_line_bytes",
            "queue_capacity",
        ):
            assert getattr(prof.limits, attr) == 1

    def test_legacy_max_results_env_alias(self, monkeypatch):
        monkeypatch.setenv("ANIME_SEARCH_INTERACTIVE_MAX_RESULTS", "7")
        prof = load_profile("interactive")
        assert prof.limits.max_results_per_term == 7


class TestProfileConstruction:
    def test_construct_with_explicit_limits(self):
        limits = SearchLimits(max_terms=3, max_term_length=100)
        profile = SearchProfile(name="custom", limits=limits)
        assert profile.limits.max_terms == 3
        assert profile.allow_insecure_engines is False  # default

    def test_engines_tuple_allowed(self):
        profile = SearchProfile(name="x", engines=("a", "b"))
        assert profile.engines == ("a", "b")
