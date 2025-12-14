"""
SettingsManager component for handling configuration management.
Provides validation, change notification, and settings persistence.
"""

import json
import os
import threading
from typing import Any, Dict, Optional, Callable
from pathlib import Path

from ..core import BaseComponent


class SettingsManager(BaseComponent):
    """
    Manages application settings with validation and persistence.
    Provides change notifications and settings migration.
    """

    def __init__(self, settings_file: str = "settings.json"):
        super().__init__("SettingsManager")
        self._settings_file = Path(settings_file)
        self._settings: Dict[str, Any] = {}
        self._defaults: Dict[str, Any] = {}
        self._validators: Dict[str, Callable] = {}
        self._change_callbacks: Dict[str, list] = {}
        self._lock = threading.RLock()

    def _initialize(self) -> None:
        """Initialize the settings manager."""
        self.log("SETTINGS_MANAGER", "Initializing Settings Manager")

        # Set up default settings
        self._setup_defaults()

        # Load settings
        self._load_settings()

        # Subscribe to settings-related events
        self.subscribe_event("settings.save", self._handle_save_settings)
        self.subscribe_event("settings.reload", self._handle_reload_settings)

    def _start(self) -> None:
        """Start the settings manager."""
        self.log("SETTINGS_MANAGER", "Starting Settings Manager")

    def _stop(self) -> None:
        """Stop the settings manager."""
        # Save settings on shutdown
        self.save_settings()
        self.log("SETTINGS_MANAGER", "Settings Manager stopped")

    def _setup_defaults(self) -> None:
        """Set up default settings values."""
        self._defaults = {
            "database": {
                "type": "sqlite",
                "path": "./data/anime.db"
            },
            "ui": {
                "theme": "default",
                "language": "en",
                "window_size": [1200, 800]
            },
            "media": {
                "players_order": ["mpv", "vlc", "ffplay"],
                "default_player": "mpv"
            },
            "downloads": {
                "max_concurrent": 3,
                "default_folder": "./downloads"
            },
            "api": {
                "timeout": 30,
                "rate_limit": 60
            },
            "file_managers": {
                "last_fm_used": "local"
            },
            "torrent_managers": {
                "last_tm_used": "qbittorrent"
            }
        }

    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a setting value.

        Args:
            key: Setting key (dot notation supported)
            default: Default value if setting not found

        Returns:
            Setting value
        """
        with self._lock:
            return self._get_nested_value(self._settings, key, default)

    def set_setting(self, key: str, value: Any, save: bool = True) -> None:
        """
        Set a setting value.

        Args:
            key: Setting key (dot notation supported)
            value: New value
            save: Whether to save immediately
        """
        with self._lock:
            old_value = self._get_nested_value(self._settings, key)

            # Validate if validator exists
            if not self._validate_setting(key, value):
                raise ValueError(f"Invalid value for setting {key}: {value}")

            # Set the value
            self._set_nested_value(self._settings, key, value)

            # Notify change listeners
            if old_value != value:
                self._notify_change(key, value, old_value)

            if save:
                self.save_settings()

    def register_validator(self, key: str, validator: Callable[[Any], bool]) -> None:
        """
        Register a validator for a setting.

        Args:
            key: Setting key
            validator: Function that returns True if value is valid
        """
        with self._lock:
            self._validators[key] = validator

    def on_setting_change(self, key: str, callback: Callable[[str, Any, Any], None]) -> None:
        """
        Register a callback for setting changes.

        Args:
            key: Setting key to watch
            callback: Function called with (key, new_value, old_value)
        """
        with self._lock:
            if key not in self._change_callbacks:
                self._change_callbacks[key] = []
            self._change_callbacks[key].append(callback)

    def save_settings(self) -> bool:
        """
        Save settings to file.

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            with self._lock:
                # Ensure directory exists
                self._settings_file.parent.mkdir(parents=True, exist_ok=True)

                with open(self._settings_file, 'w', encoding='utf-8') as f:
                    json.dump(self._settings, f, indent=2, ensure_ascii=False)

            self.log("SETTINGS_MANAGER", f"Settings saved to {self._settings_file}")
            return True

        except Exception as e:
            self.log("SETTINGS_MANAGER", f"Error saving settings: {e}")
            return False

    def reload_settings(self) -> bool:
        """
        Reload settings from file.

        Returns:
            True if reloaded successfully, False otherwise
        """
        try:
            old_settings = self._settings.copy()
            self._load_settings()

            # Notify about changed settings
            self._notify_reload_changes(old_settings)

            self.log("SETTINGS_MANAGER", f"Settings reloaded from {self._settings_file}")
            return True

        except Exception as e:
            self.log("SETTINGS_MANAGER", f"Error reloading settings: {e}")
            return False

    def reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        with self._lock:
            old_settings = self._settings.copy()
            self._settings = self._defaults.copy()
            self._notify_reload_changes(old_settings)
            self.save_settings()

    def get_all_settings(self) -> Dict[str, Any]:
        """
        Get all settings.

        Returns:
            Copy of all settings
        """
        with self._lock:
            return self._settings.copy()

    def _load_settings(self) -> None:
        """Load settings from file."""
        try:
            if self._settings_file.exists():
                with open(self._settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)

                # Merge with defaults
                self._settings = self._merge_dicts(self._defaults, loaded)
            else:
                # Use defaults if file doesn't exist
                self._settings = self._defaults.copy()

        except Exception as e:
            self.log("SETTINGS_MANAGER", f"Error loading settings, using defaults: {e}")
            self._settings = self._defaults.copy()

    def _merge_dicts(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively merge dictionaries.

        Args:
            base: Base dictionary
            override: Override dictionary

        Returns:
            Merged dictionary
        """
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_dicts(result[key], value)
            else:
                result[key] = value

        return result

    def _get_nested_value(self, data: Dict[str, Any], key: str, default: Any = None) -> Any:
        """
        Get nested dictionary value using dot notation.

        Args:
            data: Dictionary to search
            key: Key with dot notation
            default: Default value

        Returns:
            Value or default
        """
        keys = key.split('.')
        current = data

        try:
            for k in keys:
                current = current[k]
            return current
        except (KeyError, TypeError):
            return default

    def _set_nested_value(self, data: Dict[str, Any], key: str, value: Any) -> None:
        """
        Set nested dictionary value using dot notation.

        Args:
            data: Dictionary to modify
            key: Key with dot notation
            value: Value to set
        """
        keys = key.split('.')
        current = data

        for k in keys[:-1]:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value

    def _validate_setting(self, key: str, value: Any) -> bool:
        """
        Validate a setting value.

        Args:
            key: Setting key
            value: Value to validate

        Returns:
            True if valid, False otherwise
        """
        validator = self._validators.get(key)
        if validator:
            return validator(value)
        return True

    def _notify_change(self, key: str, new_value: Any, old_value: Any) -> None:
        """
        Notify listeners of setting change.

        Args:
            key: Setting key
            new_value: New value
            old_value: Old value
        """
        callbacks = self._change_callbacks.get(key, [])
        for callback in callbacks:
            try:
                callback(key, new_value, old_value)
            except Exception as e:
                self.log("SETTINGS_MANAGER", f"Error in change callback for {key}: {e}")

        # Publish event
        self.publish_event("settings.changed", {
            "key": key,
            "new_value": new_value,
            "old_value": old_value
        })

    def _notify_reload_changes(self, old_settings: Dict[str, Any]) -> None:
        """
        Notify about changes after reload.

        Args:
            old_settings: Previous settings
        """
        # This is a simplified implementation
        # In practice, you'd do a deep diff
        self.publish_event("settings.reloaded")

    def _handle_save_settings(self, event_type: str, data: Any) -> None:
        """Handle save settings event."""
        self.save_settings()

    def _handle_reload_settings(self, event_type: str, data: Any) -> None:
        """Handle reload settings event."""
        self.reload_settings()