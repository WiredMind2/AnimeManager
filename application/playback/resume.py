"""Resume position and anchor segment math."""

from __future__ import annotations

import time
from pathlib import Path

from application.playback.contract import MIN_RESUME_SECONDS, PREFETCH_MARGIN


def resume_segment_index(
    playback_start_seconds: float,
    *,
    total_segments: int,
    segment_seconds: int,
) -> int:
    if playback_start_seconds < MIN_RESUME_SECONDS or total_segments <= 0 or segment_seconds <= 0:
        return 0
    index = int(float(playback_start_seconds) // segment_seconds)
    return max(0, min(index, total_segments - 1))


def anchor_segment(resume_seg: int) -> int:
    return max(0, resume_seg - PREFETCH_MARGIN)


def normalize_resume_seconds(value: float | None) -> float:
    if value is None:
        return 0.0
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not seconds or seconds < MIN_RESUME_SECONDS or not (seconds == seconds):
        return 0.0
    return seconds


def wait_for_file(target: Path, timeout: float) -> bool:
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        if target.is_file():
            return True
        if time.monotonic() >= deadline:
            return target.is_file()
        time.sleep(0.1)


__all__ = [
    "resume_segment_index",
    "anchor_segment",
    "normalize_resume_seconds",
    "wait_for_file",
]
