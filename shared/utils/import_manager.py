"""Import path bootstrapper.

A handful of legacy modules (``classes``, ``logger``, ``animeAPI`` etc.) need
to be importable both as part of the ``AnimeManager`` package *and* as
standalone top-level modules (for example when invoked from a script or by
a sub-module that lives outside the package tree).

To keep those two execution modes working without duplicating ``try/except``
boilerplate everywhere, this module exposes a single class
(:class:`ImportManager`) whose :meth:`ImportManager.ensure_package_path`
classmethod adds the project root to ``sys.path``.

Historically this module also offered a ``import_core_components`` helper
that dynamically imported the old monolithic component graph (``UIManager``,
``ApplicationController``, ``MediaManager`` and ``SettingsManager``). Those
modules were removed during the client/server refactor and the helper has
been retired together with them. The new wiring lives in
:func:`AnimeManager.backend.build_embedded_facade`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


class ImportManager:
    """Tiny helper used by legacy modules to find the project root."""

    _project_root: Optional[Path] = None
    _path_initialized: bool = False

    @classmethod
    def get_project_root(cls) -> Path:
        """Return the absolute path of the project root.

        Walks up from this file looking for well-known project markers; if
        none is found, falls back to the directory containing this module.
        """
        if cls._project_root is None:
            current = Path(__file__).resolve()
            # ``__init__.py`` is no longer a marker because this file now
            # lives inside the ``shared.utils`` subpackage. Look for
            # repository-root anchors only.
            markers = ("setup.py", "pyproject.toml", "requirements.txt")

            for parent in [current.parent] + list(current.parents):
                if any((parent / marker).exists() for marker in markers):
                    cls._project_root = parent
                    break

            if cls._project_root is None:
                # Fall back to two directories up so ``shared/utils/...``
                # resolves to the repository root.
                cls._project_root = current.parent.parent.parent

        return cls._project_root

    @classmethod
    def ensure_package_path(cls) -> None:
        """Insert the project root into ``sys.path`` exactly once."""
        if cls._path_initialized:
            return

        project_root = str(cls.get_project_root())
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        cls._path_initialized = True


# Make sure ``sys.path`` is ready as soon as this module is imported so the
# legacy modules below can rely on top-level imports as a fallback.
ImportManager.ensure_package_path()
