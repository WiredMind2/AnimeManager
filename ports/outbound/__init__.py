"""Outbound ports (driven interfaces implemented by adapters).

Re-exports the canonical port interfaces from :mod:`ports.interfaces`
so callers can write ``from ports.outbound import AnimeRepositoryPort``.
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
    "DownloadPort",
    "MetadataProviderPort",
    "UserActionsPort",
]
