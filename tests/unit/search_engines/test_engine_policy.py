"""Unit tests for ``search_engines.engine_policy``."""

from __future__ import annotations

from search_engines.config import SearchProfile, SearchLimits
from search_engines.engine_policy import EnginePolicy, get_default_policy


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


def test_policy_blocks_insecure_tls_by_default(policy_factory):
    policy = policy_factory(
        engines={
            "safe": {"enabled": True, "risk_level": "low"},
            "unsafe": {
                "enabled": True,
                "risk_level": "high",
                "requires_insecure_tls": True,
            },
        }
    )

    kept = policy.filter(["safe", "unsafe"], _profile())
    assert kept == ["safe"]


def test_policy_allows_insecure_when_profile_opts_in(policy_factory):
    policy = policy_factory(
        engines={
            "unsafe": {
                "enabled": True,
                "requires_insecure_tls": True,
            }
        }
    )
    kept = policy.filter(["unsafe"], _profile(allow_insecure_engines=True))
    assert kept == ["unsafe"]


def test_policy_blocks_missing_timeout_in_strict_mode(policy_factory):
    policy = policy_factory(
        engines={
            "slow": {"enabled": True, "missing_timeout": True},
        }
    )
    kept = policy.filter(["slow"], _profile(name="strict"))
    assert kept == []
    kept_interactive = policy.filter(
        ["slow"], _profile(name="interactive", allow_no_timeout_engines=True)
    )
    assert kept_interactive == ["slow"]


def test_policy_explicit_allowlist_overrides_default(policy_factory):
    policy = policy_factory(
        engines={
            "a": {"enabled": True},
            "b": {"enabled": True},
        }
    )
    kept = policy.filter(["a", "b"], _profile(engines=("a",)))
    assert kept == ["a"]


def test_policy_unknown_engine_denied_by_default(policy_factory):
    policy = policy_factory(engines={})
    kept = policy.filter(["mystery"], _profile())
    assert kept == []


def test_default_policy_lists_known_engines():
    policy = get_default_policy()
    known = policy.known_engines()
    assert "nyaasi" in known
    assert "limetorrents" in known
    # Insecure engines are present but disabled.
    record = policy.record_for("limetorrents")
    assert record.requires_insecure_tls is True
    assert record.enabled is False
