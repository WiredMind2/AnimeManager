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
    "Failed to export logs batch",
    "Failed to export span batch",
)

_OTLP_NOISE_FRAGMENTS = (
    ":4318",
    "/v1/logs",
    "/v1/metrics",
    "/v1/traces",
    "otlp",
)

_OTLP_EXCEPTION_TYPES = frozenset(
    {
        "ConnectionError",
        "NewConnectionError",
        "MaxRetryError",
        "RemoteDisconnected",
        "ProtocolError",
    }
)


def _logger_name(event: dict[str, Any]) -> str:
    logger = event.get("logger")
    if isinstance(logger, str):
        return logger
    return ""


def _event_message(event: dict[str, Any]) -> str:
    return str(event.get("logentry", {}).get("message", "") or event.get("message", ""))


def _exception_text(event: dict[str, Any], hint: dict[str, Any] | None = None) -> str:
    parts: list[str] = []
    if hint:
        exc_info = hint.get("exc_info")
        if exc_info and len(exc_info) >= 2 and exc_info[1] is not None:
            parts.append(f"{type(exc_info[1]).__name__}: {exc_info[1]}")
    for entry in event.get("exception", {}).get("values") or []:
        exc_type = entry.get("type") or ""
        value = entry.get("value") or ""
        parts.append(f"{exc_type}: {value}")
    return " ".join(parts)


def _is_otel_export_noise(event: dict[str, Any]) -> bool:
    name = _logger_name(event)
    if any(name.startswith(prefix) for prefix in _OTEL_LOGGER_PREFIXES):
        return True
    message = _event_message(event)
    return any(fragment in message for fragment in _STARTUP_NOISE_MESSAGES)


def _is_otlp_connection_noise(event: dict[str, Any], hint: dict[str, Any]) -> bool:
    """Drop ConnectionError-style events aimed at a missing OTLP collector."""
    text = f"{_event_message(event)} {_exception_text(event, hint)}".lower()
    if not any(fragment in text for fragment in _OTLP_NOISE_FRAGMENTS):
        return False

    if hint:
        exc_info = hint.get("exc_info")
        if exc_info and len(exc_info) >= 2 and exc_info[1] is not None:
            if type(exc_info[1]).__name__ in _OTLP_EXCEPTION_TYPES:
                return True
            # urllib3 wraps NewConnectionError inside ConnectionError / MaxRetryError
            if isinstance(exc_info[1], OSError):
                return True

    for entry in event.get("exception", {}).get("values") or []:
        if (entry.get("type") or "") in _OTLP_EXCEPTION_TYPES:
            return True
    return False


def _is_startup_interrupt(event: dict[str, Any], hint: dict[str, Any]) -> bool:
    exc_info = hint.get("exc_info")
    if exc_info and len(exc_info) >= 2 and exc_info[0] is KeyboardInterrupt:
        return True
    message = _event_message(event)
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
    if _is_otlp_connection_noise(event, hint):
        return None
    if _is_startup_interrupt(event, hint):
        return None
    return event


def _before_send_log(log: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any] | None:
    if _is_otel_export_noise(log):
        return None
    if _is_otlp_connection_noise(log, _hint or {}):
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
