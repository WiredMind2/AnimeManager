"""Unit tests for provider health / circuit-breaker tracking."""

from __future__ import annotations

import pytest

from application.services.provider_health import ProviderHealthTracker


@pytest.mark.unit
@pytest.mark.stability_gate
def test_provider_recovers_after_quarantine_expires():
    tracker = ProviderHealthTracker(failure_threshold=2, quarantine_seconds=0.01)
    tracker.record_failure("JikanMoeWrapper")
    tracker.record_failure("JikanMoeWrapper")
    assert not tracker.is_available("JikanMoeWrapper")
    import time

    time.sleep(0.02)
    assert tracker.is_available("JikanMoeWrapper")


@pytest.mark.unit
@pytest.mark.stability_gate
def test_success_resets_failure_counter():
    tracker = ProviderHealthTracker(failure_threshold=3)
    tracker.record_failure("AnilistCoWrapper")
    tracker.record_failure("AnilistCoWrapper")
    tracker.record_success("AnilistCoWrapper")
    assert tracker.is_available("AnilistCoWrapper")
    snap = tracker.snapshot()["AnilistCoWrapper"]
    assert snap["consecutive_failures"] == 0


@pytest.mark.unit
@pytest.mark.stability_gate
def test_quarantined_names_lists_active_quarantine():
    tracker = ProviderHealthTracker(failure_threshold=1, quarantine_seconds=60.0)
    tracker.record_failure("KitsuIoWrapper")
    assert "KitsuIoWrapper" in tracker.quarantined_names()
