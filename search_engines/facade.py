"""Compatibility shim — canonical lives in :mod:`adapters.search.facade`."""

from __future__ import annotations

import warnings as _warnings

from adapters.search.facade import *  # noqa: F401,F403
from adapters.search.facade import (  # noqa: F401
    SearchFacade,
    SearchSummary,
    search,
    search_strict,
)

_warnings.warn(
    "search_engines.facade is a compatibility shim; import from "
    "adapters.search.facade instead.",
    DeprecationWarning,
    stacklevel=2,
)
