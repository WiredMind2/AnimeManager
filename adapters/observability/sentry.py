"""Optional Sentry integration for the HTTP client adapter."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

_LOG = logging.getLogger("animemanager.observability")


def init_sentry(app: FastAPI | None = None) -> bool:
    """Initialize Sentry when ``SENTRY_DSN`` is configured."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        _LOG.warning("SENTRY_DSN is set but sentry-sdk is not installed")
        return False

    traces_sample_rate = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
    sentry_sdk.init(
        dsn=dsn,
        integrations=[
            FastApiIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,
    )
    _LOG.info("Sentry initialized")
    return True
