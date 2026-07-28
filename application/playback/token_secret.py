"""Persist playback HMAC secret across process restarts."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


_SECRET_FILENAME = "playback_token_secret"


def load_or_create_playback_token_secret(appdata: str | os.PathLike[str]) -> bytes:
    """Return a stable secret stored under appdata, creating it on first use."""
    root = Path(appdata)
    root.mkdir(parents=True, exist_ok=True)
    path = root / _SECRET_FILENAME
    if path.is_file():
        raw = path.read_bytes().strip()
        if raw:
            return raw
    secret = secrets.token_hex(32).encode("ascii")
    path.write_bytes(secret)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return secret


__all__ = ["load_or_create_playback_token_secret"]
