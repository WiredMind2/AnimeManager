"""Optional OpenTelemetry integration for the HTTP client adapter."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

_LOG = logging.getLogger("animemanager.observability")

_INITIALIZED = False
_LOG_HANDLER_ATTACHED = False
_INSTRUMENTED = False


def _log_export_level() -> int:
    raw = os.environ.get("OTEL_LOG_LEVEL", "INFO").strip().upper()
    return {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
    }.get(raw, logging.INFO)


def _attach_log_handler(resource) -> bool:
    """Attach an OTLP LoggingHandler to the animemanager logger namespace."""
    global _LOG_HANDLER_ATTACHED
    if _LOG_HANDLER_ATTACHED:
        return False
    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    except ImportError:
        _LOG.warning("OpenTelemetry log export packages are not installed")
        return False

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter())
    )
    set_logger_provider(logger_provider)

    handler = LoggingHandler(
        level=_log_export_level(),
        logger_provider=logger_provider,
    )
    root_logger = logging.getLogger("animemanager")
    root_logger.addHandler(handler)
    _LOG_HANDLER_ATTACHED = True
    _LOG.info("OpenTelemetry log export attached to animemanager logger")
    return True


def instrument_fastapi_app(app: FastAPI) -> bool:
    """Attach FastAPI auto-instrumentation middleware before the ASGI stack is built.

    Must be called at module import time (before uvicorn's first ``__call__``).
    The lifespan handler wires the real :class:`TracerProvider` later via
    :func:`init_opentelemetry`; the proxy tracer obtained here delegates to it.
    """
    global _INSTRUMENTED
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return False
    if _INSTRUMENTED:
        return True
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        _LOG.warning(
            "OTEL_EXPORTER_OTLP_ENDPOINT is set but opentelemetry-instrumentation-fastapi "
            "is not installed"
        )
        return False

    try:
        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:  # pragma: no cover - defensive
        _LOG.warning("FastAPI OpenTelemetry instrumentation failed: %s", exc)
        return False

    _INSTRUMENTED = True
    _LOG.info("FastAPI OpenTelemetry instrumentation attached")
    return True


def init_opentelemetry(app: FastAPI | None = None) -> bool:
    """Initialize OpenTelemetry when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set."""
    global _INITIALIZED
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return False
    if _INITIALIZED:
        return True
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        try:
            from adapters.observability.telemetry_bridge import start_metrics_export
        except ImportError:
            from .telemetry_bridge import start_metrics_export
    except ImportError:
        _LOG.warning(
            "OTEL_EXPORTER_OTLP_ENDPOINT is set but opentelemetry packages are not installed"
        )
        return False

    service_name = os.environ.get("OTEL_SERVICE_NAME", "animemanager-http")
    resource = Resource.create({"service.name": service_name})

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    start_metrics_export(resource)
    _attach_log_handler(resource)

    _INITIALIZED = True
    _LOG.info(
        "OpenTelemetry initialized service=%s endpoint=%s traces=on metrics=on logs=on",
        service_name,
        endpoint,
    )
    return True


def reset_opentelemetry_state() -> None:
    """Reset module state (tests only)."""
    global _INITIALIZED, _LOG_HANDLER_ATTACHED, _INSTRUMENTED
    try:
        from adapters.observability.telemetry_bridge import stop_metrics_export
    except ImportError:
        from .telemetry_bridge import stop_metrics_export

    stop_metrics_export()
    _INITIALIZED = False
    _LOG_HANDLER_ATTACHED = False
    _INSTRUMENTED = False
