"""Optional Sentry integration for the HTTP client adapter."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

_LOG = logging.getLogger("animemanager.observability")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def init_sentry(app: FastAPI | None = None) -> bool:
    """Initialize Sentry when ``SENTRY_DSN`` is configured."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        _LOG.warning("SENTRY_DSN is set but sentry-sdk is not installed")
        return False

    traces_sample_rate = _env_float("SENTRY_TRACES_SAMPLE_RATE", 0.1)
    profile_session_sample_rate = _env_float("SENTRY_PROFILE_SESSION_SAMPLE_RATE", 0.0)
    init_kwargs: dict[str, Any] = {
        "dsn": dsn,
        "integrations": [
            StarletteIntegration(),
            FastApiIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        "traces_sample_rate": traces_sample_rate,
        "send_default_pii": _env_bool("SENTRY_SEND_DEFAULT_PII", False),
        "enable_logs": _env_bool("SENTRY_ENABLE_LOGS", True),
        "environment": os.environ.get("SENTRY_ENVIRONMENT", os.environ.get("NODE_ENV", "development")),
    }
    if profile_session_sample_rate > 0:
        init_kwargs["profile_session_sample_rate"] = profile_session_sample_rate
        lifecycle = os.environ.get("SENTRY_PROFILE_LIFECYCLE", "trace").strip()
        if lifecycle:
            init_kwargs["profile_lifecycle"] = lifecycle

    sentry_sdk.init(**init_kwargs)
    _LOG.info(
        "Sentry initialized traces_sample_rate=%s enable_logs=%s",
        traces_sample_rate,
        init_kwargs["enable_logs"],
    )
    return True
