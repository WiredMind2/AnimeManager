"""Additional edge case tests for ``adapters.persistence.queue.PersistenceQueue``."""

from __future__ import annotations

import threading
import time

import pytest

from adapters.persistence.queue import PersistenceQueue


def _build(received, **kwargs):
    def flush(batch):
        received.append(list(batch))

    kwargs.setdefault("batch_size", 5)
    kwargs.setdefault("max_latency_ms", 50)
    kwargs.setdefault("queue_maxsize", 100)
    return PersistenceQueue(flush, **kwargs)


class TestConstructionEdges:
    @pytest.mark.parametrize("bad", [-1, -100])
    def test_negative_batch_size_rejected(self, bad):
        with pytest.raises(ValueError):
            PersistenceQueue(lambda b: None, batch_size=bad)

    @pytest.mark.parametrize("bad", [-1, -100])
    def test_negative_latency_rejected(self, bad):
        with pytest.raises(ValueError):
            PersistenceQueue(lambda b: None, max_latency_ms=bad)

    def test_zero_queue_maxsize_treated_as_unbounded(self):
        # queue.Queue with maxsize=0 is unbounded.
        received = []
        pq = _build(received, queue_maxsize=0, batch_size=1, max_latency_ms=10)
        for i in range(10):
            assert pq.put(i) is True


class TestStartStopIdempotence:
    def test_double_start_is_no_op(self):
        received = []
        pq = _build(received)
        pq.start()
        pq.start()  # should not raise
        pq.stop(timeout=2)

    def test_stop_without_start_is_no_op(self):
        received = []
        pq = _build(received)
        pq.stop()  # must not raise

    def test_stop_drains_remaining(self):
        received = []
        pq = _build(received, batch_size=1000, max_latency_ms=1000)
        pq.start()
        for i in range(5):
            pq.put(i, block=True)
        pq.stop(timeout=2)
        flat = sorted(item for batch in received for item in batch)
        assert flat == [0, 1, 2, 3, 4]

    def test_stop_without_drain_skips_join(self):
        received = []
        pq = _build(received, batch_size=1000, max_latency_ms=10_000)
        pq.start()
        pq.put(1, block=True)
        pq.stop(drain=False, timeout=0.01)
        pq.stop()  # idempotent after worker handle cleared


class TestFlushNow:
    def test_flush_now_on_empty_does_nothing(self):
        received = []
        pq = _build(received)
        pq.flush_now()
        assert received == []

    def test_flush_now_does_not_break_subsequent_use(self):
        received = []
        pq = _build(received, batch_size=100, max_latency_ms=10_000)
        pq.put("a")
        pq.flush_now()
        pq.put("b")
        pq.flush_now()
        flat = [item for batch in received for item in batch]
        assert flat == ["a", "b"]


class TestStats:
    def test_pending_grows_until_flush(self):
        received = []
        pq = _build(received, batch_size=10, max_latency_ms=10_000)
        for i in range(3):
            pq.put(i)
        stats = pq.stats()
        assert stats["pending"] == 3
        assert stats["processed"] == 0
        pq.flush_now()
        stats = pq.stats()
        assert stats["pending"] == 0
        assert stats["processed"] == 3

    def test_dropped_counter_increments(self):
        received = []
        pq = _build(received, queue_maxsize=2, batch_size=100, max_latency_ms=10_000)
        assert pq.put("a") is True
        assert pq.put("b") is True
        # next three put attempts should all be dropped
        for _ in range(3):
            assert pq.put("x") is False
        stats = pq.stats()
        assert stats["dropped"] == 3


class TestConcurrency:
    def test_many_producers_no_data_loss(self):
        received = []
        flush_lock = threading.Lock()

        def flush(batch):
            with flush_lock:
                received.extend(batch)

        pq = PersistenceQueue(
            flush,
            batch_size=10,
            max_latency_ms=20,
            queue_maxsize=10_000,
        )
        pq.start()
        try:
            producers = []
            for tid in range(4):
                def worker(tid=tid):
                    for i in range(50):
                        pq.put((tid, i), block=True)

                t = threading.Thread(target=worker)
                t.start()
                producers.append(t)

            for t in producers:
                t.join()
        finally:
            pq.stop(timeout=2)

        assert len(received) == 200

    def test_flush_callable_exception_continues_until_stop(self):
        attempts = []

        def flush(batch):
            attempts.append(list(batch))
            raise RuntimeError("always fail")

        pq = PersistenceQueue(flush, batch_size=1, max_latency_ms=20)
        pq.start()
        try:
            for i in range(3):
                pq.put(i, block=True)
            time.sleep(0.3)
        finally:
            pq.stop(timeout=2)

        # Worker stays alive despite repeated exceptions.
        assert len(attempts) >= 3


class TestFlushNowWithRunningWorker:
    def test_can_combine_flush_now_and_background_worker(self):
        received = []
        pq = _build(received, batch_size=100, max_latency_ms=10_000)
        pq.start()
        try:
            pq.put("a", block=True)
            time.sleep(0.02)
            pq.flush_now()
            pq.put("b", block=True)
        finally:
            pq.stop(timeout=2)

        flat = [item for batch in received for item in batch]
        assert sorted(flat) == ["a", "b"]
