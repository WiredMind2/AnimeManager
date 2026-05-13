"""Narrow config-access collaborator.

This module exists because the legacy code aggregated configuration
state by *inheriting* from :class:`constants.Constants` (see
``animeAPI.AnimeAPI``, ``animeAPI.APIUtils``,
``backend.adapters.legacy_runtime.LegacyRuntime``). The new
composition rule (ADR 0005) is that those classes should take a
config collaborator as a constructor argument instead.

:class:`ConfigProvider` exposes only the subset of ``Constants`` that
runtime code actually needs. It deliberately does **not** subclass
``Constants`` so that new collaborators inherit nothing implicitly.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping, MutableMapping, Optional


def _import_constants():
    try:
        from shared.config.constants import Constants  # type: ignore
    except ImportError:  # pragma: no cover
        from AnimeManager.shared.config.constants import Constants  # type: ignore
    return Constants


class ConfigProvider:
    """Composable configuration accessor.

    Wraps an already-constructed :class:`Constants` (or any duck-typed
    object exposing the same attributes). Calling code receives a
    narrow surface (paths, settings dict, save helper) and never sees
    the rest of the legacy ``Constants`` API.

    Parameters
    ----------
    constants:
        Optional pre-built ``Constants`` instance. If omitted a new one
        is constructed lazily.
    """

    def __init__(self, constants: Optional[Any] = None) -> None:
        self._constants = constants

    @classmethod
    def from_defaults(cls) -> "ConfigProvider":
        Constants = _import_constants()
        return cls(constants=Constants())

    @property
    def _c(self) -> Any:
        if self._constants is None:
            Constants = _import_constants()
            self._constants = Constants()
        return self._constants

    # --- read accessors ------------------------------------------------------

    @property
    def appdata_path(self) -> str:
        return getattr(self._c, "getAppdata", lambda: "")()

    @property
    def db_path(self) -> str:
        return getattr(self._c, "dbPath", "")

    @property
    def settings_path(self) -> str:
        return getattr(self._c, "settingsPath", "")

    @property
    def logs_path(self) -> str:
        return getattr(self._c, "logsPath", "")

    @property
    def cache_path(self) -> str:
        return getattr(self._c, "cache", "")

    @property
    def icon_path(self) -> str:
        return getattr(self._c, "iconPath", "")

    @property
    def settings(self) -> Mapping[str, Any]:
        return getattr(self._c, "settings", {}) or {}

    # --- write accessors -----------------------------------------------------

    def update_settings(self, updates: Mapping[str, Any]) -> MutableMapping[str, Any]:
        """Merge ``updates`` into the settings file and return the new dict.

        Mirrors the behavior of ``LegacyRuntime.setSettings`` without
        requiring the caller to inherit from ``Constants``.
        """
        settings_path = self.settings_path
        if not settings_path:
            raise RuntimeError("settings path not configured")

        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for section, values in updates.items():
            if isinstance(values, dict):
                data.setdefault(section, {})
                data[section].update(values)
            else:
                data[section] = values

        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        if self._constants is not None:
            try:
                self._constants.settings = data
            except Exception:  # pragma: no cover - legacy quirk
                pass
        return data

    def ensure_appdata(self) -> str:
        path = self.appdata_path
        if path and not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        return path


_default_provider: Optional[ConfigProvider] = None


def get_default_config_provider() -> ConfigProvider:
    """Return a process-wide default :class:`ConfigProvider`."""
    global _default_provider
    if _default_provider is None:
        _default_provider = ConfigProvider.from_defaults()
    return _default_provider


__all__ = ["ConfigProvider", "get_default_config_provider"]
