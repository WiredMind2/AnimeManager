"""Tests for log viewer routes and PWA assets in :mod:`clients.http.web`."""

from __future__ import annotations

import importlib
import json
import logging

import pytest
from fastapi.testclient import TestClient

from clients.http import log_buffer as lb

http_app = importlib.import_module("clients.http.app")


class _SettingsSDK:
    def get_settings(self):
        return {
            "logs": {
                "enabled_categories": list(lb.KNOWN_CATEGORIES),
            }
        }


@pytest.fixture
def log_client(monkeypatch):
    """Isolated log buffer + minimal SDK for /ui/logs* routes."""
    buf = lb.LogBuffer()
    monkeypatch.setattr(lb, "global_buffer", buf)
    monkeypatch.setattr(http_app, "get_sdk", lambda: _SettingsSDK())
    with TestClient(http_app.app, follow_redirects=False) as client:
        client.log_buffer = buf  # type: ignore[attr-defined]
        yield client


def _sample_record(message: str = "hello", *, category: str = "HTTP") -> dict:
    return {
        "levelno": logging.INFO,
        "level": "INFO",
        "logger": "tests.http",
        "message": message,
        "category": category,
    }


def test_logs_page_renders_snapshot(log_client):
    log_client.log_buffer.add(_sample_record("boot line"))
    resp = log_client.get("/ui/logs")
    assert resp.status_code == 200
    assert "boot line" in resp.text
    assert "Logs" in resp.text


def test_logs_page_category_chip_filter(log_client):
    log_client.log_buffer.add(_sample_record("http only", category="HTTP"))
    log_client.log_buffer.add(_sample_record("other only", category="OTHER"))
    resp = log_client.get("/ui/logs", params={"category": "HTTP"})
    assert resp.status_code == 200
    assert "http only" in resp.text
    assert "other only" not in resp.text


def test_logs_data_json_since_and_limit(log_client):
    log_client.log_buffer.add(_sample_record("first"))
    log_client.log_buffer.add(_sample_record("second"))
    snap = log_client.log_buffer.snapshot()
    first_id = snap[0]["id"]
    resp = log_client.get(
        "/ui/logs/data",
        params={"since": first_id, "limit": 10, "level": "INFO"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["records"]) == 1
    assert payload["records"][0]["message"] == "second"
    assert payload["last_id"] == snap[-1]["id"]
    assert payload["buffered"] >= 2


def test_logs_data_text_and_logger_filters(log_client):
    log_client.log_buffer.add(
        {
            **_sample_record("needle in haystack"),
            "logger": "application.services.download_manager",
            "module": "worker",
        }
    )
    log_client.log_buffer.add(_sample_record("noise"))
    resp = log_client.get(
        "/ui/logs/data",
        params={"q": "needle", "logger": "download"},
    )
    assert resp.status_code == 200
    records = resp.json()["records"]
    assert len(records) == 1
    assert records[0]["message"] == "needle in haystack"


def test_logs_clear_redirects(log_client):
    log_client.log_buffer.add(_sample_record())
    resp = log_client.post("/ui/logs/clear")
    assert resp.status_code in {302, 303, 307}
    assert resp.headers["location"].endswith("/ui/logs")
    assert log_client.log_buffer.snapshot() == []


def test_logs_clear_htmx_returns_empty_table(log_client):
    log_client.log_buffer.add(_sample_record("gone"))
    resp = log_client.post(
        "/ui/logs/clear",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "gone" not in resp.text
    assert "cleared" in resp.text.lower()


def test_manifest_webmanifest(log_client):
    resp = log_client.get("/ui/manifest.webmanifest")
    assert resp.status_code == 200
    assert "application/manifest+json" in resp.headers.get("content-type", "")
    data = resp.json()
    assert data["name"] == "AnimeManager"
    assert data["start_url"] == "/ui/library"
    assert data["scope"] == "/ui/"


def test_service_worker_served(log_client):
    resp = log_client.get("/ui/sw.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("content-type", "")
    assert resp.headers.get("Service-Worker-Allowed") == "/ui/"
    assert "self" in resp.text or "addEventListener" in resp.text


def test_offline_fallback_page(log_client):
    resp = log_client.get("/ui/offline")
    assert resp.status_code == 200
    assert "offline" in resp.text.lower()
