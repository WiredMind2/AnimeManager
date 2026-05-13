"""Tk client adapter package.

``run`` is exposed lazily so importing siblings (e.g. :mod:`clients.tk.dialogs`)
does not transitively load the full Tk application module and trigger the
backend composition graph.
"""

from __future__ import annotations

from typing import Any

__all__ = ["run"]


def run(*args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
    """Lazy proxy for :func:`clients.tk.app.run`."""
    from .app import run as _run
    return _run(*args, **kwargs)
