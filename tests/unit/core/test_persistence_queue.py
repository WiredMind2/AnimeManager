"""Tests for `adapters.persistence.queue.PersistenceQueue` batching behavior."""

from __future__ import annotations

import threading
import time

import pytest

from ....adapters.persistence.queue import PersistenceQueue


def _make_queue(received: list, *, batch_size=3, max_latency_ms=100, maxsize=100):
    def flush(batch):
        received.append(list(batch))

    return PersistenceQueue(
        flush,
        batch_size=batch_size,
        max_latency_ms=max_latency_ms,
        queue_maxsize=maxsize,
    )


def test_batches_by_size():
    received = []
    pq = _make_queue(received, batch_size=3)
    pq.start()
    try:
        for i in range(6):
            pq.put(i, block=True)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if sum(len(b) for b in received) >= 6:
                break
            time.sleep(0.01)
    finally:
        pq.stop()

    flat = [item for batch in received for item in batch]
    assert sorted(flat) == list(range(6))
    # at least one batch must be >= batch_size
    assert any(len(batch) >= 3 for batch in received)


def test_drains_on_stop():
    received = []
    pq = _make_queue(received, batch_size=100, max_latency_ms=10_000)
    pq.start()
    pq.put("a", block=True)
    pq.put("b", block=True)
    pq.stop(timeout=2)
    flat = [item for batch in received for item in batch]
    assert sorted(flat) == ["a", "b"]


def test_drops_on_full_queue_without_blocking():
    received = []
    pq = _make_queue(received, batch_size=100, max_latency_ms=10_000, maxsize=2)
    # Don't start the worker, so the queue fills.
    assert pq.put("x") is True
    assert pq.put("y") is True
    assert pq.put("z") is False
    stats = pq.stats()
    assert stats["dropped"] == 1
    assert stats["pending"] == 2


def test_flush_callable_exception_does_not_kill_worker():
    raised = threading.Event()
    received = []

    def flush(batch):
        if not raised.is_set():
            raised.set()
            raise RuntimeError("boom")
        received.append(list(batch))

    pq = PersistenceQueue(flush, batch_size=1, max_latency_ms=50, queue_maxsize=10)
    pq.start()
    try:
        pq.put("first", block=True)
        pq.put("second", block=True)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if received:
                break
            time.sleep(0.01)
    finally:
        pq.stop(timeout=2)

    assert raised.is_set()
    assert any("second" in batch for batch in received)


def test_invalid_construction_raises():
    with pytest.raises(ValueError):
        PersistenceQueue(lambda b: None, batch_size=0)
    with pytest.raises(ValueError):
        PersistenceQueue(lambda b: None, max_latency_ms=0)


def test_flush_now_drains_synchronously():
    received = []
    pq = _make_queue(received, batch_size=100, max_latency_ms=10_000)
    pq.put("a", block=True)
    pq.put("b", block=True)
    pq.flush_now()
    flat = [item for batch in received for item in batch]
    assert sorted(flat) == ["a", "b"]
