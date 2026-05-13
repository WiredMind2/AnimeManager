"""Compatibility shim — canonical lives in :mod:`adapters.search.worker`."""

from __future__ import annotations

import warnings as _warnings

from adapters.search.worker import *  # noqa: F401,F403
from adapters.search.worker import (  # noqa: F401
    JobOutcome,
    NovaWorker,
    SearchJob,
    _ProcessRunner,
)

_warnings.warn(
    "search_engines.worker is a compatibility shim; import from "
    "adapters.search.worker instead.",
    DeprecationWarning,
    stacklevel=2,
)
