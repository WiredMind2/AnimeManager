"""Canonical AnimeManager bootstrap dispatcher.

This module is the **only** in-package entrypoint. ``run.py`` (the
single root-level startup script, see ADR 0006) delegates here. New
client adapters (GUI, HTTP, future CLI) plug in by adding a mode
handler below; they do not get their own ``__main__.py``.

Modes
-----
``web``
    Launch the FastAPI backend plus the Next.js frontend
    (``next-web/``). Default.
``gui``
    Launch the embedded Tk client adapter
    (``clients.tk.run``).
``api``
    Launch the FastAPI / Uvicorn HTTP client adapter
    (``clients.http.app:app``). The HTTP runtime is a peer client of
    the embedded backend per ADR 0001, not a privileged layer.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
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
        else:
            loop = sdk.start_schedule_loop()
            if loop is None:
                _LOG.warning(
                    "Embedded facade has no schedule refresh loop; "
                    "daily fetch not scheduled."
                )
            auto_loop = sdk.start_auto_download_loop()
            if auto_loop is None:
                _LOG.warning(
                    "Embedded facade has no auto-download loop; "
                    "auto-download not scheduled."
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


def _repo_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _loopback_host(host: str) -> str:
    if host in ("0.0.0.0", "::", "[::]"):
        return "127.0.0.1"
    return host


def _service_origin(host: str, port: int) -> str:
    return f"http://{_loopback_host(host)}:{port}"


def _web_prerequisite_error(next_web_dir: str) -> Optional[int]:
    """Return an exit code when web mode cannot start, else ``None``."""
    try:
        import uvicorn  # type: ignore  # noqa: F401
    except ImportError as exc:
        _LOG.error("uvicorn is required for the 'web' mode: %s", exc)
        print(
            "ERROR: 'web' mode requires uvicorn. Install with: pip install uvicorn fastapi",
            file=sys.stderr,
        )
        return 2

    try:
        from clients.http.app import app  # noqa: F401
    except ImportError as exc:
        _LOG.error("HTTP client adapter unavailable: %s", exc)
        return 2

    if shutil.which("npm") is None:
        print(
            "ERROR: 'web' mode requires Node.js/npm on PATH. "
            "Install Node.js from https://nodejs.org/ and retry.",
            file=sys.stderr,
        )
        return 2

    if not os.path.isfile(os.path.join(next_web_dir, "package.json")):
        print(
            f"ERROR: Next.js frontend not found at {next_web_dir!r}.",
            file=sys.stderr,
        )
        return 2

    if not os.path.isdir(os.path.join(next_web_dir, "node_modules")):
        print(
            "ERROR: next-web dependencies are not installed.\n"
            "Run: cd next-web && npm install",
            file=sys.stderr,
        )
        return 2

    return None


def _wait_for_http(url: str, timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.25)
    return False


def _terminate_process(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _run_web(
    host: str = "0.0.0.0",
    port: int = 8081,
    next_port: int = 3000,
) -> int:
    """Launch FastAPI and the Next.js dev server together."""
    repo = _repo_root()
    next_web_dir = os.path.join(repo, "next-web")

    prereq_error = _web_prerequisite_error(next_web_dir)
    if prereq_error is not None:
        return prereq_error

    backend_origin = _service_origin(host, port)
    frontend_origin = _service_origin("127.0.0.1", next_port)

    # Startup jobs run inside the uvicorn child via FastAPI lifespan
    # (``_warm_embedded_backend``). Do not kick off here: this parent
    # process has a separate ClientSDK/LibTorrent graph and would race
    # the child on MariaDB (duplicate torrents PRIMARY inserts).

    api_env = os.environ.copy()
    api_env["WEB_FRONTEND_URL"] = frontend_origin

    next_env = os.environ.copy()
    next_env["BACKEND_URL"] = backend_origin
    next_env["NEXT_PUBLIC_APP_URL"] = frontend_origin
    next_env["PORT"] = str(next_port)

    print(f"Starting FastAPI backend at {backend_origin} ...")
    api_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "clients.http.app:app",
            "--host",
            host,
            "--port",
            str(port),
            "--timeout-graceful-shutdown",
            "8",
        ],
        cwd=repo,
        env=api_env,
    )

    if not _wait_for_http(f"{backend_origin}/"):
        print(
            "ERROR: FastAPI backend failed to become ready in time.",
            file=sys.stderr,
        )
        _terminate_process(api_proc)
        return 2

    print(f"Starting Next.js frontend at {frontend_origin} ...")
    npm_cmd = shutil.which("npm")
    if npm_cmd is None:
        _terminate_process(api_proc)
        return 2

    next_proc = subprocess.Popen(
        [npm_cmd, "run", "dev", "--", "--port", str(next_port)],
        cwd=next_web_dir,
        env=next_env,
    )

    exit_code = 0
    try:
        next_exit = next_proc.wait()
        if next_exit != 0:
            exit_code = next_exit
    except KeyboardInterrupt:
        exit_code = 0
    finally:
        _terminate_process(next_proc)
        _terminate_process(api_proc)

    return exit_code


# Mode dispatch table. New modes register here -- no additional
# entrypoints required.
_MODES: Dict[str, Callable[..., int]] = {
    "web": _run_web,
    "gui": _run_gui,
    "api": _run_api,
}


def list_modes() -> Dict[str, Callable[..., int]]:
    """Return the registered mode handlers."""
    return dict(_MODES)


def main(mode: str = "web", **kwargs) -> int:
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
