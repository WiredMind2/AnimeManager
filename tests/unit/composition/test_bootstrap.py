"""Tests for composition bootstrap helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from composition.bootstrap import EmbeddedDeps, _BootstrapHost, bootstrap_embedded_deps


def test_bootstrap_embedded_deps_returns_wired_collaborators():
    with patch("composition.bootstrap.AnimeAPI") as api_cls:
        api_cls.return_value = object()
        deps = bootstrap_embedded_deps(api=api_cls.return_value)

    assert isinstance(deps, EmbeddedDeps)
    assert deps.config is not None
    assert deps.db_manager is not None
    assert deps.scanner is not None
    assert deps.file_manager is not None
    assert deps.torrent_manager is not None
    assert deps.api is api_cls.return_value


def test_bootstrap_host_set_settings_updates_config():
    config = MagicMock(update_settings=MagicMock(return_value={"ok": True}))
    logger = MagicMock()
    constants = SimpleNamespace(settings={"database_managers": {"last_db_used": "SQLite"}})
    with patch("composition.bootstrap.Getters.getDatabase", return_value=object()):
        host = _BootstrapHost(
            constants=constants,
            config=config,
            logger=logger,
            api=object(),
        )
    result = host.setSettings({"foo": "bar"})
    config.update_settings.assert_called_once_with({"foo": "bar"})
    assert result == {"ok": True}
    assert host.settings == {"ok": True}


def test_bootstrap_host_log_delegates_to_logger():
    logger = MagicMock()
    with patch("composition.bootstrap.Getters.getDatabase", return_value=object()):
        host = _BootstrapHost(
            constants=SimpleNamespace(settings={"database_managers": {"last_db_used": "SQLite"}}),
            config=MagicMock(),
            logger=logger,
            api=object(),
        )
    host.log("hello", level="info")
    logger.log.assert_called_once_with("hello", level="info")


def test_bootstrap_host_log_swallows_logger_errors():
    logger = MagicMock(log=MagicMock(side_effect=RuntimeError("nope")))
    with patch("composition.bootstrap.Getters.getDatabase", return_value=object()):
        host = _BootstrapHost(
            constants=SimpleNamespace(settings={"database_managers": {"last_db_used": "SQLite"}}),
            config=MagicMock(),
            logger=logger,
            api=object(),
        )
    assert host.log("x") is None
