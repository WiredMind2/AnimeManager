"""Optional OpenTelemetry integration for the HTTP client adapter."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

if TYPE_CHECKING:
    from fastapi import FastAPI

_LOG = logging.getLogger("animemanager.observability")


def _normalize_traces_endpoint(endpoint: str) -> str:
    """Return an OTLP HTTP traces URL for ``endpoint``."""
    trimmed = endpoint.rstrip("/")
    if trimmed.endswith("/v1/traces"):
        return trimmed
    return urljoin(f"{trimmed}/", "v1/traces")


def _collector_reachable(endpoint: str, timeout_sec: float = 1.5) -> bool:
    """Best-effort probe so we skip OTEL when no collector is listening."""
    try:
        import urllib.error
        import urllib.request

        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"}:
            return False
        base = f"{parsed.scheme}://{parsed.netloc}"
        for path in ("/", "/v1/traces"):
            probe = urllib.request.Request(
                urljoin(f"{base}/", path.lstrip("/")),
                method="GET",
            )
            try:
                with urllib.request.urlopen(probe, timeout=timeout_sec) as resp:
                    # Any HTTP response means something is listening on the port.
                    if resp.status < 500:
                        return True
            except urllib.error.HTTPError as exc:
                if exc.code < 500:
                    return True
            except OSError:
                continue
        return False
    except Exception:  # noqa: BLE001
        return False


def init_opentelemetry(app: FastAPI | None = None) -> bool:
    """Initialize OpenTelemetry when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set."""
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return False
    if not _collector_reachable(endpoint):
        _LOG.info(
            "Skipping OpenTelemetry init: collector unreachable at %s "
            "(unset OTEL_EXPORTER_OTLP_ENDPOINT when the stack is not running)",
            endpoint,
        )
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

    traces_endpoint = _normalize_traces_endpoint(endpoint)
    service_name = os.environ.get("OTEL_SERVICE_NAME", "animemanager-http")
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=traces_endpoint))
    )
    trace.set_tracer_provider(provider)
    if app is not None:
        FastAPIInstrumentor.instrument_app(app)
    _LOG.info(
        "OpenTelemetry initialized service=%s endpoint=%s",
        service_name,
        traces_endpoint,
    )
    return True
