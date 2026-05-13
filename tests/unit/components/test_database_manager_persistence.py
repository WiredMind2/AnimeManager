"""Tests for `DatabaseManager.enable_batched_writes` and `enqueue_anime`."""

from __future__ import annotations

import time

from ....application.services.database_manager import DatabaseManager


class _StubAnime:
    def __init__(self, rid):
        self.id = rid


class _StubDatabase:
    """Pretends to be a `BaseDB` instance with just enough surface for the tests.

    Mirrors the real ``BaseDB`` contract: ``save()`` takes no arguments
    (it's the transaction-commit hook) and persistence flows through
    ``set(id, data, table, save=...)``.
    """

    USE_CONNECTION_POOL = False

    def __init__(self):
        self.saved = []
        self.commit_count = 0
        self._lock = _NopLock()

    def get_lock(self):
        return self._lock

    def save(self):
        self.commit_count += 1

    def set(self, id, data, table, save=True):
        self.saved.append(id)
        if save:
            self.save()

    def is_initialized(self):
        return True

    def close(self):
        pass


class _NopLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _silent_logger(*_args, **_kwargs):
    return None


def test_synchronous_upsert_when_queue_disabled():
    mgr = DatabaseManager()
    mgr.log = _silent_logger
    db = _StubDatabase()
    mgr.set_database(db)

    mgr.enqueue_anime(_StubAnime(1))
    assert db.saved == [1]


def test_batched_writes_flush_records():
    mgr = DatabaseManager()
    mgr.log = _silent_logger
    db = _StubDatabase()
    mgr.set_database(db)
    mgr.enable_batched_writes(batch_size=2, max_latency_ms=50)
    try:
        mgr.enqueue_anime(_StubAnime(1))
        mgr.enqueue_anime(_StubAnime(2))
        mgr.enqueue_anime(_StubAnime(3))
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if len(db.saved) >= 3:
                break
            time.sleep(0.01)
    finally:
        mgr.close()

    assert sorted(db.saved) == [1, 2, 3]


def test_write_queue_stats_reports_pending():
    mgr = DatabaseManager()
    mgr.log = _silent_logger
    db = _StubDatabase()
    mgr.set_database(db)
    mgr.enable_batched_writes(batch_size=100, max_latency_ms=5_000)
    try:
        mgr.enqueue_anime(_StubAnime(1))
        # Stats should show at least our enqueue accounted for.
        stats = mgr.write_queue_stats()
        assert "processed" in stats
        assert "pending" in stats
    finally:
        mgr.close()


def test_telemetry_records_upsert_metrics():
    mgr = DatabaseManager()
    mgr.log = _silent_logger
    db = _StubDatabase()
    mgr.set_database(db)

    mgr.upsert_anime_batch([_StubAnime(1), _StubAnime(2)])

    snap = mgr._telemetry.snapshot()
    assert snap["counters"].get("db.upserts_committed", 0) >= 2
    assert "db.upsert_anime_batch_ms" in snap["timers"]
