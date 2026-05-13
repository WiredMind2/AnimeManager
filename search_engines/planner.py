"""Compatibility shim — canonical lives in :mod:`adapters.search.planner`."""

from __future__ import annotations

import warnings as _warnings

from adapters.search.planner import *  # noqa: F401,F403

_warnings.warn(
    "search_engines.planner is a compatibility shim; import from "
    "adapters.search.planner instead.",
    DeprecationWarning,
    stacklevel=2,
)
