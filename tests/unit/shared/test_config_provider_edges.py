"""Edge case tests for ``shared.config.config_provider.ConfigProvider``.

These tests exercise the narrow accessor surface without hitting real
``Constants``. They use a small duck-typed stand-in to drive the
attribute-forwarding code paths.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from shared.config.config_provider import ConfigProvider, get_default_config_provider


def _make_fake_constants(tmp_path, *, settings=None, settings_path=None):
    """Build a ducked Constants object compatible with ConfigProvider."""
    if settings_path is None:
        settings_path = str(tmp_path / "settings.json")
    if settings is not None:
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f)

    fake = SimpleNamespace(
        getAppdata=lambda: str(tmp_path),
        dbPath=str(tmp_path / "anime.db"),
        settingsPath=settings_path,
        logsPath=str(tmp_path / "logs"),
        cache=str(tmp_path / "cache"),
        iconPath=str(tmp_path / "icons"),
        settings=settings if settings is not None else {},
    )
    return fake


class TestConfigProviderAccessors:
    def test_returns_empty_strings_when_constants_lacks_paths(self, tmp_path):
        provider = ConfigProvider(constants=SimpleNamespace())
        assert provider.appdata_path == ""
        assert provider.db_path == ""
        assert provider.settings_path == ""
        assert provider.logs_path == ""
        assert provider.cache_path == ""
        assert provider.icon_path == ""

    def test_returns_empty_dict_when_settings_missing(self):
        provider = ConfigProvider(constants=SimpleNamespace())
        assert provider.settings == {}

    def test_returns_empty_dict_when_settings_is_none(self):
        fake = SimpleNamespace(settings=None)
        provider = ConfigProvider(constants=fake)
        assert provider.settings == {}

    def test_returns_values_from_constants(self, tmp_path):
        fake = _make_fake_constants(tmp_path, settings={"x": 1})
        provider = ConfigProvider(constants=fake)
        assert provider.appdata_path == str(tmp_path)
        assert provider.db_path == str(tmp_path / "anime.db")
        assert provider.settings_path
        assert provider.settings == {"x": 1}


class TestEnsureAppdata:
    def test_creates_directory_when_missing(self, tmp_path):
        target = tmp_path / "appdata"
        fake = SimpleNamespace(
            getAppdata=lambda: str(target),
            dbPath="",
            settingsPath="",
            logsPath="",
            cache="",
            iconPath="",
            settings={},
        )
        provider = ConfigProvider(constants=fake)
        assert not target.exists()
        out = provider.ensure_appdata()
        assert out == str(target)
        assert target.exists()

    def test_returns_existing_directory_unchanged(self, tmp_path):
        target = tmp_path / "exists"
        target.mkdir()
        fake = SimpleNamespace(
            getAppdata=lambda: str(target),
            dbPath="",
            settingsPath="",
            logsPath="",
            cache="",
            iconPath="",
            settings={},
        )
        provider = ConfigProvider(constants=fake)
        out = provider.ensure_appdata()
        assert out == str(target)

    def test_handles_empty_path(self):
        fake = SimpleNamespace(
            getAppdata=lambda: "",
            dbPath="",
            settingsPath="",
            logsPath="",
            cache="",
            iconPath="",
            settings={},
        )
        provider = ConfigProvider(constants=fake)
        out = provider.ensure_appdata()
        assert out == ""


class TestUpdateSettings:
    def test_raises_when_settings_path_missing(self):
        fake = SimpleNamespace(
            getAppdata=lambda: "",
            dbPath="",
            settingsPath="",
            logsPath="",
            cache="",
            iconPath="",
            settings={},
        )
        provider = ConfigProvider(constants=fake)
        with pytest.raises(RuntimeError):
            provider.update_settings({"a": 1})

    def test_merges_nested_section(self, tmp_path):
        fake = _make_fake_constants(
            tmp_path,
            settings={"anime": {"hideRated": True}, "other": "x"},
        )
        provider = ConfigProvider(constants=fake)
        out = provider.update_settings({"anime": {"newKey": 42}})
        assert out["anime"]["hideRated"] is True
        assert out["anime"]["newKey"] == 42
        assert out["other"] == "x"

    def test_replaces_scalar_section(self, tmp_path):
        fake = _make_fake_constants(
            tmp_path,
            settings={"flag": False},
        )
        provider = ConfigProvider(constants=fake)
        out = provider.update_settings({"flag": True})
        assert out["flag"] is True

    def test_persists_to_disk(self, tmp_path):
        fake = _make_fake_constants(tmp_path, settings={"x": 1})
        provider = ConfigProvider(constants=fake)
        provider.update_settings({"y": 2})

        # File must reflect the merge
        with open(fake.settingsPath, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["x"] == 1
        assert data["y"] == 2

    def test_unicode_persists_correctly(self, tmp_path):
        fake = _make_fake_constants(tmp_path, settings={})
        provider = ConfigProvider(constants=fake)
        provider.update_settings({"name": "ナルト"})
        with open(fake.settingsPath, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["name"] == "ナルト"

    def test_empty_update_writes_unchanged_data(self, tmp_path):
        fake = _make_fake_constants(tmp_path, settings={"a": 1})
        provider = ConfigProvider(constants=fake)
        provider.update_settings({})
        with open(fake.settingsPath, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data == {"a": 1}

    def test_writes_through_mutates_constants_settings(self, tmp_path):
        fake = _make_fake_constants(tmp_path, settings={"a": 1})
        provider = ConfigProvider(constants=fake)
        result = provider.update_settings({"a": 99})
        # The fake's settings attribute should now have the new data.
        assert fake.settings == result


class TestDefaultProviderSingleton:
    def test_returns_same_instance_when_constants_present(self, tmp_path, monkeypatch):
        # We can't easily build a real Constants without side-effects, so
        # patch the module-level cache directly.
        import shared.config.config_provider as cp_module

        fake = SimpleNamespace(
            getAppdata=lambda: str(tmp_path),
            dbPath="",
            settingsPath="",
            logsPath="",
            cache="",
            iconPath="",
            settings={},
        )
        monkeypatch.setattr(cp_module, "_default_provider", ConfigProvider(constants=fake))

        a = get_default_config_provider()
        b = get_default_config_provider()
        assert a is b
