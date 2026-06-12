"""AnimeManager single root startup script (ADR 0006).

Usage:
    python run.py [MODE] [--host HOST] [--port PORT] [--next-port PORT]

Modes:
    web  Launch FastAPI + Next.js frontend (default).
    gui  Launch the embedded Tk client adapter.
    api  Launch the FastAPI HTTP client adapter via uvicorn only.

All other startup logic lives inside the ``animemanager`` package
(``bootstrap.py``). This script intentionally contains no business
logic; it parses arguments and delegates.
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="AnimeManager unified launcher (see ADR 0006).",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="web",
        help="Runtime mode (web, gui, api). Default: web.",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host interface for 'web' and 'api' modes (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8081,
        help="TCP port for the FastAPI backend (default: 8081).",
    )
    parser.add_argument(
        "--next-port",
        type=int,
        default=3000,
        help="TCP port for the Next.js frontend in 'web' mode (default: 3000).",
    )
    return parser


def _ensure_package_path() -> None:
    """Make repo-root imports work when run.py is invoked directly.

    The repo root itself is the package, so the *parent* of this file
    is what needs to be on ``sys.path`` so that the package's
    sub-modules import cleanly when running ``python run.py``.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)


def main(argv=None) -> int:
    _ensure_package_path()

    # Required on Windows when the GUI client uses multiprocessing.
    multiprocessing.freeze_support()

    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        from bootstrap import main as bootstrap_main
    except ImportError:  # pragma: no cover - packaged install fallback
        from AnimeManager.bootstrap import main as bootstrap_main  # type: ignore

    kwargs = {}
    if args.mode in ("api", "web"):
        kwargs.update({"host": args.host, "port": args.port})
    if args.mode == "web":
        kwargs.update({"next_port": args.next_port})

    return bootstrap_main(mode=args.mode, **kwargs)


if __name__ == "__main__":
    sys.exit(main())
