"""Tests for OpenTelemetry init helpers."""

from __future__ import annotations

from adapters.observability import otel as otel_module


def test_normalize_traces_endpoint_appends_path():
    assert (
        otel_module._normalize_traces_endpoint("http://127.0.0.1:4318")
        == "http://127.0.0.1:4318/v1/traces"
    )


def test_normalize_traces_endpoint_keeps_existing_path():
    endpoint = "http://127.0.0.1:4318/v1/traces"
    assert otel_module._normalize_traces_endpoint(endpoint) == endpoint


def test_collector_reachable_false_for_invalid_scheme():
    assert otel_module._collector_reachable("ftp://127.0.0.1:4318") is False


def test_init_opentelemetry_skips_when_endpoint_unset(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert otel_module.init_opentelemetry() is False
