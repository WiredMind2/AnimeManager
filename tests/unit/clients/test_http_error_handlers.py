"""Tests for unified HTTP error mapping and handlers."""

from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from domain.errors import (
    InfrastructureError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from clients.http.errors import map_error_to_http, map_error_to_status, register_exception_handlers


class TestMapErrorToStatus:
    def test_validation_error(self):
        assert map_error_to_status(ValidationError("bad")) == (400, "bad")

    def test_unauthorized_error(self):
        assert map_error_to_status(UnauthorizedError("nope")) == (401, "nope")

    def test_not_found(self):
        assert map_error_to_status(NotFoundError("missing")) == (404, "missing")

    def test_infrastructure_error(self):
        assert map_error_to_status(InfrastructureError("db down")) == (502, "db down")

    def test_unexpected(self):
        assert map_error_to_status(RuntimeError("boom")) == (500, "boom")


class TestExceptionHandlers:
    @pytest.fixture
    def client(self):
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/unauthorized")
        def unauthorized():
            raise UnauthorizedError("nope")

        @app.get("/infra")
        def infra():
            raise InfrastructureError("db down")

        return TestClient(app, raise_server_exceptions=False)

    def test_unauthorized_maps_to_401(self, client):
        resp = client.get("/unauthorized")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "nope"

    def test_infrastructure_maps_to_502(self, client):
        resp = client.get("/infra")
        assert resp.status_code == 502
        assert resp.json()["detail"] == "db down"


def test_map_error_to_http_wrapper():
    exc = map_error_to_http(NotFoundError("missing"))
    assert exc.status_code == 404
    assert exc.detail == "missing"
