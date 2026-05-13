"""Compatibility shim — canonical lives in :mod:`adapters.search.dedupe`."""

from __future__ import annotations

import warnings as _warnings

from adapters.search.dedupe import *  # noqa: F401,F403

_warnings.warn(
    "search_engines.dedupe is a compatibility shim; import from "
    "adapters.search.dedupe instead.",
    DeprecationWarning,
    stacklevel=2,
)
