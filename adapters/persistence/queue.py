"""
Bounded, batching persistence queue used by the ingestion pipeline.

The queue accepts arbitrary callables; it drains them on a background
worker, grouping items into batches sized by `batch_size` or by
`max_latency_ms`. This eliminates the per-record fan-out from the legacy
streaming ItemList and gives a single, observable place to instrument DB
write throughput.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable, List, Optional


class PersistenceQueue:
    """A producer/consumer queue that flushes records in batches."""

    def __init__(
        self,
        flush_callable: Callable[[List[Any]], None],
        *,
        batch_size: int = 25,
        max_latency_ms: int = 250,
        queue_maxsize: int = 5000,
        worker_name: str = "PersistenceQueue",
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if max_latency_ms <= 0:
            raise ValueError("max_latency_ms must be positive")
        self._flush = flush_callable
        self._batch_size = batch_size
        self._max_latency = max_latency_ms / 1000.0
        self._queue: "queue.Queue[Any]" = queue.Queue(maxsize=queue_maxsize)
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._worker_name = worker_name
        self._dropped = 0
        self._processed = 0
        self._stats_lock = threading.Lock()

    def start(self) -> None:
        if self._worker is not None:
            return
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._run, name=self._worker_name, daemon=True)
        self._worker.start()

    def stop(self, drain: bool = True, timeout: float = 5.0) -> None:
        self._stop_event.set()
        worker = self._worker
        self._worker = None
        if worker is None:
            return
        if drain:
            worker.join(timeout=timeout)
        else:
            # Best-effort: leave the worker to die when its loop tick wakes up.
            pass

    def put(self, record: Any, *, block: bool = False) -> bool:
        """Enqueue a record; returns True if accepted, False if dropped."""
        try:
            self._queue.put(record, block=block)
            return True
        except queue.Full:
            with self._stats_lock:
                self._dropped += 1
            return False

    def stats(self) -> dict:
        with self._stats_lock:
            return {
                "processed": self._processed,
                "dropped": self._dropped,
                "pending": self._queue.qsize(),
            }

    def flush_now(self) -> None:
        """Synchronously drain everything currently queued."""
        batch: List[Any] = []
        while True:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if batch:
            self._safe_flush(batch)

    def _run(self) -> None:
        batch: List[Any] = []
        batch_deadline: Optional[float] = None
        while not self._stop_event.is_set():
            timeout = self._max_latency if batch else 0.25
            try:
                record = self._queue.get(timeout=timeout)
            except queue.Empty:
                record = None

            now = time.monotonic()
            if record is not None:
                if not batch:
                    batch_deadline = now + self._max_latency
                batch.append(record)

            should_flush = False
            if batch and len(batch) >= self._batch_size:
                should_flush = True
            elif batch and batch_deadline is not None and now >= batch_deadline:
                should_flush = True

            if should_flush:
                self._safe_flush(batch)
                batch = []
                batch_deadline = None

        if batch:
            self._safe_flush(batch)
        while True:
            try:
                self._safe_flush([self._queue.get_nowait()])
            except queue.Empty:
                break

    def _safe_flush(self, batch: List[Any]) -> None:
        try:
            self._flush(batch)
        except Exception:
            # Flush callables must own their error logging; we never let the
            # worker thread die because of a single bad batch.
            pass
        finally:
            with self._stats_lock:
                self._processed += len(batch)
