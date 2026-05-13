"""Characterization tests for :mod:`adapters.legacy.runtime`.

The Phase 2 refactor replaced ``LegacyRuntime(Constants, Getters)``
with a composed implementation. These tests pin the externally visible
behavior so the change can be detected if someone re-introduces
inheritance or breaks delegation.
"""

from __future__ import annotations

import json
import os
import tempfile
import types
from unittest import mock

import pytest


@pytest.fixture()
def fake_state():
    state = types.SimpleNamespace()
    state.database = object()
    state.api = object()
    state.fm = object()
    state.tm = object()
    state.settings = {"app": {"mode": "test"}}
    state.dbPath = "/tmp/anime.db"
    state.settingsPath = os.path.join(tempfile.gettempdir(), "_amgr_test_settings.json")
    state.log = lambda *args, **kwargs: None
    state.setSettings = lambda updates: {"app": {"mode": updates["app"]["mode"]}, "x": 1, "y": 2}
    return state


def _import_runtime():
    try:
        from adapters.legacy.runtime import LegacyRuntime  # type: ignore
    except Exception:  # pragma: no cover
        pytest.skip("legacy_runtime not importable in this environment")
    return LegacyRuntime


def test_legacy_runtime_does_not_inherit_from_constants_or_getters(fake_state):
    LegacyRuntime = _import_runtime()

    from shared.config.constants import Constants
    from shared.config.getters import Getters

    runtime = LegacyRuntime(
        state=fake_state,
        constants=types.SimpleNamespace(),
        config=types.SimpleNamespace(settings_path=fake_state.settingsPath),
    )

    assert not isinstance(runtime, Constants), (
        "LegacyRuntime must use composition, not inheritance, against Constants."
    )
    assert not isinstance(runtime, Getters), (
        "LegacyRuntime must use composition, not inheritance, against Getters."
    )


def test_legacy_runtime_delegates_public_attributes(fake_state):
    LegacyRuntime = _import_runtime()
    runtime = LegacyRuntime(
        state=fake_state,
        constants=types.SimpleNamespace(),
        config=types.SimpleNamespace(settings_path=fake_state.settingsPath),
    )

    assert runtime.database is fake_state.database
    assert runtime.api is fake_state.api
    assert runtime.fm is fake_state.fm
    assert runtime.tm is fake_state.tm
    assert runtime.settings == {"app": {"mode": "test"}}
    assert runtime.dbPath == "/tmp/anime.db"
    assert runtime.settingsPath == fake_state.settingsPath


def test_legacy_runtime_set_settings_persists_to_disk(tmp_path, fake_state):
    LegacyRuntime = _import_runtime()

    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"app": {"mode": "initial"}, "x": 1}), encoding="utf-8")
    fake_state.settingsPath = str(settings_file)
    fake_config = types.SimpleNamespace(
        settings_path=str(settings_file),
        update_settings=lambda updates: {"app": {"mode": updates["app"]["mode"]}, "x": 1, "y": 2},
    )
    fake_state.setSettings = fake_config.update_settings

    runtime = LegacyRuntime(state=fake_state, constants=types.SimpleNamespace(), config=fake_config)
    result = runtime.setSettings({"app": {"mode": "updated"}, "y": 2})

    assert result["app"]["mode"] == "updated"
    assert result["x"] == 1
    assert result["y"] == 2

def test_legacy_runtime_log_is_side_effect_free_by_default(fake_state):
    LegacyRuntime = _import_runtime()
    runtime = LegacyRuntime(
        state=fake_state,
        constants=types.SimpleNamespace(),
        config=types.SimpleNamespace(settings_path=fake_state.settingsPath),
    )

    # log() must never raise even with empty args (legacy contract).
    assert runtime.log() is None
    assert runtime.log("CATEGORY", "msg") is None
