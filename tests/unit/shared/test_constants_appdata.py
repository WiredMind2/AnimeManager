"""Tests for Constants.getAppdata environment override."""

from __future__ import annotations

import json
import sys

import pytest

from shared.config.constants import Constants


def test_get_appdata_honors_env_override(monkeypatch, tmp_path):
    override = tmp_path / "appdata"
    monkeypatch.setenv("ANIMEMANAGER_APPDATA", str(override))
    assert Constants.getAppdata() == str(override)


def test_get_appdata_linux_default_without_override(monkeypatch):
    monkeypatch.delenv("ANIMEMANAGER_APPDATA", raising=False)
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    assert Constants.getAppdata() == "/srv/Anime Manager/"


def test_check_settings_normalizes_empty_sqlite_dbpath(monkeypatch, tmp_path):
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    settings_path = appdata / "settings.json"
    db_path = appdata / "animeData.db"
    db_path.write_text("", encoding="utf-8")
    settings_path.write_text(
        json.dumps(
            {
                "database_managers": {
                    "last_db_used": "SQLite",
                    "SQLite": {"dbPath": ""},
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("ANIMEMANAGER_APPDATA", str(appdata))
    monkeypatch.setattr(Constants, "log", lambda *args, **kwargs: None)

    constants = Constants()
    constants.settingsPath = str(settings_path)
    constants.dbPath = str(db_path)
    constants.checkSettings()

    assert constants.settings["database_managers"]["SQLite"]["dbPath"] == str(db_path)