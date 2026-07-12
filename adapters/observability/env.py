"""Load optional local environment files for observability exporters."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path) -> None:
    """Populate ``os.environ`` from a simple ``KEY=value`` file.

    Existing environment variables are never overwritten.
    """
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_repo_env() -> None:
    """Load ``.env`` from the repository root when present."""
    root = Path(__file__).resolve().parents[2]
    load_env_file(root / ".env")
