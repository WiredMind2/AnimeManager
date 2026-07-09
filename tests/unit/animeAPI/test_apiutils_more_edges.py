"""Additional edge case tests for ``adapters.api.APIUtils``.

Covers:
- ``EnhancedSession`` cache wiring (no network calls; the session is patched).
- ``DummyDB`` SQL routing.
- ``APIUtils.handle_sql_queue`` and ``reroute_sql_queue`` lifecycle.
- ``cached_request`` deferral.
"""

from __future__ import annotations

import queue
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from adapters.api.APIUtils import (
    APICache,
    DummyDB,
    EnhancedSession,
    cached_api_request,
    cached_request,
)


# ---------------------------------------------------------------------------
# EnhancedSession cache wiring
# ---------------------------------------------------------------------------


class TestEnhancedSession:
    def test_default_timeout_set(self):
        s = EnhancedSession()
        assert s.timeout == (3.05, 4)

    def test_custom_timeout(self):
        s = EnhancedSession(timeout=10)
        assert s.timeout == 10

    def test_no_cache_skips_lookup(self):
        s = EnhancedSession()
        with patch("requests.Session.request") as base:
            base.return_value = SimpleNamespace(status_code=200)
            s.request("GET", "http://x")
            base.assert_called_once()

    def test_get_cache_hit_short_circuits(self):
        cache = APICache()
        cached = SimpleNamespace(status_code=200)
        cache.set("http://x", cached, method="GET")
        s = EnhancedSession(api_cache=cache)
        with patch("requests.Session.request") as base:
            r = s.request("GET", "http://x")
            base.assert_not_called()
        assert r is cached

    def test_get_cache_miss_makes_request(self):
        cache = APICache()
        s = EnhancedSession(api_cache=cache)
        with patch("requests.Session.request") as base:
            base.return_value = SimpleNamespace(status_code=200)
            r = s.request("GET", "http://x")
            base.assert_called_once()
        # After the request, status 200 caches it.
        assert cache.get("http://x", method="GET") is not None

    def test_non_get_does_not_cache(self):
        cache = APICache()
        s = EnhancedSession(api_cache=cache)
        with patch("requests.Session.request") as base:
            base.return_value = SimpleNamespace(status_code=200)
            s.request("POST", "http://x")
        # POST not cached.
        assert cache.get("http://x", method="POST") is None

    def test_non_200_get_not_cached(self):
        cache = APICache()
        s = EnhancedSession(api_cache=cache)
        with patch("requests.Session.request") as base:
            base.return_value = SimpleNamespace(status_code=500)
            s.request("GET", "http://x")
        assert cache.get("http://x", method="GET") is None

    def test_timeout_added_to_kwargs(self):
        s = EnhancedSession(timeout=7)
        with patch("requests.Session.request") as base:
            base.return_value = SimpleNamespace(status_code=200)
            s.request("GET", "http://x")
            assert base.call_args.kwargs["timeout"] == 7

    def test_timeout_preserves_caller_value(self):
        s = EnhancedSession(timeout=7)
        with patch("requests.Session.request") as base:
            base.return_value = SimpleNamespace(status_code=200)
            s.request("GET", "http://x", timeout=99)
            assert base.call_args.kwargs["timeout"] == 99

    def test_method_case_only_checked_for_branch_not_cache_key(self):
        """Documents a quirk: ``method.upper() == 'GET'`` controls the cache
        branch, but ``cache.get`` is called with the original case which
        means ``"get"`` and ``"GET"`` produce distinct cache keys.
        """
        cache = APICache()
        cached = SimpleNamespace(status_code=200)
        cache.set("http://x", cached, method="GET")
        s = EnhancedSession(api_cache=cache)
        with patch("requests.Session.request") as base:
            base.return_value = SimpleNamespace(status_code=200)
            s.request("get", "http://x")
            # Cache lookup miss because keys are case-sensitive.
            base.assert_called_once()


# ---------------------------------------------------------------------------
# DummyDB
# ---------------------------------------------------------------------------


