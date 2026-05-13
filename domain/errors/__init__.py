"""Domain and application-level error hierarchy.

This module is the canonical home of the error classes. The legacy
``backend.domain.errors`` module is a thin compatibility shim that
re-exports from here.
"""

from __future__ import annotations


class AnimeManagerError(Exception):
    """Base class for refactored architecture errors."""


class NotFoundError(AnimeManagerError):
    """Raised when a requested resource cannot be found."""


class ValidationError(AnimeManagerError):
    """Raised when an input contract is invalid."""


class InfrastructureError(AnimeManagerError):
    """Raised when an infrastructure adapter fails."""


class UnauthorizedError(AnimeManagerError):
    """Raised when an action requires authentication."""


__all__ = [
    "AnimeManagerError",
    "NotFoundError",
    "ValidationError",
    "InfrastructureError",
    "UnauthorizedError",
]
