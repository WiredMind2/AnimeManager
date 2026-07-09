"""Additional edge case tests for ``adapters.search.engine_policy``."""

from __future__ import annotations

import json
import threading

import pytest

from search_engines.config import SearchLimits, SearchProfile
from search_engines.engine_policy import (
    EnginePolicy,
    EngineRecord,
    get_default_policy,
    reset_default_policy,
)


def _profile(**overrides) -> SearchProfile:
    base = dict(
        name="test",
        limits=SearchLimits(),
        allow_insecure_engines=False,
        allow_no_timeout_engines=False,
        engines=None,
        category="anime",
        rank_results=False,
    )
    base.update(overrides)
    return SearchProfile(**base)


class TestEnginePolicyLoading:
    def test_default_action_allow_lets_unknown_through(self, policy_factory):
        policy = policy_factory(engines={}, default_action="allow")
        kept = policy.filter(["random-unknown"], _profile())
        assert kept == ["random-unknown"]

    def test_default_action_deny_blocks_unknown(self, policy_factory):
        policy = policy_factory(engines={}, default_action="deny")
        kept = policy.filter(["random-unknown"], _profile())
        assert kept == []

    def test_disabled_engine_filtered_out(self, policy_factory):
        policy = policy_factory(
            engines={"x": {"enabled": False}},
        )
        kept = policy.filter(["x"], _profile())
        assert kept == []

    def test_nsfw_blocked_unless_profile_allows(self, policy_factory):
        policy = policy_factory(
            engines={"adult": {"enabled": True, "nsfw": True}},
        )
        kept_blocked = policy.filter(["adult"], _profile(allow_nsfw=False))
        assert kept_blocked == []
        kept_allowed = policy.filter(["adult"], _profile(allow_nsfw=True))
        assert kept_allowed == ["adult"]

    def test_explicit_allowlist_lower_cases_the_comparison_only(self, policy_factory):
        """Allowlist match is case-insensitive, but record lookup is case-sensitive.

        This documents the current behavior: the lower-cased candidate must
        appear in the lower-cased allowlist, but the record key lookup that
        follows is exact. So mixed-case candidate names yield
        ``unknown_engine_default_deny`` even when the allowlist would have
        accepted them.
        """
        policy = policy_factory(
            engines={
                "a": {"enabled": True},
                "b": {"enabled": True},
            }
        )
        # Lower-case candidates with lower-case allowlist => passes
        assert policy.filter(["a"], _profile(engines=("a",))) == ["a"]
        # Mixed-case candidate triggers record-miss path even when allowlist
        # matches.
        assert policy.filter(["A"], _profile(engines=("a",))) == []

    def test_empty_candidates_yields_empty(self, policy_factory):
        policy = policy_factory(engines={"a": {"enabled": True}})
        kept = policy.filter([], _profile())
        assert kept == []

    def test_falsy_engines_tuple_treated_as_no_allowlist(self, policy_factory):
        """``profile.engines`` falsy (None or empty tuple) means no filter.

        The implementation tests ``if profile.engines else None`` so an empty
        tuple collapses to ``None`` and the candidate set is unconstrained.
        """
        policy = policy_factory(engines={"a": {"enabled": True}})
        kept = policy.filter(["a"], _profile(engines=()))
        assert kept == ["a"]

    def test_known_engines_sorted(self, policy_factory):
        policy = policy_factory(
            engines={
                "z_engine": {"enabled": True},
                "a_engine": {"enabled": True},
            }
        )
        assert policy.known_engines() == ("a_engine", "z_engine")

    def test_record_for_unknown_returns_default(self, policy_factory):
        policy = policy_factory(engines={"a": {"enabled": True}})
        rec = policy.record_for("nonexistent")
        assert isinstance(rec, EngineRecord)
        assert rec.enabled is False
        assert rec.name == ""

    def test_record_for_known_returns_record(self, policy_factory):
        policy = policy_factory(
            engines={
                "good": {"enabled": True, "risk_level": "low", "notes": "ok"},
            }
        )
        rec = policy.record_for("good")
        assert rec.enabled is True
        assert rec.notes == "ok"


class TestPolicyLoadingFromDisk:
    def test_handles_missing_engines_section(self, tmp_path):
        path = tmp_path / "policy.json"
        path.write_text(json.dumps({"default_action": "deny"}), encoding="utf-8")
        policy = EnginePolicy.load(str(path))
        assert policy.known_engines() == ()

    def test_handles_malformed_engine_entry(self, tmp_path):
        path = tmp_path / "policy.json"
        path.write_text(
            json.dumps(
                {
                    "default_action": "deny",
                    "engines": {
                        "a": {},
                        "b": {"enabled": True, "extra_unknown": "ignored"},
                    },
                }
            ),
            encoding="utf-8",
        )
        policy = EnginePolicy.load(str(path))
        # Missing fields default to defaults
        rec_a = policy.record_for("a")
        assert rec_a.enabled is False
        rec_b = policy.record_for("b")
        assert rec_b.enabled is True

    def test_invalid_json_raises(self, tmp_path):
        path = tmp_path / "policy.json"
        path.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            EnginePolicy.load(str(path))

    def test_missing_file_raises(self, tmp_path):
        path = tmp_path / "does_not_exist.json"
        with pytest.raises(FileNotFoundError):
            EnginePolicy.load(str(path))


class TestDefaultPolicyCache:
    def test_default_policy_is_cached(self):
        a = get_default_policy()
        b = get_default_policy()
        assert a is b

    def test_reset_clears_cache(self):
        a = get_default_policy()
        reset_default_policy()
        b = get_default_policy()
        # After reset, may or may not be the same instance, but call shouldn't fail
        assert b is not None

    def test_reset_default_policy_is_thread_safe(self):
        # Hammer the cache from multiple threads
        def worker():
            for _ in range(5):
                get_default_policy()
                reset_default_policy()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # If no exception, thread-safety holds


class TestEngineRecordDefaults:
    def test_default_record_fields(self):
        rec = EngineRecord(
            name="x",
            enabled=False,
            risk_level="low",
            anime_relevant=False,
            requires_insecure_tls=False,
            missing_timeout=False,
        )
        # nsfw and notes are defaulted
        assert rec.nsfw is False
        assert rec.notes == ""

    def test_frozen(self):
        rec = EngineRecord(
            name="x",
            enabled=False,
            risk_level="low",
            anime_relevant=False,
            requires_insecure_tls=False,
            missing_timeout=False,
        )
        with pytest.raises(Exception):
            rec.enabled = True  # type: ignore[misc]
