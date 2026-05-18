"""Unit tests for :mod:`clients.http.log_buffer`."""

from __future__ import annotations

import logging
import queue
import time

import pytest

from clients.http import log_buffer as lb


def test_derive_category_from_legacy_bracket():
    payload = {"message": "[ MAIN_STATE ] - pipeline started", "logger": "x"}
    assert lb.derive_category(payload) == "MAIN_STATE"


def test_derive_category_from_logger_prefix():
    payload = {
        "message": "fetch ok",
        "logger": "application.services.download_manager.worker",
        "levelno": logging.INFO,
    }
    assert lb.derive_category(payload) == "DOWNLOAD"


def test_derive_category_db_error_on_high_level():
    payload = {
        "message": "write failed",
        "logger": "adapters.persistence.db",
        "levelno": logging.ERROR,
    }
    assert lb.derive_category(payload) == "DB_ERROR"


def test_strip_legacy_bracket():
    clean, cat = lb.strip_legacy_bracket("[ NETWORK ] - timeout")
    assert cat == "NETWORK"
    assert clean == "timeout"
    assert lb.strip_legacy_bracket("plain text") == ("plain text", None)


def test_log_buffer_add_and_snapshot_filters():
    buf = lb.LogBuffer(max_records=10)
    buf.add(
        {
            "levelno": logging.INFO,
            "level": "INFO",
            "logger": "tests.unit",
            "message": "hello",
            "category": "HTTP",
        }
    )
    buf.add(
        {
            "levelno": logging.ERROR,
            "level": "ERROR",
            "logger": "tests.unit",
            "message": "boom",
            "category": "HTTP",
        }
    )
    errors = buf.snapshot(min_level=logging.ERROR)
    assert len(errors) == 1
    assert errors[0]["message"] == "boom"


def test_disabled_categories_drop_records():
    buf = lb.LogBuffer()
    buf.set_disabled_categories(["HTTP"])
    stored = buf.add(
        {
            "levelno": logging.INFO,
            "message": "hidden",
            "category": "HTTP",
        }
    )
    assert stored is None
    assert buf.snapshot() == []


def test_subscribe_receives_broadcast():
    buf = lb.LogBuffer()
    sub = buf.subscribe(maxsize=5)
    try:
        buf.add({"levelno": logging.INFO, "message": "live", "category": "OTHER"})
        item = sub.get(timeout=1.0)
        assert item["message"] == "live"
        assert "id" in item
    finally:
        buf.unsubscribe(sub)


def test_subscribe_drops_oldest_on_overflow():
    buf = lb.LogBuffer()
    sub = buf.subscribe(maxsize=1)
    try:
        buf.add({"levelno": logging.INFO, "message": "first", "category": "OTHER"})
        buf.add({"levelno": logging.INFO, "message": "second", "category": "OTHER"})
        latest = sub.get_nowait()
        assert latest["message"] in {"first", "second"}
    finally:
        buf.unsubscribe(sub)


def test_sync_from_settings_whitelist():
    buf = lb.LogBuffer()
    disabled = lb.sync_from_settings(
        {"logs": {"enabled_categories": ["HTTP", "SEARCH"]}},
        buffer=buf,
    )
    assert "MAIN_STATE" in disabled
    assert "HTTP" not in disabled


def test_buffering_handler_emit_strips_bracket_category():
    buf = lb.LogBuffer()
    handler = lb.BufferingHandler(buf, level=logging.DEBUG)
    record = logging.LogRecord(
        name="bootstrap",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="[ STARTUP ] - ready",
        args=(),
        exc_info=None,
    )
    handler.emit(record)
    snap = buf.snapshot()
    assert len(snap) == 1
    assert snap[0]["category"] == "STARTUP"
    assert snap[0]["message"] == "ready"


def test_stream_filtered_yields_heartbeat_on_timeout():
    buf = lb.LogBuffer()
    sub = queue.Queue()
    gen = lb.stream_filtered(sub, timeout=0.01)
    item = next(gen)
    assert item is None


