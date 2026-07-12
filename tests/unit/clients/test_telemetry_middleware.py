"""Tests for HTTP telemetry middleware."""

from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from clients.http.request_context import REQUEST_ID_HEADER
from clients.http.telemetry_middleware import install_telemetry_middleware
from shared.telemetry import get_telemetry, reset_telemetry


@pytest.fixture(autouse=True)
def _reset_metrics():
    reset_telemetry()
    yield
    reset_telemetry()


def test_middleware_propagates_request_id_and_records_latency():
    app = FastAPI()
    install_telemetry_middleware(app)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/ping", headers={REQUEST_ID_HEADER: "test-req-1"})
    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "test-req-1"

    snap = get_telemetry().snapshot()
    assert snap["counters"]["http.requests"] == 1.0
    assert snap["counters"]["http.responses.200"] == 1.0
    assert snap["timers"]["http.request_ms"]["count"] == 1.0


def test_middleware_generates_request_id_when_missing():
    app = FastAPI()
    install_telemetry_middleware(app)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.headers.get(REQUEST_ID_HEADER)
