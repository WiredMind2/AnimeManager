"""Edge case tests for ``shared.telemetry.TelemetryCollector`` and singletons."""

from __future__ import annotations

import threading

import pytest

from shared.telemetry import TelemetryCollector, get_telemetry, reset_telemetry


class TestCollectorEdges:
    def test_increment_with_zero(self):
        c = TelemetryCollector()
        c.increment("x", 0)
        assert c.snapshot()["counters"]["x"] == 0

    def test_increment_with_negative_value(self):
        c = TelemetryCollector()
        c.increment("x", 5)
        c.increment("x", -3)
        assert c.snapshot()["counters"]["x"] == 2

    def test_record_ms_zero_value(self):
        c = TelemetryCollector()
        c.record_ms("op", 0.0)
        snap = c.snapshot()["timers"]["op"]
        assert snap["count"] == 1
        assert snap["min"] == 0.0
        assert snap["max"] == 0.0

    def test_record_ms_with_very_large_values(self):
        c = TelemetryCollector()
        big = 1e9
        c.record_ms("op", big)
        snap = c.snapshot()["timers"]["op"]
        assert snap["max"] == big

    def test_sample_capacity_is_bounded(self):
        c = TelemetryCollector(sample_capacity=4)
        for i in range(10):
            c.record_ms("x", float(i))
        snap = c.snapshot()["timers"]["x"]
        # The deque drops oldest entries past the capacity.
        assert snap["count"] == 4
        # min must be among the last 4 inserted -> 6..9, so >= 6
        assert snap["min"] >= 6.0

    def test_unknown_timer_not_in_snapshot(self):
        c = TelemetryCollector()
        snap = c.snapshot()
        assert snap["timers"] == {}

    def test_snapshot_skips_timer_buckets_with_no_samples(self):
        c = TelemetryCollector()
        with c._lock:
            # Touching the defaultdict allocates an empty deque with no samples.
            _ = c._timers["never_recorded"]
        snap = c.snapshot()
        assert "never_recorded" not in snap["timers"]

    def test_set_gauge_overwrites(self):
        c = TelemetryCollector()
        c.set_gauge("g", 1)
        c.set_gauge("g", 99)
        assert c.snapshot()["gauges"]["g"] == 99.0

    def test_snapshot_returns_independent_copy(self):
        c = TelemetryCollector()
        c.increment("x")
        snap = c.snapshot()
        snap["counters"]["x"] = 99
        # Internal state must not have been mutated.
        assert c.snapshot()["counters"]["x"] == 1

    def test_time_context_records_even_on_exception(self):
        c = TelemetryCollector()
        with pytest.raises(RuntimeError):
            with c.time("op"):
                raise RuntimeError("boom")
        snap = c.snapshot()["timers"]
        assert "op" in snap
        assert snap["op"]["count"] == 1

    def test_thread_safety_of_gauges(self):
        c = TelemetryCollector()

        def worker():
            for i in range(200):
                c.set_gauge("g", i)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # No exception means the lock prevented races; final value is whatever
        # came last.
        snap = c.snapshot()["gauges"]
        assert 0 <= snap["g"] < 200

    def test_record_ms_str_coerced_to_float(self):
        c = TelemetryCollector()
        c.record_ms("op", "5.5")  # type: ignore[arg-type]
        snap = c.snapshot()["timers"]["op"]
        assert snap["count"] == 1
        assert snap["min"] == 5.5

    def test_record_ms_invalid_raises(self):
        c = TelemetryCollector()
        with pytest.raises(ValueError):
            c.record_ms("op", "not a number")  # type: ignore[arg-type]

    def test_increment_invalid_value_raises(self):
        c = TelemetryCollector()
        with pytest.raises((ValueError, TypeError)):
            c.increment("x", "five")  # type: ignore[arg-type]


class TestSingleton:
    def test_idempotent_reset(self):
        reset_telemetry()
        reset_telemetry()
        snap = get_telemetry().snapshot()
        assert snap == {"counters": {}, "gauges": {}, "timers": {}}

    def test_get_telemetry_returns_same_instance(self):
        a = get_telemetry()
        b = get_telemetry()
        assert a is b
