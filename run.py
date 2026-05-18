"""AnimeManager single root startup script (ADR 0006).

Usage:
    python run.py [MODE] [--host HOST] [--port PORT] [--next-port PORT]

Modes:
    api  Launch the FastAPI HTTP / web UI client adapter via uvicorn (default).
    gui  Launch the embedded Tk client adapter.
    both Launch API + Next.js web UI dev server together.

All other startup logic lives inside the ``animemanager`` package
(``bootstrap.py``). This script intentionally contains no business
logic; it parses arguments and delegates.
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import shutil
import subprocess
import sys
import time


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="AnimeManager unified launcher (see ADR 0006).",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="api",
        help="Runtime mode (api, gui, both). Default: api (web UI).",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host interface for 'api' mode (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8081,
        help="TCP port for 'api' mode (default: 8081).",
    )
    parser.add_argument(
        "--next-dir",
        default="next-web",
        help="Path to Next.js app for 'both' mode (default: next-web).",
    )
    parser.add_argument(
        "--next-host",
        default="127.0.0.1",
        help="Host for Next.js dev server in 'both' mode (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--next-port",
        type=int,
        default=3000,
        help="Port for Next.js dev server in 'both' mode (default: 3000).",
    )
    parser.add_argument(
        "--next-script",
        default="dev",
        help="NPM script name to run for Next.js in 'both' mode (default: dev).",
    )
    parser.add_argument(
        "--npm-bin",
        default="npm",
        help="npm executable for 'both' mode (default: npm).",
    )
    return parser


def _ensure_package_path() -> None:
    """Make package imports work when run.py is invoked directly.

    The repo directory is the ``AnimeManager`` package. Its *parent* must
    be on ``sys.path`` so ``import AnimeManager...`` resolves; the repo
    root is appended so legacy flat imports (``clients``, ``bootstrap``)
    still work when modules are loaded outside the package prefix.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    if here not in sys.path:
        sys.path.append(here)


def _resolve_npm_executable(npm_bin: str) -> str | None:
    """Resolve npm on Windows where the launcher is usually ``npm.cmd``."""
    for candidate in (npm_bin, f"{npm_bin}.cmd", f"{npm_bin}.exe"):
        path = shutil.which(candidate)
        if path:
            return path
    return None


def _popen_command(cmd: list[str], *, cwd: str, env: dict[str, str] | None = None) -> subprocess.Popen:
    """Spawn a child process with Windows-safe npm/cmd handling."""
    if sys.platform == "win32":
        return subprocess.Popen(
            subprocess.list2cmdline(cmd),
            cwd=cwd,
            env=env,
            shell=True,
        )
    return subprocess.Popen(cmd, cwd=cwd, env=env)


def _backend_base_url(host: str, port: int) -> str:
    if host in {"0.0.0.0", "::"}:
        return f"http://127.0.0.1:{port}"
    return f"http://{host}:{port}"


def _terminate_process(proc: subprocess.Popen, *, timeout_s: float = 6.0) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2.0)
    except Exception:
        # Best effort shutdown only.
        pass


def _run_both(args: argparse.Namespace) -> int:
    repo_root = os.path.dirname(os.path.abspath(__file__))
    next_dir = os.path.abspath(os.path.join(repo_root, args.next_dir))
    if not os.path.isdir(next_dir):
        print(
            f"ERROR: Next.js directory not found: {next_dir}",
            file=sys.stderr,
        )
        return 2
    npm_path = _resolve_npm_executable(args.npm_bin)
    if not npm_path:
        print(
            f"ERROR: npm executable not found: {args.npm_bin}",
            file=sys.stderr,
        )
        return 2

    api_cmd = [
        sys.executable,
        os.path.abspath(__file__),
        "api",
        "--host",
        str(args.host),
        "--port",
        str(args.port),
    ]
    next_cmd = [
        npm_path,
        "run",
        str(args.next_script),
        "--",
        "--hostname",
        str(args.next_host),
        "--port",
        str(args.next_port),
    ]

    backend_base = _backend_base_url(args.host, args.port)
    next_base = f"http://{args.next_host}:{args.next_port}"
    api_env = os.environ.copy()
    api_env["ANIMEMANAGER_NEXT_UI_URL"] = next_base
    next_env = os.environ.copy()
    next_env["PYTHON_API_BASE_URL"] = backend_base
    next_env.setdefault("NEXT_PUBLIC_PYTHON_WS_BASE_URL", backend_base.replace("http://", "ws://").replace("https://", "wss://"))

    api_proc = _popen_command(api_cmd, cwd=repo_root, env=api_env)
    try:
        next_proc = _popen_command(next_cmd, cwd=next_dir, env=next_env)
    except OSError as exc:
        _terminate_process(api_proc)
        print(f"ERROR: failed to start Next.js dev server: {exc}", file=sys.stderr)
        return 2
    try:
        while True:
            api_rc = api_proc.poll()
            next_rc = next_proc.poll()
            if api_rc is not None or next_rc is not None:
                _terminate_process(api_proc)
                _terminate_process(next_proc)
                if api_rc not in (None, 0):
                    return int(api_rc)
                if next_rc not in (None, 0):
                    return int(next_rc)
                return 0
            time.sleep(0.25)
    except KeyboardInterrupt:
        _terminate_process(api_proc)
        _terminate_process(next_proc)
        return 130


def main(argv=None) -> int:
    _ensure_package_path()

    # Required on Windows when the GUI client uses multiprocessing.
    multiprocessing.freeze_support()

    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.mode == "both":
        return _run_both(args)

    try:
        from AnimeManager.bootstrap import main as bootstrap_main  # type: ignore
    except ImportError:  # pragma: no cover - flat checkout fallback
        from bootstrap import main as bootstrap_main

    kwargs = {}
    if args.mode == "api":
        kwargs.update({"host": args.host, "port": args.port})

    return bootstrap_main(mode=args.mode, **kwargs)


if __name__ == "__main__":
    sys.exit(main())