class TestDummyDB:
    def test_select_passes_through(self):
        real = MagicMock()
        real.sql.return_value = [(1,)]
        d = DummyDB(real)
        result = d.sql("SELECT * FROM t", (1, 2))
        assert result == [(1,)]
        real.sql.assert_called_once()

    def test_non_select_caches(self):
        real = MagicMock()
        d = DummyDB(real)
        d.sql("INSERT INTO t VALUES (?)", (1,))
        real.sql.assert_not_called()
        assert len(d.cache) == 1
        assert d.cache[0][0] == "sql"

    def test_unknown_method_goes_to_cache(self):
        real = MagicMock()
        d = DummyDB(real)
        d.do_something(1, 2, k="v")
        assert d.cache[0][0] == "do_something"

    def test_getid_routes_to_real_db(self):
        # Use a class instead of MagicMock because __getattribute__ on
        # MagicMock doesn't auto-create attributes.
        class _Real:
            def getId(self, x):
                self.last = x
                return 7

        real = _Real()
        d = DummyDB(real)
        assert d.getId(1) == 7

    def test_get_lock_routes_to_real_db(self):
        class _Real:
            def get_lock(self):
                self.called = True
                return "lock"

        real = _Real()
        d = DummyDB(real)
        assert d.get_lock() == "lock"

    def test_save_is_noop(self):
        real = MagicMock()
        d = DummyDB(real)
        # save returns a lambda that does nothing
        result = d.save("x")
        assert result is None
        real.save.assert_not_called()


# ---------------------------------------------------------------------------
# cached_request decorator
# ---------------------------------------------------------------------------


class TestCachedRequestDecorator:
    def test_invokes_when_defer_disabled(self):
        called = []

        @cached_request
        def example(self, x):
            called.append(x)
            return x

        obj = SimpleNamespace(defer_writes=False, queue=queue.Queue())
        assert example(obj, 5) == 5
        assert called == [5]

    def test_defers_to_queue_when_enabled(self):
        called = []

        @cached_request
        def example(self, x):
            called.append(x)
            return x

        obj = SimpleNamespace(defer_writes=True, queue=queue.Queue())
        result = example(obj, 5)
        assert result is None
        assert called == []
        assert obj.queue.qsize() == 1

    def test_missing_defer_writes_attr_calls_func(self):
        called = []

        @cached_request
        def example(self, x):
            called.append(x)
            return x

        # No defer_writes attribute set; getattr returns False default.
        obj = SimpleNamespace(queue=queue.Queue())
        assert example(obj, 5) == 5
        assert called == [5]

    def test_schedule_light_skips_cached_request(self):
        called = []

        @cached_request
        def example(self, x):
            called.append(x)
            return x

        obj = SimpleNamespace(schedule_light=True, defer_writes=False, queue=queue.Queue())
        assert example(obj, 5) is None
        assert called == []


# ---------------------------------------------------------------------------
# APIUtils queue handling
# ---------------------------------------------------------------------------


class TestAPIUtilsQueue:
    def test_handle_sql_queue_executes_all_items(self):
        from adapters.api.APIUtils import APIUtils

        u = object.__new__(APIUtils)
        u.queue = queue.Queue()
        results = []

        def func(a, b, c=None):
            results.append((a, b, c))

        u.queue.put((func, (1, 2), {"c": 3}))
        u.queue.put((func, (4, 5), {"c": 6}))

        lock = MagicMock()
        lock.__enter__ = lambda self: self
        lock.__exit__ = lambda *a: False
        u.database = MagicMock()
        u.database.get_lock.return_value = lock

        u.handle_sql_queue()
        assert results == [(1, 2, 3), (4, 5, 6)]
        assert u.queue.empty()

    def test_reroute_sql_queue_moves_items(self):
        from adapters.api.APIUtils import APIUtils

        u = object.__new__(APIUtils)
        u.queue = queue.Queue()
        u.queue.put("a")
        u.queue.put("b")
        new_q = queue.Queue()

        u.reroute_sql_queue(new_q)
        assert u.queue is new_q
        items = []
        while not new_q.empty():
            items.append(new_q.get())
        assert items == ["a", "b"]


# ---------------------------------------------------------------------------
# cached_api_request decorator: explicit none-return path
# ---------------------------------------------------------------------------


class TestCachedAPIRequestNoneReturn:
    def test_none_result_is_not_cached(self):
        class _Stub:
            api_cache = APICache()
            calls = 0

            @cached_api_request(ttl=60)
            def fetch(self, arg):
                self.calls += 1
                return None

        s = _Stub()
        s.fetch("k")
        s.fetch("k")
        # None is never cached so the function is called twice.
        assert s.calls == 2
