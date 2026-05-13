"""Search orchestration adapters.

This package is the **canonical** home of the torrent search
orchestration layer (planner, engine policy, secure worker pool,
parser, dedupe, ranking, telemetry). The vendored ``nova3``
qBittorrent search-plugin tree remains at ``search_engines/nova3``
and is invoked as a black-box subprocess; do not import it directly.

The legacy ``search_engines`` package is a thin compatibility shim
that re-exports the public surface from here.
"""

from __future__ import annotations

from typing import Iterable, Iterator

from .config import (
    DEFAULT_PROFILES,
    INTERACTIVE_PROFILE,
    STRICT_PROFILE,
    SearchLimits,
    SearchProfile,
    load_profile,
)
from .facade import SearchFacade, SearchSummary, search_strict
from .facade import search as _facade_search


def search(terms: Iterable[str]) -> Iterator[dict]:
    """Backward-compatible streaming search."""
    return _facade_search(terms)


__all__ = [
    "search",
    "search_strict",
    "SearchFacade",
    "SearchSummary",
    "SearchProfile",
    "SearchLimits",
    "INTERACTIVE_PROFILE",
    "STRICT_PROFILE",
    "DEFAULT_PROFILES",
    "load_profile",
]
