#!/usr/bin/env python3
"""Download project-local ffmpeg/ffprobe into tools/ffmpeg/bin.

Windows: gyan.dev release essentials zip.
Other platforms: print install guidance (use system package manager).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = REPO_ROOT / "tools" / "ffmpeg" / "bin"
WIN_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def _exe(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def _bin_paths() -> tuple[Path, Path]:
    return BIN_DIR / _exe("ffmpeg"), BIN_DIR / _exe("ffprobe")


def _is_runnable(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        result = subprocess.run(
            [str(path), "-version"],
            check=False,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _install_windows(*, force: bool) -> int:
    ffmpeg_path, ffprobe_path = _bin_paths()
    if not force and _is_runnable(ffmpeg_path) and _is_runnable(ffprobe_path):
        print(f"Already installed:\n  {ffmpeg_path}\n  {ffprobe_path}")
        return 0

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="am-ffmpeg-") as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / "ffmpeg-release-essentials.zip"
        print(f"Downloading {WIN_URL} …")
        urllib.request.urlretrieve(WIN_URL, archive)  # noqa: S310 — fixed vendor URL
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract_dir)
        found_ffmpeg = next(extract_dir.rglob("ffmpeg.exe"), None)
        found_ffprobe = next(extract_dir.rglob("ffprobe.exe"), None)
        if found_ffmpeg is None or found_ffprobe is None:
            print("ERROR: ffmpeg.exe / ffprobe.exe not found in archive", file=sys.stderr)
            return 1
        shutil.copy2(found_ffmpeg, ffmpeg_path)
        shutil.copy2(found_ffprobe, ffprobe_path)

    if not _is_runnable(ffmpeg_path) or not _is_runnable(ffprobe_path):
        print("ERROR: installed binaries failed -version check", file=sys.stderr)
        return 1
    print(f"Installed:\n  {ffmpeg_path}\n  {ffprobe_path}")
    print("Restart AnimeManager so playback picks up the project-local bins.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when binaries already look runnable",
    )
    args = parser.parse_args(argv)

    if os.name == "nt":
        return _install_windows(force=bool(args.force))

    print(
        "This installer currently downloads Windows essentials builds only.\n"
        "On this platform, install ffmpeg/ffprobe via your package manager\n"
        "(e.g. brew install ffmpeg, apt install ffmpeg) so they are on PATH,\n"
        f"or place binaries in:\n  {BIN_DIR}",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
