"""
Security primitives shared across the API->DB pipeline.

Centralizes outbound URL validation, secret loading, and log redaction so
every callsite enforces the same guarantees. Each helper is intentionally
free of side effects so it can be unit-tested in isolation.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import urlparse


__all__ = [
    "is_safe_url",
    "validate_url",
    "load_secret",
    "redact",
    "DEFAULT_ALLOWED_SCHEMES",
    "DEFAULT_PRIVATE_BLOCKLIST",
]


DEFAULT_ALLOWED_SCHEMES: Tuple[str, ...] = ("https",)
DEFAULT_PRIVATE_BLOCKLIST = (
    "is_loopback",
    "is_link_local",
    "is_unspecified",
    "is_multicast",
    "is_private",
    "is_reserved",
)

_SECRET_KEY_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|bearer|client[_-]?secret)"
)
_BEARER_PATTERN = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._\-]+")


def is_safe_url(
    url: str,
    *,
    allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
    allowed_hosts: Optional[Iterable[str]] = None,
    blocked_attrs: Iterable[str] = DEFAULT_PRIVATE_BLOCKLIST,
    resolver=None,
) -> bool:
    """Return True only if `url` passes scheme, host, and DNS safety checks.

    The function rejects:
      * URLs missing a scheme or hostname
      * Schemes outside `allowed_schemes`
      * Hostnames not in `allowed_hosts` (when provided)
      * Hostnames whose resolved IP is private/loopback/link-local/multicast/reserved/unspecified

    DNS resolution defaults to a late-bound `socket.gethostbyname` so unit
    tests can monkey-patch the module-level function.
    """
    return validate_url(
        url,
        allowed_schemes=allowed_schemes,
        allowed_hosts=allowed_hosts,
        blocked_attrs=blocked_attrs,
        resolver=resolver,
    )[0]


def validate_url(
    url: str,
    *,
    allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
    allowed_hosts: Optional[Iterable[str]] = None,
    blocked_attrs: Iterable[str] = DEFAULT_PRIVATE_BLOCKLIST,
    resolver=None,
) -> Tuple[bool, str]:
    """Same as `is_safe_url` but returns `(safe, reason)`.

    The reason string is suitable for logging without exposing the URL.
    """
    if not isinstance(url, str) or not url:
        return False, "empty_url"

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "unparseable"

    scheme = (parsed.scheme or "").lower()
    if scheme not in {s.lower() for s in allowed_schemes}:
        return False, f"scheme_blocked:{scheme or 'none'}"
    if scheme not in {"http", "https"}:
        # Even when explicitly allowlisted, non-HTTP schemes are treated as
        # non-routable in this helper; callsites should handle them directly.
        return False, "missing_host"

    host = (parsed.hostname or "").lower()
    if not host:
        return False, "missing_host"

    if allowed_hosts is not None:
        allow = {h.lower() for h in allowed_hosts}
        if host not in allow and not any(host.endswith("." + h) for h in allow):
            return False, "host_not_allowlisted"

    resolve = resolver if resolver is not None else socket.gethostbyname
    try:
        addr = resolve(host)
    except Exception:
        return False, "dns_failure"

    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False, "invalid_ip"

    for attr in blocked_attrs:
        if getattr(ip, attr, False):
            return False, f"ip_blocked:{attr}"

    return True, "ok"


def load_secret(
    key: str,
    *,
    settings: Optional[Dict[str, Any]] = None,
    env: Optional[Dict[str, str]] = None,
    default: Optional[str] = None,
) -> Optional[str]:
    """Load a secret with a strict priority: env var -> settings -> default.

    Environment is consulted first so deployments can override on-disk
    configuration without rewriting files. `settings` is a flat mapping or a
    nested dict containing the secret under `key`.

    The function trims surrounding whitespace and treats empty strings as
    missing, returning `default` instead.
    """
    env_source = env if env is not None else os.environ
    raw = env_source.get(key)
    if raw is None and settings is not None:
        raw = _lookup_nested(settings, key)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return default
    if isinstance(raw, str):
        return raw.strip()
    return raw


def _lookup_nested(settings: Dict[str, Any], key: str) -> Optional[Any]:
    """Look up `key` in a settings dict, supporting dotted paths."""
    if key in settings:
        return settings[key]
    if "." not in key:
        return None
    cursor: Any = settings
    for part in key.split("."):
        if isinstance(cursor, dict) and part in cursor:
            cursor = cursor[part]
        else:
            return None
    return cursor


def redact(value: Any) -> Any:
    """Return a copy of `value` with secrets masked for safe logging.

    Strings have bearer tokens collapsed to `Bearer ***`. Dicts have any key
    matching a known secret pattern replaced with `***`. Other types are
    returned unchanged.
    """
    if isinstance(value, dict):
        return {k: ("***" if _SECRET_KEY_PATTERN.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact(v) for v in value)
    if isinstance(value, str):
        return _BEARER_PATTERN.sub("Bearer ***", value)
    return value
