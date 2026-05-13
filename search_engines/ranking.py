"""Compatibility shim — canonical lives in :mod:`adapters.search.ranking`."""

from __future__ import annotations

import warnings as _warnings

from adapters.search.ranking import *  # noqa: F401,F403

_warnings.warn(
    "search_engines.ranking is a compatibility shim; import from "
    "adapters.search.ranking instead.",
    DeprecationWarning,
    stacklevel=2,
)
