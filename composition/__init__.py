"""Composition root for the AnimeManager runtime.

This package is the **only** place allowed to wire concrete adapters into
application ports. See ``docs/adr/0006-package-layout-and-single-entrypoint.md``
and ``docs/developer/layer-contracts.rst``.
"""

from .root import build_embedded_facade

__all__ = ["build_embedded_facade"]
