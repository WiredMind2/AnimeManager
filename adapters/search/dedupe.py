"""Deterministic deduplication for parsed torrent results.

Replaces the legacy ``hash(dict.values())`` fallback (which always raised
and silently collapsed distinct items via ``None``) with a stable
fingerprint. Magnet infohashes are preferred; when absent, a tuple of
normalized identifying fields is used.

The ``ResultDeduper`` is thread-safe so multiple worker threads can push
results concurrently into a single dedupe instance.
"""

from __future__ import annotations

import threading
import unicodedata
from typing import Optional, Tuple

from .parser import TorrentResult


Fingerprint = Tuple[str, ...]


def fingerprint(result: TorrentResult) -> Fingerprint:
    """Compute a deterministic fingerprint for a torrent record.

    The infohash branch is case-insensitive so records produced through
    different upstream code paths (e.g., direct construction in tests vs.
    parser output) still collapse onto the same identity.
    """
    if result.infohash:
        return ("ih", result.infohash.strip().lower())
    name = _normalize_name(result.name)
    engine = (result.engine_url or "").strip().lower()
    desc = (result.desc_link or "").strip().lower()
    return ("nf", name, str(result.size), engine, desc)


def _normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).casefold()
    return " ".join(ch for ch in text.split() if ch)


class ResultDeduper:
    """Thread-safe O(1) duplicate tracker."""

    def __init__(self) -> None:
        self._seen: set[Fingerprint] = set()
        self._lock = threading.Lock()

    def register(self, result: TorrentResult) -> Optional[Fingerprint]:
        fp = fingerprint(result)
        with self._lock:
            if fp in self._seen:
                return None
            self._seen.add(fp)
        return fp

    def __len__(self) -> int:
        with self._lock:
            return len(self._seen)
