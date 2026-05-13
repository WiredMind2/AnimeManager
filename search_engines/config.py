"""Compatibility shim — canonical lives in :mod:`adapters.search.config`."""

from __future__ import annotations

import warnings as _warnings

from adapters.search.config import *  # noqa: F401,F403
from adapters.search.config import (  # noqa: F401
    DEFAULT_PROFILES,
    INTERACTIVE_PROFILE,
    STRICT_PROFILE,
    SearchLimits,
    SearchProfile,
    load_profile,
)

_warnings.warn(
    "search_engines.config is a compatibility shim; import from "
    "adapters.search.config instead.",
    DeprecationWarning,
    stacklevel=2,
)
