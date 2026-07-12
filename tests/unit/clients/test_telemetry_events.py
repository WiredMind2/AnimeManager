"""Tests for client telemetry event ingestion."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from clients.http.telemetry_events import ingest_client_events
from shared.telemetry import get_telemetry, reset_telemetry

http_app_module = importlib.import_module("clients.http.app")


@pytest.fixture(autouse=True)
def _reset_metrics():
    reset_telemetry()
    yield
    reset_telemetry()


def test_ingest_client_events_updates_telemetry():
    accepted = ingest_client_events(
        [
            {"ts": "2026-01-01T00:00:00Z", "level": "info", "event": "page.view", "data": {"path": "/library"}},
            {"ts": "2026-01-01T00:00:01Z", "level": "error", "event": "client.error", "data": {"message": "boom"}},
        ]
    )
    assert accepted == 2
    snap = get_telemetry().snapshot()
    assert snap["counters"]["client.events"] == 2.0
    assert snap["counters"]["client.errors"] == 1.0


def test_client_telemetry_endpoint(client=None):
    client = TestClient(http_app_module.app)
    resp = client.post(
        "/ui/telemetry/events",
        json={"events": [{"ts": "2026-01-01T00:00:00Z", "level": "warn", "event": "api.slow", "data": {}}]},
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1
