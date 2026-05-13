"""Tests for `shared.security` URL validation, secret loading, and redaction."""

from __future__ import annotations

import pytest

from ....shared.security import (
    DEFAULT_ALLOWED_SCHEMES,
    is_safe_url,
    load_secret,
    redact,
    validate_url,
)


class TestValidateUrl:
    def test_rejects_empty(self):
        assert validate_url("") == (False, "empty_url")

    def test_rejects_non_https(self):
        ok, reason = validate_url("http://example.com/x")
        assert ok is False
        assert reason.startswith("scheme_blocked")

    def test_rejects_missing_host(self):
        assert validate_url("https:///path") == (False, "missing_host")

    def test_accepts_public_host(self):
        ok, reason = validate_url(
            "https://example.com/x",
            resolver=lambda host: "8.8.8.8",
        )
        assert ok is True
        assert reason == "ok"

    @pytest.mark.parametrize(
        "addr,expected",
        [
            ("127.0.0.1", "ip_blocked:is_loopback"),
            ("10.0.0.1", "ip_blocked:is_private"),
            ("169.254.0.1", "ip_blocked:is_link_local"),
            ("224.0.0.1", "ip_blocked:is_multicast"),
            ("0.0.0.0", "ip_blocked:is_unspecified"),
        ],
    )
    def test_rejects_private_or_reserved(self, addr, expected):
        ok, reason = validate_url(
            "https://example.com/x",
            resolver=lambda host: addr,
        )
        assert ok is False
        assert reason == expected

    def test_honors_allow_list(self):
        ok, _ = validate_url(
            "https://blocked.example.com/x",
            allowed_hosts={"good.example.com"},
            resolver=lambda host: "8.8.8.8",
        )
        assert ok is False
        ok, _ = validate_url(
            "https://good.example.com/x",
            allowed_hosts={"good.example.com"},
            resolver=lambda host: "8.8.8.8",
        )
        assert ok is True

    def test_honors_allow_list_subdomain(self):
        ok, _ = validate_url(
            "https://api.example.com/x",
            allowed_hosts={"example.com"},
            resolver=lambda host: "8.8.8.8",
        )
        assert ok is True

    def test_dns_failure_blocks(self):
        def bad_resolver(host):
            raise OSError("dns down")

        ok, reason = validate_url(
            "https://example.com/x",
            resolver=bad_resolver,
        )
        assert ok is False
        assert reason == "dns_failure"

    def test_is_safe_url_thin_wrapper(self):
        assert is_safe_url(
            "https://example.com",
            resolver=lambda h: "8.8.8.8",
        ) is True
        assert is_safe_url("ftp://example.com") is False

    def test_default_schemes_only_https(self):
        assert "https" in DEFAULT_ALLOWED_SCHEMES
        assert "http" not in DEFAULT_ALLOWED_SCHEMES


class TestLoadSecret:
    def test_env_takes_precedence(self):
        out = load_secret(
            "TOKEN",
            env={"TOKEN": "env-value"},
            settings={"TOKEN": "settings-value"},
        )
        assert out == "env-value"

    def test_falls_back_to_settings(self):
        out = load_secret(
            "TOKEN",
            env={},
            settings={"TOKEN": "settings-value"},
        )
        assert out == "settings-value"

    def test_respects_nested_settings(self):
        out = load_secret(
            "section.subkey",
            env={},
            settings={"section": {"subkey": "nested"}},
        )
        assert out == "nested"

    def test_empty_string_is_missing(self):
        out = load_secret(
            "TOKEN",
            env={"TOKEN": "   "},
            settings=None,
            default="fallback",
        )
        assert out == "fallback"

    def test_default_when_missing(self):
        assert load_secret("missing", env={}, default=None) is None


class TestRedact:
    def test_redacts_bearer_in_string(self):
        out = redact("Authorization: Bearer abc.def.ghi")
        assert "abc.def.ghi" not in out
        assert "Bearer ***" in out

    def test_redacts_secret_keys(self):
        data = {"password": "p", "token": "t", "name": "ok", "client_secret": "s"}
        out = redact(data)
        assert out["password"] == "***"
        assert out["token"] == "***"
        assert out["client_secret"] == "***"
        assert out["name"] == "ok"

    def test_recursive(self):
        data = {"outer": {"api_key": "x", "y": [1, "Bearer ttt"]}}
        out = redact(data)
        assert out["outer"]["api_key"] == "***"
        assert "ttt" not in out["outer"]["y"][1]
