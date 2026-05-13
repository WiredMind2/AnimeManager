"""Tests for `shared.telemetry.TelemetryCollector`."""

from __future__ import annotations

import threading
import time

from ....shared.telemetry import TelemetryCollector, get_telemetry, reset_telemetry


def test_counter_increments():
    c = TelemetryCollector()
    c.increment("hits")
    c.increment("hits", 4)
    snap = c.snapshot()
    assert snap["counters"]["hits"] == 5


def test_gauge_set():
    c = TelemetryCollector()
    c.set_gauge("queue.depth", 12)
    assert c.snapshot()["gauges"]["queue.depth"] == 12


def test_record_ms_produces_percentiles():
    c = TelemetryCollector()
    for v in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10):
        c.record_ms("latency", v)
    snap = c.snapshot()["timers"]["latency"]
    assert snap["count"] == 10
    assert snap["min"] == 1
    assert snap["max"] == 10
    assert snap["p50"] == 6  # index 5 of sorted 1..10


def test_time_context_manager():
    c = TelemetryCollector()
    with c.time("op"):
        time.sleep(0.01)
    snap = c.snapshot()["timers"]["op"]
    assert snap["count"] == 1
    assert snap["max"] >= 5  # 10ms but allow slack


def test_default_collector_is_singleton():
    a = get_telemetry()
    b = get_telemetry()
    assert a is b
    reset_telemetry()
    snap = get_telemetry().snapshot()
    assert snap == {"counters": {}, "gauges": {}, "timers": {}}


def test_thread_safety():
    c = TelemetryCollector(sample_capacity=2048)
    n_threads = 4
    n_ticks = 250

    def worker():
        for _ in range(n_ticks):
            c.increment("x")
            c.record_ms("op", 1.0)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    snap = c.snapshot()
    assert snap["counters"]["x"] == n_threads * n_ticks
    assert snap["timers"]["op"]["count"] == min(n_threads * n_ticks, 2048)


def test_reset_clears_state():
    c = TelemetryCollector()
    c.increment("k")
    c.record_ms("op", 1.0)
    c.set_gauge("g", 1.0)
    c.reset()
    snap = c.snapshot()
    assert snap == {"counters": {}, "gauges": {}, "timers": {}}
