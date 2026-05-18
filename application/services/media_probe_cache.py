"""Persistent on-disk cache for ffprobe-derived media metadata.

Entries are keyed by resolved path, mtime, and size so edits to a file
invalidate stale rows automatically. A small process-local LRU sits in
front of SQLite to avoid repeated disk I/O on hot paths.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

_LOG = logging.getLogger(__name__)


def _fingerprint_parts(resolved_path: str, mtime_ns: int, size: int) -> str:
    raw = f"{resolved_path}\0{mtime_ns}\0{size}".encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(raw).hexdigest()


class MediaProbeCache:
    """SQLite-backed probe cache with an in-memory LRU front layer."""

    def __init__(self, root: Path, *, mem_max: int = 512) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._db_path = self._root / "probe.sqlite3"
        self._lock = threading.Lock()
        self._mem: OrderedDict[str, tuple[dict[str, list[dict[str, Any]]], float | None]] = (
            OrderedDict()
        )
        self._mem_max = max(32, int(mem_max))
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS media_probe (
                        cache_key TEXT PRIMARY KEY,
                        duration REAL,
                        tracks_json TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def get(
        self, resolved_path: str, mtime_ns: int, size: int
    ) -> Optional[tuple[dict[str, list[dict[str, Any]]], float | None]]:
        key = _fingerprint_parts(resolved_path, mtime_ns, size)
        with self._lock:
            hit = self._mem.get(key)
            if hit is not None:
                self._mem.move_to_end(key)
                return hit
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            try:
                row = conn.execute(
                    "SELECT duration, tracks_json FROM media_probe WHERE cache_key = ?",
                    (key,),
                ).fetchone()
            finally:
                conn.close()
            if row is None:
                return None
            dur_raw, tracks_raw = row
            try:
                tracks_payload = json.loads(tracks_raw or "{}")
            except json.JSONDecodeError:
                _LOG.debug("probe_cache_corrupt key=%s", key[:12])
                return None
            audio = list(tracks_payload.get("audio") or [])
            subtitles = list(tracks_payload.get("subtitles") or [])
            duration: float | None
            if dur_raw is None:
                duration = None
            else:
                try:
                    d = float(dur_raw)
                except (TypeError, ValueError):
                    duration = None
                else:
                    duration = d if d > 0 else None
            tracks = {"audio": audio, "subtitles": subtitles}
            self._mem[key] = (tracks, duration)
            self._mem.move_to_end(key)
            while len(self._mem) > self._mem_max:
                self._mem.popitem(last=False)
            return tracks, duration

    def put(
        self,
        resolved_path: str,
        mtime_ns: int,
        size: int,
        *,
        tracks: dict[str, list[dict[str, Any]]],
        duration_seconds: float | None,
    ) -> None:
        key = _fingerprint_parts(resolved_path, mtime_ns, size)
        audio = list(tracks.get("audio") or [])
        subtitles = list(tracks.get("subtitles") or [])
        payload = {"audio": audio, "subtitles": subtitles}
        tracks_json = json.dumps(payload, separators=(",", ":"))
        dur_store: float | None
        if duration_seconds is None:
            dur_store = None
        else:
            try:
                d = float(duration_seconds)
            except (TypeError, ValueError):
                dur_store = None
            else:
                dur_store = d if d > 0 else None
        now = time.time()
        with self._lock:
            self._mem[key] = ({"audio": audio, "subtitles": subtitles}, dur_store)
            self._mem.move_to_end(key)
            while len(self._mem) > self._mem_max:
                self._mem.popitem(last=False)
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            try:
                conn.execute(
                    """
                    INSERT INTO media_probe(cache_key, duration, tracks_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        duration = excluded.duration,
                        tracks_json = excluded.tracks_json,
                        updated_at = excluded.updated_at
                    """,
                    (key, dur_store, tracks_json, now),
                )
                conn.commit()
            finally:
                conn.close()


__all__ = ["MediaProbeCache", "_fingerprint_parts"]
