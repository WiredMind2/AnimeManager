"""Domain layer for AnimeManager.

Pure business logic only: no IO, no framework imports, no UI imports.
Architecture rules are documented in
``docs/developer/layer-contracts.rst`` and ADRs 0003 / 0005 / 0006.

This package is the **canonical** home of the entities, DTOs,
policies, and error hierarchy. The legacy ``backend.domain``
subpackage now consists of thin compatibility shims that import from
here.
"""

from __future__ import annotations

from domain.dto import (
    AnimeListRequest,
    AnimeListResponse,
    DownloadRequest,
    SearchRequest,
)
from domain.entities import AnimeEntity, TorrentEntity, from_legacy_anime
from domain.errors import (
    AnimeManagerError,
    InfrastructureError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from domain.policies import derive_status, normalize_search_query

__all__ = [
    "AnimeEntity",
    "TorrentEntity",
    "from_legacy_anime",
    "SearchRequest",
    "AnimeListRequest",
    "DownloadRequest",
    "AnimeListResponse",
    "derive_status",
    "normalize_search_query",
    "AnimeManagerError",
    "NotFoundError",
    "ValidationError",
    "InfrastructureError",
    "UnauthorizedError",
]
