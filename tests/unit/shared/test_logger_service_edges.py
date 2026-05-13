"""Edge case tests for ``shared.telemetry.logger_service.LoggerService``."""

from __future__ import annotations

import pytest

from shared.telemetry.logger_service import LoggerService, get_default_logger_service


class _RecordingLogger:
    def __init__(self):
        self.calls = []

    def log(self, category, *args, **kwargs):
        self.calls.append((category, args, kwargs))


class _BrokenLogger:
    def log(self, *args, **kwargs):
        raise RuntimeError("boom")


class _LoggerMissingLog:
    pass


# ---------------------------------------------------------------------------
# LoggerService.log
# ---------------------------------------------------------------------------


class TestLoggerService:
    def test_forwards_to_legacy_logger(self):
        rec = _RecordingLogger()
        svc = LoggerService(legacy_logger=rec)
        svc.log("NETWORK", "a", "b", key="val")
        assert rec.calls == [("NETWORK", ("a", "b"), {"key": "val"})]

    def test_log_with_none_logger_is_noop(self):
        svc = LoggerService(legacy_logger=None)
        # Should not raise
        svc.log("anything", 1, 2)

    def test_log_with_logger_missing_log_attribute(self):
        # The collaborator could be the wrong type; the service ignores it.
        svc = LoggerService(legacy_logger=_LoggerMissingLog())
        svc.log("anything")  # must not raise

    def test_log_swallows_exceptions_from_legacy_logger(self):
        svc = LoggerService(legacy_logger=_BrokenLogger())
        # Logging must NEVER raise upwards
        svc.log("anything")

    def test_log_passes_kwargs(self):
        rec = _RecordingLogger()
        svc = LoggerService(legacy_logger=rec)
        svc.log("X", foo="bar")
        assert rec.calls == [("X", (), {"foo": "bar"})]

    def test_default_logger_service_returns_logger_service_instance(self):
        svc = get_default_logger_service()
        assert isinstance(svc, LoggerService)

    def test_default_logger_service_is_singleton(self):
        a = get_default_logger_service()
        b = get_default_logger_service()
        assert a is b


# ---------------------------------------------------------------------------
# from_defaults
# ---------------------------------------------------------------------------


class TestFromDefaults:
    def test_from_defaults_yields_logger_service(self):
        svc = LoggerService.from_defaults()
        # Either it found the legacy logger or fell back to None — both are
        # valid LoggerService instances.
        assert isinstance(svc, LoggerService)

    def test_from_defaults_log_does_not_raise(self):
        svc = LoggerService.from_defaults()
        # Should never raise even though we don't know which path was taken.
        svc.log("test_category", "msg")
