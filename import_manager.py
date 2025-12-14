"""
Import Manager Utility for AnimeManager

This module provides utilities for handling imports in both package and standalone modes.
It enables the application to work whether run as a package or as individual scripts.
"""

import os
import sys
from pathlib import Path
from typing import Any, List, Optional, Union


class ImportManager:
    """Manages imports with fallback mechanisms for package/standalone compatibility."""

    _project_root: Optional[Path] = None
    _path_initialized: bool = False

    @classmethod
    def get_project_root(cls) -> Path:
        """Get the project root directory."""
        if cls._project_root is None:
            # Start from this file's location and work upward
            current = Path(__file__).resolve()

            # Look for project markers
            markers = ["__init__.py", "setup.py", "requirements.txt", "animeManager.py"]

            # Check current directory and parents
            for parent in [current.parent] + list(current.parents):
                if any((parent / marker).exists() for marker in markers):
                    cls._project_root = parent
                    break

            # Fallback to current file's parent
            if cls._project_root is None:
                cls._project_root = current.parent

        return cls._project_root

    @classmethod
    def ensure_package_path(cls) -> None:
        """Ensure the package root is in sys.path."""
        if not cls._path_initialized:
            project_root = str(cls.get_project_root())

            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            cls._path_initialized = True

    @classmethod
    def safe_import(
        cls,
        relative_path: str,
        fallback_path: Optional[str] = None,
        from_list: Optional[List[str]] = None,
    ) -> Any:
        """
        Safely import a module with relative/absolute fallback.

        Args:
            relative_path: Relative import path (e.g., '.classes')
            fallback_path: Absolute import path (e.g., 'AnimeManager.classes')
            from_list: List of names to import from module

        Returns:
            Imported module or None if failed
        """
        from_list = from_list or []

        try:
            # Try relative import first
            return __import__(relative_path, fromlist=from_list, level=1)
        except (ImportError, ValueError):
            try:
                # Try absolute import with fallback path
                if fallback_path:
                    cls.ensure_package_path()
                    return __import__(fallback_path, fromlist=from_list)

                # Try converting relative to absolute
                if relative_path.startswith("."):
                    # Convert .module to AnimeManager.module
                    abs_path = "AnimeManager" + relative_path
                    cls.ensure_package_path()
                    return __import__(abs_path, fromlist=from_list)

            except ImportError:
                pass

            # Last resort: try just the module name
            try:
                module_name = relative_path.lstrip(".")
                cls.ensure_package_path()
                return __import__(module_name, fromlist=from_list)
            except ImportError:
                return None

    @classmethod
    def import_from(
        cls,
        module_path: str,
        names: Union[str, List[str]],
        fallback_module: Optional[str] = None,
    ) -> dict:
        """
        Import specific names from a module with fallback.

        Args:
            module_path: Module to import from (relative or absolute)
            names: Name(s) to import
            fallback_module: Alternative module path

        Returns:
            Dictionary mapping names to imported objects
        """
        if isinstance(names, str):
            names = [names]

        result = {}

        # Try main module
        module = cls.safe_import(module_path, fallback_module, names)
        if module:
            for name in names:
                if hasattr(module, name):
                    result[name] = getattr(module, name)

        # If some names are missing, try fallback
        if len(result) < len(names) and fallback_module:
            fallback = cls.safe_import(fallback_module, None, names)
            if fallback:
                for name in names:
                    if name not in result and hasattr(fallback, name):
                        result[name] = getattr(fallback, name)

        return result

    @classmethod
    def get_import_context(cls) -> str:
        """
        Determine the current import context.

        Returns:
            'package' if running as package, 'standalone' if running as script
        """
        # Check if we're in a package context by looking for __package__
        frame = sys._getframe(1)
        package_name = frame.f_globals.get("__package__")

        if package_name:
            return "package"

        # Check if project root is in sys.path (indicates standalone)
        project_root = str(cls.get_project_root())
        if project_root in sys.path:
            return "standalone"

        return "unknown"


# Convenience functions for common import patterns
def safe_relative_import(module_path: str, names: Optional[List[str]] = None):
    """Safely import with relative path and automatic fallback."""
    return ImportManager.safe_import(module_path, None, names)


def import_anime_classes():
    """Import common AnimeManager classes with fallback."""
    return ImportManager.import_from(
        ".classes",
        ["Anime", "AnimeList", "Character", "Torrent", "TorrentList"],
        "classes",
    )


def import_core_components():
    """Import core AnimeManager components."""
    components = {}

    # Import classes
    components.update(import_anime_classes())

    # Import other core modules
    modules = {
        "Constants": (".constants", "constants"),
        "Logger": (".logger", "logger"),
        "Getters": (".getters", "getters"),
    }

    for class_name, (rel_path, abs_path) in modules.items():
        imported = ImportManager.import_from(rel_path, [class_name], abs_path)
        components.update(imported)

    # Import new component architecture
    component_modules = {
        "EventBus": (".core.event_bus", "core.event_bus"),
        "DependencyContainer": (".core.dependency_container", "core.dependency_container"),
        "BaseComponent": (".core.base_component", "core.base_component"),
        "ApplicationController": (".components.application_controller", "components.application_controller"),
        "DatabaseManager": (".components.database_manager", "components.database_manager"),
        "APICoordinator": (".components.api_coordinator", "components.api_coordinator"),
        "UIManager": (".components.ui_manager", "components.ui_manager"),
        "MediaManager": (".components.media_manager", "components.media_manager"),
        "DownloadManager": (".components.download_manager", "components.download_manager"),
        "SettingsManager": (".components.settings_manager", "components.settings_manager"),
    }

    for class_name, (rel_path, abs_path) in component_modules.items():
        imported = ImportManager.import_from(rel_path, [class_name], abs_path)
        components.update(imported)

    return components


# Initialize path on import
ImportManager.ensure_package_path()
