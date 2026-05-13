"""Compatibility shim — canonical search orchestration lives in
:mod:`adapters.search`.

The vendored ``search_engines.nova3`` qBittorrent plugin tree
(immutable, black-box dependency) still lives here and is loaded by
the orchestration worker as a subprocess. Direct imports of the
``nova3`` submodule remain supported; orchestration imports
(``from search_engines.facade import SearchFacade`` etc.) emit a
``DeprecationWarning`` and forward to :mod:`adapters.search`.
"""

from __future__ import annotations

import warnings as _warnings

from adapters.search import (  # noqa: F401
    DEFAULT_PROFILES,
    INTERACTIVE_PROFILE,
    STRICT_PROFILE,
    SearchFacade,
    SearchLimits,
    SearchProfile,
    SearchSummary,
    load_profile,
    search,
    search_strict,
)

_warnings.warn(
    "search_engines is a compatibility shim; import from adapters.search "
    "instead. The vendored search_engines.nova3 subtree is unaffected.",
    DeprecationWarning,
    stacklevel=2,
)

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
