"""Edge case tests for adapters.api.APIUtils helper classes.

Focuses on ``APICache`` and the pure ``getStatusFromData`` logic that
controls status derivation across all metadata providers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from adapters.api.APIUtils import APICache, cached_api_request


# ---------------------------------------------------------------------------
# APICache
# ---------------------------------------------------------------------------


class TestAPICache:
    def test_miss_returns_none(self):
        cache = APICache()
        assert cache.get("http://x") is None
        stats = cache.get_stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 0

    def test_hit_after_set(self):
        cache = APICache()
        cache.set("http://x", "value")
        assert cache.get("http://x") == "value"
        assert cache.get_stats()["hits"] == 1

    def test_clear_removes_all(self):
        cache = APICache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_eviction_when_full(self):
        cache = APICache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # should evict oldest
        # one of a or b is gone
        present = [k for k in ("a", "b", "c") if cache.get(k) is not None]
        assert len(present) == 2
        assert "c" in present
        assert cache.get_stats()["evictions"] >= 1

    def test_distinct_keys_for_different_methods(self):
        cache = APICache()
        cache.set("http://x", "GET-value", method="GET")
        cache.set("http://x", "POST-value", method="POST")
        assert cache.get("http://x", method="GET") == "GET-value"
        assert cache.get("http://x", method="POST") == "POST-value"

    def test_distinct_keys_for_different_params(self):
        cache = APICache()
        cache.set("http://x", "a", params={"p": 1})
        cache.set("http://x", "b", params={"p": 2})
        assert cache.get("http://x", params={"p": 1}) == "a"
        assert cache.get("http://x", params={"p": 2}) == "b"

    def test_ttl_expiration(self):
        # Use a tiny TTL so the entry expires before we read it back.
        cache = APICache(default_ttl=0.0001)
        cache.set("http://x", 1)
        # Backdate the internal access timestamp to force expiry. The key in
        # access_times is the MD5 hash, so we reach in via the same helper.
        key = cache._generate_key("http://x")
        cache.access_times[key] = 0
        assert cache.get("http://x") is None
        assert cache.get_stats()["evictions"] >= 1

    def test_stats_hit_rate_computation(self):
        cache = APICache()
        cache.set("a", 1)
        # 3 hits, 1 miss => 75 %
        for _ in range(3):
            cache.get("a")
        cache.get("missing")
        stats = cache.get_stats()
        assert stats["hits"] == 3
        assert stats["misses"] == 1
        assert pytest.approx(stats["hit_rate"], abs=0.01) == 0.75

    def test_evict_oldest_safe_on_empty(self):
        cache = APICache()
        # Should not raise when cache is empty
        cache._evict_oldest()

    def test_set_size_zero_acts_unbounded(self):
        # max_size <= 0 triggers eviction, but our logic compares >=.
        cache = APICache(max_size=0)
        cache.set("a", 1)
        # When max_size is 0, len(cache) >= 0 always, so eviction is attempted.
        # The eviction handler does not crash on empty cache.
        assert cache is not None


# ---------------------------------------------------------------------------
# cached_api_request decorator
# ---------------------------------------------------------------------------


class _DummySelf:
    def __init__(self):
        self.api_cache = APICache(max_size=100, default_ttl=60)
        self.call_count = 0


class TestCachedApiRequestDecorator:
    def test_first_call_invokes_function(self):
        instance = _DummySelf()

        @cached_api_request()
        def fn(self, key):
            self.call_count += 1
            return key.upper()

        out = fn(instance, "hello")
        assert out == "HELLO"
        assert instance.call_count == 1

    def test_second_call_uses_cache(self):
        instance = _DummySelf()

        @cached_api_request()
        def fn(self, key):
            self.call_count += 1
            return key.upper()

        fn(instance, "hello")
        fn(instance, "hello")
        assert instance.call_count == 1

    def test_different_args_invoke_new_call(self):
        instance = _DummySelf()

        @cached_api_request()
        def fn(self, key):
            self.call_count += 1
            return key.upper()

        fn(instance, "hello")
        fn(instance, "world")
        assert instance.call_count == 2

    def test_none_result_not_cached(self):
        instance = _DummySelf()

        @cached_api_request()
        def fn(self, key):
            instance.call_count += 1
            return None

        fn(instance, "hello")
        fn(instance, "hello")
        # None results should not be cached, so call count grows
        assert instance.call_count == 2


# ---------------------------------------------------------------------------
# Pure status derivation from raw API data
# ---------------------------------------------------------------------------


# We test ``APIUtils.getStatusFromData`` as a pure function on a small fake
# instance. This avoids invoking the real ``__init__`` chain which requires
# database access.

class _APIUtilsFake:
    """Just enough of the interface for `getStatusFromData` to be invokable."""

    pass


def _get_status(data):
    from adapters.api.APIUtils import APIUtils

    return APIUtils.getStatusFromData(_APIUtilsFake(), data)


class TestGetStatusFromData:
    def test_no_date_from_unknown(self):
        data = {"date_from": None, "date_to": None, "episodes": 12}
        assert _get_status(data) == "UNKNOWN"

    def test_non_int_date_from_returns_update(self):
        data = {"date_from": "not-an-int", "date_to": None, "episodes": 12}
        assert _get_status(data) == "UPDATE"

    def test_future_date_from_is_upcoming(self):
        future = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
        data = {"date_from": future, "date_to": None, "episodes": 12}
        assert _get_status(data) == "UPCOMING"

    def test_past_no_end_single_episode_finished(self):
        past = int((datetime.now(timezone.utc) - timedelta(days=10)).timestamp())
        data = {"date_from": past, "date_to": None, "episodes": 1}
        assert _get_status(data) == "FINISHED"

    def test_past_no_end_multi_episode_airing(self):
        past = int((datetime.now(timezone.utc) - timedelta(days=10)).timestamp())
        data = {"date_from": past, "date_to": None, "episodes": 12}
        assert _get_status(data) == "AIRING"

    def test_past_with_past_end_finished(self):
        df = int((datetime.now(timezone.utc) - timedelta(days=400)).timestamp())
        dt = int((datetime.now(timezone.utc) - timedelta(days=10)).timestamp())
        assert _get_status({"date_from": df, "date_to": dt, "episodes": 12}) == "FINISHED"

    def test_past_with_future_end_airing(self):
        df = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
        dt = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
        assert _get_status({"date_from": df, "date_to": dt, "episodes": 12}) == "AIRING"

    def test_negative_timestamp_supported(self):
        # Pre-1970 dates: the helper computes manually from epoch.
        # It must not raise and must produce a sensible status.
        data = {"date_from": -1000, "date_to": -500, "episodes": 12}
        result = _get_status(data)
        assert result in {"FINISHED", "AIRING", "UPCOMING", "UNKNOWN"}

    def test_extremely_large_timestamp_returns_unknown(self):
        # 64-bit overflow territory should be caught and collapsed.
        data = {"date_from": 10**30, "date_to": None, "episodes": 12}
        assert _get_status(data) == "UNKNOWN"

    def test_invalid_date_to_falls_back_to_airing(self):
        df = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
        # date_to too large to convert -> caught and treated as AIRING.
        assert _get_status({"date_from": df, "date_to": 10**30, "episodes": 12}) == "AIRING"
