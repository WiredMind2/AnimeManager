"""Tests for Sentry noise filters."""

from __future__ import annotations

from adapters.observability import sentry as sentry_module


def test_before_send_drops_otel_exporter_logs():
    event = {
        "logger": "opentelemetry.exporter.otlp.proto.http.metric_exporter",
        "logentry": {"message": "Failed to export metrics batch code: 404"},
    }
    assert sentry_module._before_send(event, {}) is None


def test_before_send_drops_startup_keyboard_interrupt():
    event = {
        "message": "Application startup failed. Exiting.",
        "exception": {
            "values": [{"type": "KeyboardInterrupt", "value": ""}],
        },
    }
    assert sentry_module._before_send(event, {}) is None


def test_before_send_keeps_real_errors():
    event = {
        "logger": "animemanager.http",
        "logentry": {"message": "download failed for anime 42"},
    }
    assert sentry_module._before_send(event, {}) == event


def test_before_send_log_drops_otel_sdk_internal():
    log = {
        "logger": "opentelemetry.sdk._shared_internal",
        "body": "Exception while exporting Log.",
    }
    assert sentry_module._before_send_log(log, {}) is None
