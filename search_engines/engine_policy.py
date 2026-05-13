"""Compatibility shim — canonical lives in :mod:`adapters.search.engine_policy`."""

from __future__ import annotations

import warnings as _warnings

from adapters.search.engine_policy import *  # noqa: F401,F403
from adapters.search.engine_policy import (  # noqa: F401
    EnginePolicy,
    get_default_policy,
)

_warnings.warn(
    "search_engines.engine_policy is a compatibility shim; import from "
    "adapters.search.engine_policy instead.",
    DeprecationWarning,
    stacklevel=2,
)
