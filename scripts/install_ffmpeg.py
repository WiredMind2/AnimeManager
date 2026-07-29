#!/usr/bin/env python3
"""Download project-local ffmpeg/ffprobe into tools/ffmpeg/bin.

Windows: gyan.dev release essentials zip.
Other platforms: print install guidance (use system package manager).

When the newest release advertises NVENC but cannot open the encoder on the
local NVIDIA driver (common with ffmpeg 8.1+ requiring NVENC API 13.1 while
drivers still expose 13.0), the installer falls back to the previous release
so GPU playback keeps working.
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

# Newest essentials build (rolling).
WIN_URL_LATEST = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
# Previous release — typically built against an older NVENC SDK that still
# works on current Game Ready drivers (e.g. 581.x / API 13.0).
WIN_URL_NVENC_COMPAT = (
    "https://github.com/GyanD/codexffmpeg/releases/download/8.0.1/"
    "ffmpeg-8.0.1-essentials_build.zip"
)


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


def _nvenc_usable(ffmpeg_path: Path) -> bool:
    """True when h264_nvenc can open (listed alone is not enough)."""
    if not ffmpeg_path.is_file():
        return False
    try:
        result = subprocess.run(
            [
                str(ffmpeg_path),
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=256x144:d=0.1",
                "-frames:v",
                "1",
                "-c:v",
                "h264_nvenc",
                "-f",
                "null",
                "-",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _nvenc_listed(ffmpeg_path: Path) -> bool:
    try:
        result = subprocess.run(
            [str(ffmpeg_path), "-hide_banner", "-encoders"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "h264_nvenc" in ((result.stdout or "") + (result.stderr or ""))


def _download_and_extract(url: str, dest_ffmpeg: Path, dest_ffprobe: Path) -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="am-ffmpeg-") as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / "ffmpeg.zip"
        print(f"Downloading {url} …")
        urllib.request.urlretrieve(url, archive)  # noqa: S310 — fixed vendor URL
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract_dir)
        found_ffmpeg = next(extract_dir.rglob(_exe("ffmpeg")), None)
        found_ffprobe = next(extract_dir.rglob(_exe("ffprobe")), None)
        if found_ffmpeg is None or found_ffprobe is None:
            raise RuntimeError("ffmpeg / ffprobe not found in archive")
        shutil.copy2(found_ffmpeg, dest_ffmpeg)
        shutil.copy2(found_ffprobe, dest_ffprobe)


def _install_windows(*, force: bool, prefer_gpu: bool) -> int:
    ffmpeg_path, ffprobe_path = _bin_paths()
    if (
        not force
        and _is_runnable(ffmpeg_path)
        and _is_runnable(ffprobe_path)
        and (not prefer_gpu or not _nvenc_listed(ffmpeg_path) or _nvenc_usable(ffmpeg_path))
    ):
        print(f"Already installed:\n  {ffmpeg_path}\n  {ffprobe_path}")
        if _nvenc_usable(ffmpeg_path):
            print("NVENC: usable (GPU H.264 encode OK)")
        elif _nvenc_listed(ffmpeg_path):
            print(
                "NVENC: listed but unusable on this driver — re-run with "
                "--force --prefer-gpu to install a compatible build."
            )
        return 0

    candidates = [WIN_URL_LATEST]
    if prefer_gpu:
        # Try latest first; if NVENC cannot open, fall back.
        candidates = [WIN_URL_LATEST, WIN_URL_NVENC_COMPAT]

    last_error: Exception | None = None
    for url in candidates:
        try:
            _download_and_extract(url, ffmpeg_path, ffprobe_path)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"Download failed ({url}): {exc}", file=sys.stderr)
            continue
        if not _is_runnable(ffmpeg_path) or not _is_runnable(ffprobe_path):
            print("ERROR: installed binaries failed -version check", file=sys.stderr)
            continue
        if prefer_gpu and _nvenc_listed(ffmpeg_path) and not _nvenc_usable(ffmpeg_path):
            print(
                "NVENC cannot open with this build (driver/SDK mismatch); "
                "trying a compatible release…"
            )
            continue
        print(f"Installed:\n  {ffmpeg_path}\n  {ffprobe_path}")
        if _nvenc_usable(ffmpeg_path):
            print("NVENC: usable (GPU H.264 encode OK)")
        elif _nvenc_listed(ffmpeg_path):
            print(
                "NVENC: listed but unusable — update NVIDIA drivers to 610+ "
                "or re-run with --prefer-gpu."
            )
        else:
            print("NVENC: not present in this build")
        print("Restart AnimeManager so playback picks up the project-local bins.")
        return 0

    if last_error is not None:
        print(f"ERROR: {last_error}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when binaries already look runnable",
    )
    parser.add_argument(
        "--prefer-gpu",
        action="store_true",
        default=True,
        help="Prefer a build whose NVENC encoder opens on this machine (default)",
    )
    parser.add_argument(
        "--no-prefer-gpu",
        action="store_false",
        dest="prefer_gpu",
        help="Always keep the latest release even if NVENC cannot open",
    )
    args = parser.parse_args(argv)

    if os.name == "nt":
        return _install_windows(force=bool(args.force), prefer_gpu=bool(args.prefer_gpu))

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
