"""Unit tests for :mod:`application.services.media_probe_cache`."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from application.services.media_probe_cache import MediaProbeCache, _fingerprint_parts


@pytest.fixture
def cache_root(tmp_path: Path) -> Path:
    return tmp_path / "probe-cache"


def test_fingerprint_parts_stable_and_unique():
    a = _fingerprint_parts("/media/ep.mkv", 100, 2048)
    b = _fingerprint_parts("/media/ep.mkv", 100, 2048)
    c = _fingerprint_parts("/media/ep.mkv", 101, 2048)
    assert a == b
    assert a != c
    assert len(a) == 64


def test_get_miss_returns_none(cache_root: Path):
    cache = MediaProbeCache(cache_root)
    assert cache.get("/files/show.mkv", 1, 99) is None


def test_put_then_get_memory_hit(cache_root: Path):
    cache = MediaProbeCache(cache_root, mem_max=32)
    tracks = {"audio": [{"id": 0, "label": "jpn"}], "subtitles": []}
    cache.put(
        "/files/show.mkv",
        10,
        500,
        tracks=tracks,
        duration_seconds=120.5,
    )
    hit = cache.get("/files/show.mkv", 10, 500)
    assert hit is not None
    got_tracks, duration = hit
    assert got_tracks["audio"][0]["label"] == "jpn"
    assert duration == pytest.approx(120.5)


def test_get_loads_from_sqlite_when_not_in_memory(cache_root: Path):
    cache = MediaProbeCache(cache_root, mem_max=32)
    path = "/files/persist.mkv"
    mtime, size = 42, 1000
    cache.put(
        path,
        mtime,
        size,
        tracks={"audio": [], "subtitles": [{"id": 1, "label": "eng"}]},
        duration_seconds=90.0,
    )
    cache._mem.clear()
    hit = cache.get(path, mtime, size)
    assert hit is not None
    tracks, duration = hit
    assert tracks["subtitles"][0]["label"] == "eng"
    assert duration == pytest.approx(90.0)


def test_fingerprint_change_invalidates_entry(cache_root: Path):
    cache = MediaProbeCache(cache_root)
    cache.put(
        "/files/ep.mkv",
        1,
        100,
        tracks={"audio": [], "subtitles": []},
        duration_seconds=10.0,
    )
    assert cache.get("/files/ep.mkv", 2, 100) is None


def test_corrupt_tracks_json_returns_none(cache_root: Path):
    cache = MediaProbeCache(cache_root)
    key = _fingerprint_parts("/bad.mkv", 1, 1)
    conn = sqlite3.connect(cache._db_path)
    try:
        conn.execute(
            "INSERT INTO media_probe(cache_key, duration, tracks_json, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (key, 1.0, "{not-json", 0.0),
        )
        conn.commit()
    finally:
        conn.close()
    assert cache.get("/bad.mkv", 1, 1) is None


def test_invalid_duration_in_db_treated_as_none(cache_root: Path):
    cache = MediaProbeCache(cache_root)
    key = _fingerprint_parts("/dur.mkv", 5, 5)
    payload = json.dumps({"audio": [], "subtitles": []})
    conn = sqlite3.connect(cache._db_path)
    try:
        conn.execute(
            "INSERT INTO media_probe(cache_key, duration, tracks_json, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (key, "nope", payload, 0.0),
        )
        conn.commit()
    finally:
        conn.close()
    tracks, duration = cache.get("/dur.mkv", 5, 5)
    assert tracks == {"audio": [], "subtitles": []}
    assert duration is None


def test_put_rejects_non_positive_duration(cache_root: Path):
    cache = MediaProbeCache(cache_root)
    cache.put(
        "/files/zero.mkv",
        1,
        1,
        tracks={"audio": [], "subtitles": []},
        duration_seconds=0,
    )
    _, duration = cache.get("/files/zero.mkv", 1, 1)
    assert duration is None


def test_lru_evicts_oldest_memory_entries(cache_root: Path):
    cache = MediaProbeCache(cache_root, mem_max=32)
    for i in range(40):
        cache.put(
            f"/files/{i}.mkv",
            i,
            i,
            tracks={"audio": [], "subtitles": []},
            duration_seconds=float(i + 1),
        )
    assert len(cache._mem) <= 32
    assert cache.get("/files/0.mkv", 0, 0) is not None
    assert cache.get("/files/39.mkv", 39, 39) is not None
