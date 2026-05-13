"""Generic technical helpers.

This package is the **canonical** home of the generic utilities
historically shipped under ``general_utils`` and the import-path
bootstrapper from ``import_manager``. The legacy root modules are
thin compatibility shims that forward here.
"""

from __future__ import annotations

from shared.utils.general import *  # noqa: F401,F403
from shared.utils.import_manager import ImportManager  # noqa: F401

__all__: list[str] = ["ImportManager"]
