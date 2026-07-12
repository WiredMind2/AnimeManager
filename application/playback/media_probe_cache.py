"""In-process ffprobe result cache keyed by path, mtime, and size."""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MediaProbeResult:
    audio: list[dict[str, Any]]
    subtitles: list[dict[str, Any]]
    duration_seconds: float


class MediaProbeCache:
    """Thread-safe LRU cache for ffprobe payloads."""

    def __init__(self, max_entries: int = 512) -> None:
        self._max_entries = max(16, int(max_entries))
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple[str, int, int], MediaProbeResult] = OrderedDict()

    def lookup(self, path: str) -> MediaProbeResult | None:
        key = self._cache_key(path)
        if key is None:
            return None
        with self._lock:
            hit = self._entries.get(key)
            if hit is None:
                return None
            self._entries.move_to_end(key)
            return hit

    def store(self, path: str, result: MediaProbeResult) -> None:
        key = self._cache_key(path)
        if key is None:
            return
        with self._lock:
            self._entries[key] = result
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def invalidate_path(self, path: str) -> None:
        normalized = os.path.normcase(os.path.normpath(str(path or "").strip()))
        if not normalized:
            return
        with self._lock:
            doomed = [key for key in self._entries if key[0] == normalized]
            for key in doomed:
                self._entries.pop(key, None)

    @staticmethod
    def _cache_key(path: str) -> tuple[str, int, int] | None:
        normalized = os.path.normcase(os.path.normpath(str(path or "").strip()))
        if not normalized or not os.path.isfile(normalized):
            return None
        try:
            stat = os.stat(normalized)
        except OSError:
            return None
        mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
        return (normalized, int(mtime_ns), int(stat.st_size))
