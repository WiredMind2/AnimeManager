"""Ports (interfaces) for AnimeManager.

Ports are pure ``Protocol`` / abstract declarations. They depend on
``domain`` and nothing else -- in particular they never import
concrete adapters, frameworks, or IO modules.

This package is the **canonical** home of the port interfaces. The
legacy ``backend.ports`` subpackage now consists of thin
compatibility shims that import from here.
"""

from __future__ import annotations

from ports.interfaces import (
    AnimeRepositoryPort,
    DownloadPort,
    MetadataProviderPort,
    UserActionsPort,
)

__all__ = [
    "AnimeRepositoryPort",
    "MetadataProviderPort",
    "DownloadPort",
    "UserActionsPort",
]
