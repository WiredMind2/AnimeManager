"""Unit tests for OpenTelemetry bridge and client telemetry enrichment."""

from __future__ import annotations

import os

import pytest

from adapters.observability.otel import (
    init_opentelemetry,
    instrument_fastapi_app,
    reset_opentelemetry_state,
)
from adapters.observability.telemetry_bridge import snapshot_to_metrics_data, stop_metrics_export
from clients.http.telemetry_events import _structured_extra, ingest_client_events
from shared.telemetry import get_telemetry, reset_telemetry


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", raising=False)
    reset_telemetry()
    reset_opentelemetry_state()
    yield
    stop_metrics_export()
    reset_opentelemetry_state()


def test_init_opentelemetry_skipped_without_endpoint() -> None:
    assert init_opentelemetry() is False


def test_instrument_fastapi_app_skipped_without_endpoint() -> None:
    from fastapi import FastAPI

    assert instrument_fastapi_app(FastAPI()) is False


def test_instrument_fastapi_app_calls_instrumentor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import FastAPI

    calls: list[object] = []

    class _FakeInstrumentor:
        @staticmethod
        def instrument_app(app: object) -> None:
            calls.append(app)

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    monkeypatch.setattr(
        "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor",
        _FakeInstrumentor,
    )

    app = FastAPI()
    assert instrument_fastapi_app(app) is True
    assert calls == [app]
    assert instrument_fastapi_app(app) is True
    assert len(calls) == 1


def test_snapshot_to_metrics_data_maps_collector_fields() -> None:
    from opentelemetry.sdk.resources import Resource

    telemetry = get_telemetry()
    telemetry.increment("http.requests", 3)
    telemetry.set_gauge("playback.active_sessions", 2.0)
    telemetry.record_ms("http.request_ms", 12.5)
    telemetry.record_ms("http.request_ms", 50.0)

    resource = Resource.create({"service.name": "test"})
    metrics_data = snapshot_to_metrics_data(resource)
    assert metrics_data is not None

    names: set[str] = set()
    for resource_metrics in metrics_data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                names.add(metric.name)

    assert "http.requests" in names
    assert "playback.active_sessions" in names
    assert "http.request_ms.p50" in names
    assert "http.request_ms.count" in names


def test_snapshot_to_metrics_data_empty_returns_none() -> None:
    from opentelemetry.sdk.resources import Resource

    resource = Resource.create({"service.name": "test"})
    assert snapshot_to_metrics_data(resource) is None


def test_init_opentelemetry_wires_all_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    metrics_calls: list[tuple[object, ...]] = []
    log_calls: list[tuple[object, ...]] = []

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "test-http")
    monkeypatch.setattr(
        "adapters.observability.telemetry_bridge.start_metrics_export",
        lambda *args, **kwargs: metrics_calls.append(args) or True,
    )
    monkeypatch.setattr(
        "adapters.observability.otel._attach_log_handler",
        lambda *args, **kwargs: log_calls.append(args) or True,
    )

    assert init_opentelemetry() is True
    assert init_opentelemetry() is True
    assert len(metrics_calls) == 1
    assert len(metrics_calls[0]) == 1
    assert len(log_calls) == 1
    assert len(log_calls[0]) == 1


def test_otlp_http_exporters_expand_base_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    exporters = [
        OTLPSpanExporter(),
        OTLPMetricExporter(),
        OTLPLogExporter(),
    ]
    try:
        assert [exporter._endpoint for exporter in exporters] == [  # noqa: SLF001
            "http://127.0.0.1:4318/v1/traces",
            "http://127.0.0.1:4318/v1/metrics",
            "http://127.0.0.1:4318/v1/logs",
        ]
    finally:
        for exporter in exporters:
            exporter.shutdown()


def test_structured_extra_for_client_error() -> None:
    extra = _structured_extra(
        "client.error",
        "error",
        {
            "path": "/library",
            "error_name": "ApiError",
            "error_message": "Request failed",
            "request_id": "abc-123",
        },
        "2026-01-01T00:00:00Z",
    )
    assert extra["telemetry.event"] == "client.error"
    assert extra["telemetry.path"] == "/library"
    assert extra["telemetry.error_name"] == "ApiError"
    assert extra["telemetry.request_id"] == "abc-123"


def test_structured_extra_for_web_vital() -> None:
    extra = _structured_extra(
        "web_vital.LCP",
        "info",
        {"value": 1234.5, "path": "/anime/1"},
        None,
    )
    assert extra["telemetry.web_vital"] == "LCP"
    assert extra["telemetry.web_vital_value"] == 1234.5


def test_ingest_client_events_passes_structured_extra(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    captured: list[dict] = []

    def _fake_info(msg: str, *args, extra: dict | None = None, **kwargs) -> None:
        if extra:
            captured.append(extra)

    monkeypatch.setattr(
        "clients.http.telemetry_events._CLIENT_LOG.info",
        _fake_info,
    )
    count = ingest_client_events(
        [
            {
                "event": "web_vital.LCP",
                "level": "info",
                "ts": "2026-01-01T00:00:00Z",
                "data": {"value": 99.0, "path": "/library"},
            }
        ]
    )
    assert count == 1
    assert captured[0]["telemetry.web_vital"] == "LCP"
    assert captured[0]["telemetry.web_vital_value"] == 99.0
