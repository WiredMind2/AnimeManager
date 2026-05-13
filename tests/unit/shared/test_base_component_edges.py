"""Edge case tests for ``shared.base_component.BaseComponent``."""

from __future__ import annotations

import threading

import pytest

from shared.base_component import BaseComponent


class TestBaseComponentLifecycle:
    def test_default_name_is_class_name(self):
        c = BaseComponent()
        assert c.name == "BaseComponent"

    def test_custom_name_used(self):
        c = BaseComponent(name="custom")
        assert c.name == "custom"

    def test_empty_string_name_falls_back_to_class_name(self):
        c = BaseComponent(name="")
        assert c.name == "BaseComponent"

    def test_none_name_falls_back_to_class_name(self):
        c = BaseComponent(name=None)
        assert c.name == "BaseComponent"

    def test_initial_state(self):
        c = BaseComponent()
        assert c.is_initialized is False
        assert c.is_started is False
        assert c.is_stopped is False

    def test_initialize_sets_flag(self):
        c = BaseComponent()
        c.initialize()
        assert c.is_initialized is True

    def test_initialize_idempotent(self):
        calls = []

        class Sub(BaseComponent):
            def _initialize(self):
                calls.append("init")

        c = Sub()
        c.initialize()
        c.initialize()
        c.initialize()
        assert calls == ["init"]

    def test_start_idempotent(self):
        calls = []

        class Sub(BaseComponent):
            def _start(self):
                calls.append("start")

        c = Sub()
        c.start()
        c.start()
        assert calls == ["start"]

    def test_stop_idempotent(self):
        calls = []

        class Sub(BaseComponent):
            def _stop(self):
                calls.append("stop")

        c = Sub()
        c.stop()
        c.stop()
        assert calls == ["stop"]

    def test_lifecycle_can_run_through_each_state(self):
        c = BaseComponent()
        c.initialize()
        c.start()
        c.stop()
        assert c.is_initialized and c.is_started and c.is_stopped

    def test_repr_includes_state(self):
        c = BaseComponent(name="my-comp")
        rep = repr(c)
        assert "my-comp" in rep
        assert "initialized=False" in rep
        assert "started=False" in rep

    def test_log_is_callable(self):
        c = BaseComponent()
        assert callable(c.log)

    def test_subclass_initialize_exception_does_not_set_flag(self):
        class Sub(BaseComponent):
            def _initialize(self):
                raise RuntimeError("boom")

        c = Sub()
        with pytest.raises(RuntimeError):
            c.initialize()
        # Flag remains False so caller can retry / clean up
        assert c.is_initialized is False

    def test_subclass_start_exception_keeps_flag_false(self):
        class Sub(BaseComponent):
            def _start(self):
                raise RuntimeError("boom")

        c = Sub()
        with pytest.raises(RuntimeError):
            c.start()
        assert c.is_started is False

    def test_lock_is_reentrant(self):
        c = BaseComponent()
        # Acquire twice from the same thread; should not deadlock
        with c._lock:
            with c._lock:
                pass

    def test_concurrent_initialize_calls_each_subclass_once(self):
        calls = []

        class Sub(BaseComponent):
            def _initialize(self):
                calls.append(1)

        c = Sub()

        def worker():
            c.initialize()

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert calls == [1]
