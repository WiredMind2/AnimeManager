"""Threaded SDK execution helper for Tk presenters."""

from __future__ import annotations

import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable


class TkAsyncRunner:
    """Runs blocking SDK calls off the Tk main thread."""

    def __init__(self, schedule_ui: Callable[[Callable[[], None]], None]) -> None:
        self._schedule_ui = schedule_ui
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tk-sdk")

    def submit(
        self,
        func: Callable[..., Any],
        *args: Any,
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        **kwargs: Any,
    ) -> None:
        future = self._executor.submit(func, *args, **kwargs)

        def _done() -> None:
            try:
                result = future.result()
            except Exception as exc:  # pragma: no cover - GUI path
                # Bind ``exc`` to a local outside the ``except`` block so
                # the scheduled lambda can still see it after Python clears
                # the exception variable when the block exits.
                err = exc
                traceback.print_exception(type(err), err, err.__traceback__, file=sys.stderr)
                if on_error is not None:
                    self._schedule_ui(lambda: on_error(err))
                return
            if on_success is not None:
                self._schedule_ui(lambda: on_success(result))

        future.add_done_callback(lambda _f: _done())

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
