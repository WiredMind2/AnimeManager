"""Compatibility shim — canonical lives in :mod:`adapters.search.telemetry`."""

from __future__ import annotations

import warnings as _warnings

from adapters.search.telemetry import *  # noqa: F401,F403
from adapters.search.telemetry import get_metrics, structured_log  # noqa: F401

_warnings.warn(
    "search_engines.telemetry is a compatibility shim; import from "
    "adapters.search.telemetry instead.",
    DeprecationWarning,
    stacklevel=2,
)
