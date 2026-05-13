"""Canonical AnimeManager bootstrap dispatcher.

This module is the **only** in-package entrypoint. ``run.py`` (the
single root-level startup script, see ADR 0006) delegates here. New
client adapters (GUI, HTTP, future CLI) plug in by adding a mode
handler below; they do not get their own ``__main__.py``.

Modes
-----
``gui``
    Launch the embedded Tk client adapter
    (``clients.tk.run``). Default.
``api``
    Launch the FastAPI / Uvicorn HTTP client adapter
    (``clients.http.app:app``). The HTTP runtime is a peer client of
    the embedded backend per ADR 0001, not a privileged layer.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import sys
from typing import Callable, Dict, Optional

_LOG = logging.getLogger("animemanager.bootstrap")


def _kickoff_startup_jobs() -> None:
    """Fire the startup processing pipeline on a background thread.

    The legacy ``Manager`` class drove a chain of update tasks
    (``UpdateUtils.updateAllProgression``) on startup that included
    pulling the latest anime data from every provider. After the
    architecture refactor that chain was lost; this helper resurrects
    it by asking the embedded facade to dispatch
    :class:`application.services.startup_jobs.StartupJobsService` as
    soon as the dependency graph is wired.

    Errors are swallowed: if the SDK cannot be imported (e.g. test
    harness, partial install) we still return cleanly so the rest of
    the bootstrap can proceed.
    """
    try:
        from clients.sdk import ClientSDK
    except ImportError:  # pragma: no cover - partial install
        try:
            from AnimeManager.clients.sdk import ClientSDK  # type: ignore
        except ImportError:
            _LOG.warning(
                "ClientSDK unavailable; skipping startup-jobs pipeline."
            )
            return

    try:
        sdk = ClientSDK()
        thread = sdk.kickoff_startup_jobs()
        if thread is None:
            _LOG.warning(
                "Embedded facade has no startup-jobs service; "
                "pipeline not started."
            )
    except Exception as exc:  # noqa: BLE001 - best-effort
        _LOG.warning("Startup-jobs pipeline failed to launch: %s", exc)


def _run_gui() -> int:
    """Launch the embedded Tk client adapter."""
    try:
        from clients.tk import run
    except ImportError:  # pragma: no cover - packaged install fallback
        from AnimeManager.clients.tk import run  # type: ignore

    multiprocessing.freeze_support()
    proc = multiprocessing.current_process()
    if proc.name == "MainProcess":
        _kickoff_startup_jobs()
        run()
    return 0


def _run_api(host: str = "0.0.0.0", port: int = 8081) -> int:
    """Launch the HTTP client adapter via uvicorn."""
    try:
        import uvicorn  # type: ignore
    except ImportError as exc:
        _LOG.error("uvicorn is required for the 'api' mode: %s", exc)
        print(
            "ERROR: 'api' mode requires uvicorn. Install with: pip install uvicorn fastapi",
            file=sys.stderr,
        )
        return 2

    try:
        from clients.http.app import app  # noqa: F401  (import check only)
    except ImportError as exc:
        _LOG.error("HTTP client adapter unavailable: %s", exc)
        return 2

    _kickoff_startup_jobs()
    uvicorn.run(
        "clients.http.app:app",
        host=host,
        port=port,
        timeout_graceful_shutdown=8,
    )
    return 0


# Mode dispatch table. New modes register here -- no additional
# entrypoints required.
_MODES: Dict[str, Callable[..., int]] = {
    "gui": _run_gui,
    "api": _run_api,
}


def list_modes() -> Dict[str, Callable[..., int]]:
    """Return the registered mode handlers."""
    return dict(_MODES)


def main(mode: str = "gui", **kwargs) -> int:
    """Dispatch to the requested runtime mode.

    Parameters
    ----------
    mode:
        Mode name. See :data:`_MODES`.
    **kwargs:
        Forwarded to the mode handler (e.g. ``host``/``port`` for API).

    Returns
    -------
    int
        Process exit code (``0`` on success).
    """
    if mode not in _MODES:
        valid = ", ".join(sorted(_MODES))
        print(
            f"ERROR: unknown mode '{mode}'. Valid modes: {valid}",
            file=sys.stderr,
        )
        return 2

    # Multi-process safety: only the main process should drive the
    # heavy GUI / HTTP startup. Subprocesses (spawned by
    # ``multiprocessing.freeze_support``) need to import the module
    # but skip the actual run.
    proc = multiprocessing.current_process()
    if proc.name != "MainProcess" and mode == "gui":
        return 0

    os.environ.setdefault("ANIMEMANAGER_BOOTSTRAP", mode)
    handler = _MODES[mode]
    return handler(**kwargs) or 0


__all__ = ["main", "list_modes"]
