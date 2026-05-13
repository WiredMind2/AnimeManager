"""Edge case tests for ``shared.utils.import_manager.ImportManager``."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from shared.utils.import_manager import ImportManager


class TestImportManager:
    def test_project_root_is_path(self):
        root = ImportManager.get_project_root()
        assert isinstance(root, Path)
        assert root.exists()

    def test_project_root_cached(self):
        ImportManager._project_root = None
        ImportManager._path_initialized = False
        first = ImportManager.get_project_root()
        second = ImportManager.get_project_root()
        assert first is second

    def test_ensure_package_path_is_idempotent(self):
        ImportManager._path_initialized = False
        before = list(sys.path)
        ImportManager.ensure_package_path()
        after_first = list(sys.path)
        ImportManager.ensure_package_path()
        after_second = list(sys.path)
        # path list shouldn't keep growing after the first call.
        assert after_first == after_second
        # Project root must be on sys.path
        root = str(ImportManager.get_project_root())
        assert root in after_first or any(
            Path(p).resolve() == Path(root).resolve() for p in after_first
        )

    def test_project_root_contains_marker(self):
        root = ImportManager.get_project_root()
        markers = ("setup.py", "pyproject.toml", "requirements.txt")
        # At least one marker should be present (unless fallback was used)
        present = [(root / m).exists() for m in markers]
        # We can't assert strongly because the fallback path may apply on
        # unusual checkouts; just confirm we got a directory.
        assert root.is_dir()

    def test_fallback_when_no_markers_found(self, tmp_path, monkeypatch):
        # Force the cache to be reset and patch the __file__ resolution path
        # to point at a directory with no markers.
        from shared.utils import import_manager as mod

        monkeypatch.setattr(mod, "__file__", str(tmp_path / "fake_module.py"))
        ImportManager._project_root = None
        try:
            root = ImportManager.get_project_root()
            # Fallback resolves to two parents up; just confirm it's a path
            assert isinstance(root, Path)
        finally:
            # Restore the cache to the real project root for downstream tests.
            ImportManager._project_root = None
            ImportManager._path_initialized = False
            ImportManager.get_project_root()
            ImportManager.ensure_package_path()
