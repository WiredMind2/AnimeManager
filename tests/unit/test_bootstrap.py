"""Unit tests for :mod:`bootstrap` dispatch (no Tk GUI launch)."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import bootstrap


def test_list_modes_exposes_api_and_gui():
    modes = bootstrap.list_modes()
    assert set(modes) == {"api", "gui"}
    assert callable(modes["api"])
    assert callable(modes["gui"])


def test_main_unknown_mode_returns_error_code(capsys):
    assert bootstrap.main(mode="nope") == 2
    err = capsys.readouterr().err
    assert "unknown mode" in err.lower()


def test_main_gui_subprocess_skips_run():
    proc = SimpleNamespace(name="SpawnProcess-1")
    with patch.object(bootstrap.multiprocessing, "current_process", return_value=proc):
        assert bootstrap.main(mode="gui") == 0


def test_kickoff_startup_jobs_import_failure_is_safe():
    import types

    empty = types.ModuleType("clients.sdk")
    with patch.dict(
        sys.modules,
        {"clients.sdk": empty, "AnimeManager.clients.sdk": types.ModuleType("x")},
    ):
        bootstrap._kickoff_startup_jobs()


def test_kickoff_startup_jobs_launches_when_sdk_available():
    thread = MagicMock()
    sdk_instance = MagicMock()
    sdk_instance.kickoff_startup_jobs.return_value = thread
    mock_sdk_class = MagicMock(return_value=sdk_instance)
    with patch("clients.sdk.ClientSDK", mock_sdk_class):
        bootstrap._kickoff_startup_jobs()
    mock_sdk_class.assert_called_once()
    sdk_instance.kickoff_startup_jobs.assert_called_once()


def test_kickoff_startup_jobs_warns_when_no_thread():
    sdk_instance = MagicMock()
    sdk_instance.kickoff_startup_jobs.return_value = None
    with patch("clients.sdk.ClientSDK", return_value=sdk_instance):
        bootstrap._kickoff_startup_jobs()


def test_run_api_without_uvicorn_returns_two():
    real_import = __import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "uvicorn":
            raise ImportError("uvicorn not installed")
        return real_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=_import):
        assert bootstrap._run_api() == 2


def test_run_api_import_failure_returns_two():
    fake_uvicorn = MagicMock()
    with patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
        with patch(
            "bootstrap._http_app_import_target",
            side_effect=ImportError("missing app"),
        ):
            assert bootstrap._run_api() == 2


def test_run_api_starts_uvicorn_and_kickoff():
    fake_uvicorn = MagicMock()
    with patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
        with patch(
            "bootstrap._http_app_import_target",
            return_value=(object(), "clients.http.app:app"),
        ):
            with patch("bootstrap._kickoff_startup_jobs") as kickoff:
                assert bootstrap._run_api(host="127.0.0.1", port=9000) == 0
    kickoff.assert_called_once()
    fake_uvicorn.run.assert_called_once_with(
        "clients.http.app:app",
        host="127.0.0.1",
        port=9000,
        timeout_graceful_shutdown=8,
    )


def test_http_app_import_target_prefers_packaged_path():
    sentinel = object()
    with patch.dict(
        sys.modules,
        {"AnimeManager.clients.http.app": SimpleNamespace(app=sentinel)},
    ):
        app, target = bootstrap._http_app_import_target()
    assert app is sentinel
    assert target == "AnimeManager.clients.http.app:app"
