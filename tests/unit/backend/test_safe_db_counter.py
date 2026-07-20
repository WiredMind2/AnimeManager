"""Tests for safe_db_counter helper."""

from __future__ import annotations

from application.services.database_manager import DatabaseManager, safe_db_counter


class _ProxyDB:
    """Mimics thread_safe_db: missing attrs become callables."""

    def __getattr__(self, name):
        return lambda *a, **k: f"proxied:{name}"


def test_safe_db_counter_returns_zero_for_proxy_getattr():
    assert safe_db_counter(_ProxyDB(), "_commit_count") == 0
    assert safe_db_counter(_ProxyDB(), "_query_count") == 0


def test_safe_db_counter_reads_real_instance_attrs():
    db = type("DB", (), {})()
    db._commit_count = 7
    db._query_count = 3
    assert safe_db_counter(db, "_commit_count") == 7
    assert safe_db_counter(db, "_query_count") == 3


def test_safe_db_counter_reads_nested_db_attrs():
    inner = type("Inner", (), {})()
    inner._commit_count = 11
    outer = type("Outer", (), {})()
    outer.db = inner

    class _ProxyOuter:
        def __init__(self):
            self.db = inner

        def __getattr__(self, name):
            return lambda *a, **k: None

    assert safe_db_counter(_ProxyOuter(), "_commit_count") == 11


def test_safe_db_counter_none_and_invalid():
    assert safe_db_counter(None, "_commit_count") == 0
    db = type("DB", (), {})()
    db._commit_count = "nope"
    assert safe_db_counter(db, "_commit_count") == 0


def test_db_io_stats_uses_safe_counters():
    mgr = DatabaseManager()
    mgr.set_database(_ProxyDB())
    stats = mgr.db_io_stats()
    assert stats["commits"] == 0
    assert stats["queries"] == 0
