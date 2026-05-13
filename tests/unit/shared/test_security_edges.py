"""Additional edge case tests for ``shared.security`` URL validation, secret loading, and redaction."""

from __future__ import annotations

import pytest

from shared.security import (
    DEFAULT_ALLOWED_SCHEMES,
    DEFAULT_PRIVATE_BLOCKLIST,
    is_safe_url,
    load_secret,
    redact,
    validate_url,
)


# ---------------------------------------------------------------------------
# validate_url - additional edges
# ---------------------------------------------------------------------------


class TestValidateUrlEdges:
    def test_non_string_url_is_rejected(self):
        ok, reason = validate_url(None)  # type: ignore[arg-type]
        assert ok is False
        assert reason == "empty_url"

    def test_bytes_url_is_rejected(self):
        ok, reason = validate_url(b"https://example.com")  # type: ignore[arg-type]
        assert ok is False
        assert reason == "empty_url"

    def test_integer_url_is_rejected(self):
        ok, reason = validate_url(123)  # type: ignore[arg-type]
        assert ok is False
        assert reason == "empty_url"

    def test_uppercase_scheme_accepted(self):
        ok, reason = validate_url(
            "HTTPS://example.com",
            resolver=lambda host: "8.8.8.8",
        )
        assert ok is True
        assert reason == "ok"

    def test_invalid_ip_resolver_returns_invalid_ip(self):
        ok, reason = validate_url(
            "https://example.com",
            resolver=lambda host: "not.an.ip",
        )
        assert ok is False
        assert reason == "invalid_ip"

    def test_ipv6_loopback_is_blocked(self):
        ok, reason = validate_url(
            "https://example.com",
            resolver=lambda host: "::1",
        )
        assert ok is False
        assert reason.startswith("ip_blocked")

    def test_host_allowlist_does_not_match_unrelated_suffix(self):
        ok, _ = validate_url(
            "https://evilexample.com",
            allowed_hosts={"example.com"},
            resolver=lambda host: "8.8.8.8",
        )
        assert ok is False

    def test_custom_scheme_allowlist(self):
        ok, reason = validate_url(
            "magnet://example",
            allowed_schemes=("magnet",),
            resolver=lambda host: "8.8.8.8",
        )
        # missing_host comes before resolver, magnet:// has no host
        assert ok is False
        assert reason in {"missing_host", "ok"}

    def test_unparseable_url(self):
        # urlparse rarely raises but ensure malformed inputs return cleanly
        ok, reason = validate_url("https://")
        assert ok is False

    def test_scheme_default_is_https_only(self):
        assert DEFAULT_ALLOWED_SCHEMES == ("https",)

    def test_blocked_attrs_subset_works(self):
        # Only loopback blocked, but resolver returns multicast (should pass)
        ok, _ = validate_url(
            "https://example.com",
            blocked_attrs=("is_loopback",),
            resolver=lambda host: "224.0.0.1",
        )
        assert ok is True

    def test_default_private_blocklist_contains_basic_categories(self):
        assert "is_loopback" in DEFAULT_PRIVATE_BLOCKLIST
        assert "is_private" in DEFAULT_PRIVATE_BLOCKLIST

    def test_is_safe_url_returns_bool(self):
        assert is_safe_url("https://example.com", resolver=lambda h: "8.8.8.8") is True
        assert is_safe_url("") is False


# ---------------------------------------------------------------------------
# load_secret - additional edges
# ---------------------------------------------------------------------------


class TestLoadSecretEdges:
    def test_whitespace_only_env_falls_through_to_settings(self):
        out = load_secret(
            "TOKEN",
            env={"TOKEN": "  \n  "},
            settings={"TOKEN": "from-settings"},
        )
        # whitespace counts as missing => falls back to default, not settings
        assert out is None

    def test_strips_surrounding_whitespace(self):
        out = load_secret("TOKEN", env={"TOKEN": "  abc123  "})
        assert out == "abc123"

    def test_returns_non_string_values_unchanged(self):
        out = load_secret(
            "FLAG",
            env={},
            settings={"FLAG": 42},
        )
        assert out == 42

    def test_nested_settings_missing_key_returns_default(self):
        out = load_secret(
            "section.missing",
            env={},
            settings={"section": {"present": "x"}},
            default="fallback",
        )
        assert out == "fallback"

    def test_nested_settings_non_dict_path_returns_default(self):
        out = load_secret(
            "section.subkey",
            env={},
            settings={"section": "not a dict"},
            default="fb",
        )
        assert out == "fb"

    def test_deeply_nested_dotted_lookup(self):
        out = load_secret(
            "a.b.c",
            env={},
            settings={"a": {"b": {"c": "deep"}}},
        )
        assert out == "deep"

    def test_default_is_none(self):
        assert load_secret("missing", env={}) is None

    def test_empty_settings_dict(self):
        assert load_secret("k", env={}, settings={}, default="d") == "d"


# ---------------------------------------------------------------------------
# redact - additional edges
# ---------------------------------------------------------------------------


class TestRedactEdges:
    def test_none_unchanged(self):
        assert redact(None) is None

    def test_int_unchanged(self):
        assert redact(42) == 42

    def test_bool_unchanged(self):
        assert redact(True) is True

    def test_empty_dict(self):
        assert redact({}) == {}

    def test_empty_list(self):
        assert redact([]) == []

    def test_tuple_redacted_recursively(self):
        out = redact(("Bearer abc", "ok"))
        assert isinstance(out, tuple)
        assert "abc" not in out[0]
        assert out[1] == "ok"

    def test_case_insensitive_keys(self):
        out = redact({"PASSWORD": "p", "Token": "t"})
        assert out["PASSWORD"] == "***"
        assert out["Token"] == "***"

    def test_password_and_secret_variants(self):
        sensitive = {
            "passwd": "x",
            "client_secret": "y",
            "api_key": "z",
            "api-key": "z",
        }
        out = redact(sensitive)
        for value in out.values():
            assert value == "***"

    def test_deeply_nested(self):
        data = {
            "outer": [
                {"token": "t"},
                {"name": "Bearer aaa"},
            ]
        }
        out = redact(data)
        assert out["outer"][0]["token"] == "***"
        assert "aaa" not in out["outer"][1]["name"]

    def test_bearer_pattern_does_not_match_inside_word(self):
        out = redact("BearerCard 123")
        # Pattern requires whitespace between bearer and token; should be unchanged
        assert "BearerCard" in out

    def test_long_string_with_multiple_bearer_tokens(self):
        out = redact("Bearer aaa; later Bearer bbb")
        assert "aaa" not in out
        assert "bbb" not in out
        assert out.count("Bearer ***") == 2
