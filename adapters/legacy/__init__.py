"""Legacy bridge adapters.

This package is the **canonical** home of :class:`LegacyRuntime` and
the bridge adapters. The legacy ``backend.adapters.legacy_runtime``
module is a thin compatibility shim that re-exports from here.
"""

from __future__ import annotations

from adapters.legacy.runtime import (
    LegacyAnimeRepositoryAdapter,
    LegacyDownloadAdapter,
    LegacyMetadataProviderAdapter,
    LegacyRuntime,
    LegacyUserActionsAdapter,
)

__all__ = [
    "LegacyRuntime",
    "LegacyAnimeRepositoryAdapter",
    "LegacyMetadataProviderAdapter",
    "LegacyDownloadAdapter",
    "LegacyUserActionsAdapter",
]