def test_level_value_coercion():
    assert lb._level_value("INFO") == logging.INFO
    assert lb._level_value(30) == 30
    assert lb._level_value("", default=logging.WARNING) == logging.WARNING
    assert lb._level_value("not-a-level", default=logging.ERROR) == logging.ERROR


def test_clear_and_latest_id():
    buf = lb.LogBuffer()
    assert buf.latest_id() == 0
    stored = buf.add({"levelno": logging.INFO, "message": "one", "category": "OTHER"})
    assert stored is not None
    assert buf.latest_id() == stored["id"]
    assert buf.clear() == 1
    assert buf.snapshot() == []
    assert buf.latest_id() == 0


def test_known_categories_includes_observed_extras():
    buf = lb.LogBuffer()
    buf.add({"levelno": logging.INFO, "message": "x", "category": "CUSTOM_CAT"})
    cats = buf.known_categories()
    assert "CUSTOM_CAT" in cats
    assert cats.index("HTTP") < cats.index("CUSTOM_CAT")


def test_snapshot_filters_logger_text_and_categories():
    buf = lb.LogBuffer()
    buf.add(
        {
            "levelno": logging.INFO,
            "logger": "adapters.api.jikan",
            "module": "client",
            "message": "fetch ok",
            "category": "NETWORK",
        }
    )
    buf.add(
        {
            "levelno": logging.ERROR,
            "logger": "other",
            "message": "boom",
            "category": "OTHER",
            "exc_info": "Traceback\nline",
        }
    )
    assert len(buf.snapshot(logger_substr="jikan")) == 1
    assert len(buf.snapshot(text="Traceback")) == 1
    assert len(buf.snapshot(categories=["NETWORK"])) == 1
    assert len(buf.snapshot(min_level=logging.ERROR)) == 1
    assert len(buf.snapshot(limit=1)) == 1


def test_sync_from_settings_missing_key_clears_disabled():
    buf = lb.LogBuffer()
    buf.set_disabled_categories(["HTTP"])
    disabled = lb.sync_from_settings({"logs": {}}, buffer=buf)
    assert disabled == set()


def test_sync_from_settings_empty_enabled_silences_all():
    buf = lb.LogBuffer()
    disabled = lb.sync_from_settings(
        {"logs": {"enabled_categories": []}},
        buffer=buf,
    )
    assert "HTTP" in disabled
    assert buf.add({"levelno": logging.INFO, "message": "x", "category": "HTTP"}) is None


def test_stream_filtered_passes_matching_records():
    sub = queue.Queue()
    sub.put(
        {
            "levelno": logging.WARNING,
            "message": "warn",
            "category": "DOWNLOAD",
        }
    )
    gen = lb.stream_filtered(sub, min_level=logging.INFO, categories=["DOWNLOAD"], timeout=0.01)
    record = next(gen)
    assert record is not None
    assert record["message"] == "warn"


def test_buffering_handler_captures_exc_info():
    import sys

    buf = lb.LogBuffer()
    handler = lb.BufferingHandler(buf, level=logging.DEBUG)
    try:
        raise ValueError("kaboom")
    except ValueError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="tests",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="failed",
        args=(),
        exc_info=exc_info,
    )
    handler.emit(record)
    snap = buf.snapshot()
    assert snap[0]["exc_info"]
    assert "ValueError" in snap[0]["exc_info"]


def test_install_returns_same_handler_twice():
    root = logging.getLogger()
    before = [h for h in root.handlers if isinstance(h, lb.BufferingHandler)]
    first = lb.install(buffer=lb.LogBuffer(), capture_root=False)
    second = lb.install(buffer=lb.LogBuffer(), capture_root=False)
    assert first is second
    for extra in [h for h in root.handlers if isinstance(h, lb.BufferingHandler)]:
        if extra not in before:
            root.removeHandler(extra)


def test_iter_records_reads_snapshot():
    buf = lb.LogBuffer()
    buf.add({"levelno": logging.INFO, "message": "snap", "category": "OTHER"})
    rows = list(lb.iter_records(buf))
    assert rows[0]["message"] == "snap"


def test_derive_category_clients_http_prefix():
    payload = {"message": "req", "logger": "clients.http.web"}
    assert lb.derive_category(payload) == "HTTP"
