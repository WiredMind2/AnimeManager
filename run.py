"""AnimeManager single root startup script (ADR 0006).

Usage:
    python run.py [MODE] [--host HOST] [--port PORT]

Modes:
    gui  Launch the embedded Tk client adapter (default).
    api  Launch the FastAPI HTTP client adapter via uvicorn.

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
        default="gui",
        help="Runtime mode (gui, api). Default: gui.",
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
    if args.mode == "api":
        kwargs.update({"host": args.host, "port": args.port})

    return bootstrap_main(mode=args.mode, **kwargs)


if __name__ == "__main__":
    sys.exit(main())
