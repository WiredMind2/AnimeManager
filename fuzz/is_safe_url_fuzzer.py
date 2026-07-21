#!/usr/bin/env python3
"""Atheris harness for shared.security.is_safe_url / validate_url."""

from __future__ import annotations

import sys
from pathlib import Path

import atheris

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

with atheris.instrument_imports():
    from shared.security import is_safe_url, validate_url


def _stub_resolver(_host: str) -> str:
    """Avoid real DNS during fuzzing; return a public IP."""
    return "8.8.8.8"


def TestOneInput(data: bytes) -> None:
    try:
        text = data.decode("utf-8", errors="surrogateescape")
    except Exception:
        return
    # Exercise both entry points with a stub resolver (no network).
    is_safe_url(text, resolver=_stub_resolver)
    validate_url(text, resolver=_stub_resolver)
    # Also allow http so scheme branching gets coverage.
    validate_url(
        text,
        allowed_schemes=("http", "https"),
        resolver=_stub_resolver,
    )


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
