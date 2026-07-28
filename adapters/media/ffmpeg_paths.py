"""Resolve project-local or PATH ffmpeg/ffprobe binaries."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# adapters/media/ffmpeg_paths.py → repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_BIN = _REPO_ROOT / "tools" / "ffmpeg" / "bin"

FFMPEG_MISSING_HINT = (
    "Playback is unavailable because ffmpeg/ffprobe was not found. "
    "Run `.venv/Scripts/python.exe scripts/install_ffmpeg.py` "
    "(or install ffmpeg on PATH), then restart the app."
)


def local_ffmpeg_bin_dir(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    return root / "tools" / "ffmpeg" / "bin"


def _exe_name(base: str) -> str:
    return f"{base}.exe" if os.name == "nt" else base


def _bin_is_usable(candidate: str) -> bool:
    path = Path(candidate)
    if path.is_file():
        return True
    return shutil.which(candidate) is not None


def resolve_ffmpeg_bins(repo_root: Path | None = None) -> tuple[str, str]:
    """Prefer ``tools/ffmpeg/bin``, then PATH, else bare command names."""
    bin_dir = local_ffmpeg_bin_dir(repo_root)
    local_ffmpeg = bin_dir / _exe_name("ffmpeg")
    local_ffprobe = bin_dir / _exe_name("ffprobe")
    if local_ffmpeg.is_file() and local_ffprobe.is_file():
        return str(local_ffmpeg.resolve()), str(local_ffprobe.resolve())

    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    return ffmpeg, ffprobe


def ffmpeg_bins_available(ffmpeg_bin: str, ffprobe_bin: str) -> bool:
    return _bin_is_usable(ffmpeg_bin) and _bin_is_usable(ffprobe_bin)


__all__ = [
    "FFMPEG_MISSING_HINT",
    "ffmpeg_bins_available",
    "local_ffmpeg_bin_dir",
    "resolve_ffmpeg_bins",
]
