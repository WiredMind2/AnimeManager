"""Optional OpenTelemetry integration for the HTTP client adapter."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

_LOG = logging.getLogger("animemanager.observability")


def init_opentelemetry(app: FastAPI | None = None) -> bool:
    """Initialize OpenTelemetry when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set."""
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        _LOG.warning(
            "OTEL_EXPORTER_OTLP_ENDPOINT is set but opentelemetry packages are not installed"
        )
        return False

    service_name = os.environ.get("OTEL_SERVICE_NAME", "animemanager-http")
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
    )
    trace.set_tracer_provider(provider)
    if app is not None:
        FastAPIInstrumentor.instrument_app(app)
    _LOG.info("OpenTelemetry initialized service=%s endpoint=%s", service_name, endpoint)
    return True
