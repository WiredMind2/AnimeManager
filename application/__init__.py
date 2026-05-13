"""Application layer for AnimeManager.

Use-case orchestration sits here. The application layer depends on
``domain`` and ``ports`` but never on concrete adapters; the
composition root injects adapter implementations.

This package is the **canonical** home of the application service.
The legacy ``backend.application`` subpackage now consists of thin
compatibility shims that import from here.
"""

from __future__ import annotations

from application.services.anime_service import AnimeApplicationService

__all__ = ["AnimeApplicationService"]
