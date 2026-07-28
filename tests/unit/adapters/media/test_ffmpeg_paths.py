"""Tests for project-local ffmpeg path resolution."""

from __future__ import annotations

from pathlib import Path

from adapters.media.ffmpeg_paths import (
    FFMPEG_MISSING_HINT,
    ffmpeg_bins_available,
    resolve_ffmpeg_bins,
)


def test_resolve_prefers_tools_ffmpeg_bin(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "tools" / "ffmpeg" / "bin"
    bin_dir.mkdir(parents=True)
    ffmpeg = bin_dir / "ffmpeg.exe"
    ffprobe = bin_dir / "ffprobe.exe"
    ffmpeg.write_bytes(b"x")
    ffprobe.write_bytes(b"x")

    monkeypatch.setattr("adapters.media.ffmpeg_paths.os.name", "nt")
    resolved = resolve_ffmpeg_bins(tmp_path)
    assert resolved == (str(ffmpeg.resolve()), str(ffprobe.resolve()))


def test_resolve_falls_back_to_which(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "adapters.media.ffmpeg_paths.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    ffmpeg, ffprobe = resolve_ffmpeg_bins(tmp_path)
    assert ffmpeg == "/usr/bin/ffmpeg"
    assert ffprobe == "/usr/bin/ffprobe"


def test_ffmpeg_bins_available_false_for_missing_names():
    assert ffmpeg_bins_available("no-such-ffmpeg-xyz", "no-such-ffprobe-xyz") is False


def test_missing_hint_mentions_install_script():
    assert "install_ffmpeg.py" in FFMPEG_MISSING_HINT
