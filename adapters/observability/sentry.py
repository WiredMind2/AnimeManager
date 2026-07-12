"""Optional Sentry integration for the HTTP client adapter."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

_LOG = logging.getLogger("animemanager.observability")

_OTEL_LOGGER_PREFIXES = (
    "opentelemetry.exporter.",
    "opentelemetry.sdk._shared_internal",
)

_STARTUP_NOISE_MESSAGES = (
    "Application startup failed. Exiting.",
    "Exception while exporting Log.",
    "Failed to export metrics batch",
)


def _logger_name(event: dict[str, Any]) -> str:
    logger = event.get("logger")
    if isinstance(logger, str):
        return logger
    return ""


def _is_otel_export_noise(event: dict[str, Any]) -> bool:
    name = _logger_name(event)
    if any(name.startswith(prefix) for prefix in _OTEL_LOGGER_PREFIXES):
        return True
    message = str(event.get("logentry", {}).get("message", "") or event.get("message", ""))
    return any(fragment in message for fragment in _STARTUP_NOISE_MESSAGES)


def _is_startup_interrupt(event: dict[str, Any], hint: dict[str, Any]) -> bool:
    exc_info = hint.get("exc_info")
    if exc_info and len(exc_info) >= 2 and exc_info[0] is KeyboardInterrupt:
        return True
    message = str(event.get("logentry", {}).get("message", "") or event.get("message", ""))
    if "Application startup failed. Exiting." not in message:
        return False
    exception_values = event.get("exception", {}).get("values") or []
    for entry in exception_values:
        exc_type = entry.get("type") or ""
        if exc_type in {"KeyboardInterrupt", "Empty", "_Empty"}:
            return True
        value = str(entry.get("value") or "")
        if "KeyboardInterrupt" in value or "_queue.Empty" in value:
            return True
    return False


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    if _is_otel_export_noise(event):
        return None
    if _is_startup_interrupt(event, hint):
        return None
    return event


def _before_send_log(log: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any] | None:
    if _is_otel_export_noise(log):
        return None
    return log


def init_sentry(app: FastAPI | None = None) -> bool:
    """Initialize Sentry when ``SENTRY_DSN`` is configured."""
    del app  # FastAPI integration is registered via FastApiIntegration()
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
        before_send=_before_send,
        before_send_log=_before_send_log,
    )
    _LOG.info("Sentry initialized")
    return True
