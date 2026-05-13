"""Compatibility shim — canonical lives in :mod:`adapters.search.parser`."""

from __future__ import annotations

import warnings as _warnings

from adapters.search.parser import *  # noqa: F401,F403

_warnings.warn(
    "search_engines.parser is a compatibility shim; import from "
    "adapters.search.parser instead.",
    DeprecationWarning,
    stacklevel=2,
)
