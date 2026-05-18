"""Edge case tests for ``shared.telemetry.logger`` (filesystem + singleton behavior)."""

from __future__ import annotations

import builtins
import os
from unittest.mock import patch

import pytest

from shared.telemetry.logger import Logger, log


@pytest.fixture(autouse=True)
def _reset_logger_globals(monkeypatch):
    """Isolate logger singleton state between tests."""
    monkeypatch.delenv("ANIMEMANAGER_LOGFILE", raising=False)
    for attr in ("anime_manager_logger", "anime_manager_log_file"):
        monkeypatch.delattr(builtins, attr, raising=False)
    yield
    monkeypatch.delenv("ANIMEMANAGER_LOGFILE", raising=False)
    for attr in ("anime_manager_logger", "anime_manager_log_file"):
        monkeypatch.delattr(builtins, attr, raising=False)


def _patch_appdata(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "shared.telemetry.logger.Constants.getAppdata",
        staticmethod(lambda: str(tmp_path)),
    )
    return logs


class TestLoggerInit:
    def test_reuses_existing_builtin_singleton(self, tmp_path, monkeypatch):
        _patch_appdata(tmp_path, monkeypatch)
        existing = Logger(logs="ALL")
        assert getattr(builtins, "anime_manager_logger") is existing

        second = Logger(logs="NONE")
        # Early-return path must not register a second global logger.
        assert getattr(builtins, "anime_manager_logger") is existing
        assert not hasattr(second, "logFile")

    def test_init_logs_uses_env_logfile(self, tmp_path, monkeypatch):
        logs = _patch_appdata(tmp_path, monkeypatch)
        log_path = logs / "log_env.txt"
        log_path.write_text("seed\n", encoding="utf-8")
        monkeypatch.setenv("ANIMEMANAGER_LOGFILE", str(log_path))

        logger = Logger(logs="ALL")
        assert logger.logFile == str(log_path)

    def test_init_logs_reuses_recent_file_in_directory(self, tmp_path, monkeypatch):
        logs = _patch_appdata(tmp_path, monkeypatch)
        recent = logs / "log_recent.txt"
        recent.write_text("x\n", encoding="utf-8")

        logger = Logger(logs="ALL")
        assert os.path.normpath(logger.logFile) == os.path.normpath(str(recent))

    def test_remote_flag_sets_none_mode(self, tmp_path, monkeypatch):
        _patch_appdata(tmp_path, monkeypatch)

        class RemoteLogger(Logger):
            remote = True

        logger = RemoteLogger(logs="ALL")
        assert logger.log_mode == "NONE"

    def test_custom_logs_list_sets_default_mode(self, tmp_path, monkeypatch):
        _patch_appdata(tmp_path, monkeypatch)
        logger = Logger(logs=["CUSTOM"])
        assert logger.log_mode == "DEFAULT"


class TestLoggerLog:
    def test_writes_categorized_message_to_file(self, tmp_path, monkeypatch, capsys):
        _patch_appdata(tmp_path, monkeypatch)
        logger = Logger(logs="ALL")
        logger.log("NETWORK", "hello", "world")

        content = open(logger.logFile, encoding="utf-8").read()
        assert "NETWORK" in content
        assert "hello" in content
        captured = capsys.readouterr()
        assert "NETWORK" in captured.out

    def test_none_mode_suppresses_console_but_writes_file(
        self, tmp_path, monkeypatch, capsys
    ):
        _patch_appdata(tmp_path, monkeypatch)
        logger = Logger(logs="NONE")
        logger.log("NETWORK", "silent console")

        captured = capsys.readouterr()
        assert captured.out == ""
        content = open(logger.logFile, encoding="utf-8").read()
        assert "silent console" in content

    def test_unknown_category_suppresses_console(self, tmp_path, monkeypatch, capsys):
        _patch_appdata(tmp_path, monkeypatch)
        logger = Logger(logs="ALL")
        logger.log("NOT_A_REAL_CATEGORY", "hidden from console")

        captured = capsys.readouterr()
        assert captured.out == ""
        content = open(logger.logFile, encoding="utf-8").read()
        assert "hidden from console" in content

    def test_plain_message_uses_generic_prefix(self, tmp_path, monkeypatch, capsys):
        _patch_appdata(tmp_path, monkeypatch)
        logger = Logger(logs="ALL")
        logger.log("plain message")

        captured = capsys.readouterr()
        assert "LOG" in captured.out

    def test_logging_callback_invoked(self, tmp_path, monkeypatch):
        _patch_appdata(tmp_path, monkeypatch)
        logger = Logger(logs="ALL")
        seen = []
        logger.loggingCb = seen.append
        logger.log("SETTINGS", "cb test")
        assert len(seen) == 1
        assert "SETTINGS" in seen[0]

    def test_log_mode_override_per_call(self, tmp_path, monkeypatch, capsys):
        _patch_appdata(tmp_path, monkeypatch)
        logger = Logger(logs="NONE")
        logger.log("NETWORK", "forced", log_mode="ALL")
        captured = capsys.readouterr()
        assert "NETWORK" in captured.out


class TestLoggerLogRotation:
    def test_removes_oldest_logs_when_over_size_limit(self, tmp_path, monkeypatch):
        import time as time_mod

        logs = _patch_appdata(tmp_path, monkeypatch)
        stale = time_mod.time() - 120
        old = logs / "log_old.txt"
        old.write_bytes(b"x" * 30_000)
        new = logs / "log_new.txt"
        new.write_bytes(b"y" * 30_000)
        os.utime(old, (stale, stale))
        os.utime(new, (stale, stale))

        logger = Logger(logs="ALL")
        logger.maxLogsSize = 40_000
        # Avoid initLogs short-circuit via env/builtins from the constructor.
        monkeypatch.delenv("ANIMEMANAGER_LOGFILE", raising=False)
        monkeypatch.delattr(builtins, "anime_manager_log_file", raising=False)
        logger.initLogs()

        remaining = [f for f in os.listdir(logs) if f.startswith("log_")]
        total_size = sum(os.path.getsize(logs / f) for f in remaining)
        assert len(remaining) < 2 or total_size < logger.maxLogsSize


class TestModuleLogFunction:
    def test_log_function_creates_singleton(self, tmp_path, monkeypatch, capsys):
        _patch_appdata(tmp_path, monkeypatch)
        assert getattr(builtins, "anime_manager_logger", None) is None

        log("MAIN_STATE", "from helper")
        assert getattr(builtins, "anime_manager_logger", None) is not None

        captured = capsys.readouterr()
        assert "MAIN_STATE" in captured.out or "from helper" in captured.out

    def test_log_function_reuses_existing_singleton(self, tmp_path, monkeypatch):
        _patch_appdata(tmp_path, monkeypatch)
        first = Logger(logs="ALL")
        builtins.anime_manager_logger = first

        log("SETTINGS", "again")
        assert getattr(builtins, "anime_manager_logger") is first
