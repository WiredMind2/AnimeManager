"""
Lightweight in-process telemetry used by the pipeline.

The collector is deliberately dependency-free so it can be exercised in
unit tests and threaded code without external services. Production
deployments may forward snapshots to logging / metrics backends.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import Deque, Dict, Iterator, Optional


__all__ = [
    "TelemetryCollector",
    "get_telemetry",
    "reset_telemetry",
]


class TelemetryCollector:
    """Counter + histogram store with hard caps to bound memory usage."""

    def __init__(self, sample_capacity: int = 512):
        self._lock = threading.RLock()
        self._counters: Dict[str, int] = defaultdict(int)
        self._timers: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=sample_capacity))
        self._gauges: Dict[str, float] = {}
        self._sample_capacity = sample_capacity

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += int(value)

    def record_ms(self, name: str, value_ms: float) -> None:
        with self._lock:
            self._timers[name].append(float(value_ms))

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = float(value)

    @contextmanager
    def time(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self.record_ms(name, (time.perf_counter() - start) * 1000.0)

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            timers: Dict[str, Dict[str, float]] = {}
            for name, samples in self._timers.items():
                if not samples:
                    continue
                ordered = sorted(samples)
                count = len(ordered)
                timers[name] = {
                    "count": float(count),
                    "min": ordered[0],
                    "p50": ordered[count // 2],
                    "p95": ordered[min(count - 1, int(count * 0.95))],
                    "max": ordered[-1],
                    "avg": sum(ordered) / count,
                }
        return {"counters": counters, "gauges": gauges, "timers": timers}

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._timers.clear()
            self._gauges.clear()


_default_collector: Optional[TelemetryCollector] = None
_default_lock = threading.Lock()


def get_telemetry() -> TelemetryCollector:
    """Return the process-wide telemetry collector."""
    global _default_collector
    if _default_collector is None:
        with _default_lock:
            if _default_collector is None:
                _default_collector = TelemetryCollector()
    return _default_collector


def reset_telemetry() -> None:
    """Reset the default telemetry collector. Test-only helper."""
    if _default_collector is not None:
        _default_collector.reset()
