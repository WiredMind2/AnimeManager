"""Shared / cross-cutting technical helpers.

``shared`` contains framework-agnostic helpers used by ``application``
and ``adapters``. It must not contain feature business logic (that
lives in ``domain``) and must not import from ``adapters`` or
``clients`` (those are downstream layers).
"""

from __future__ import annotations

__all__: list[str] = []
