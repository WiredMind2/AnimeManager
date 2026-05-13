"""Telemetry primitives for the torrent search subsystem.

Provides:
  * a thread-safe ``Metrics`` aggregator that counters/timings can be
    pulled from in tests and operational dashboards;
  * a ``structured_log`` helper that emits one-line key=value records
    via the project logger when available, with a stdout fallback for
    unit tests that import the package standalone.

No external dependencies. Designed to stay cheap on the hot path.
"""

from __future__ import annotations

import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, Optional


def new_request_id() -> str:
    """Return a short, unique identifier suitable for log correlation."""
    return uuid.uuid4().hex[:12]


@dataclass
class Metrics:
    """Process-wide aggregated counters and timings for search operations."""

    counters: Dict[str, int] = field(default_factory=dict)
    timings_ms: Dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def incr(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self.counters[name] = self.counters.get(name, 0) + amount

    def observe_ms(self, name: str, value_ms: float) -> None:
        with self._lock:
            # Accumulate so callers can compute averages externally.
            self.timings_ms[name] = self.timings_ms.get(name, 0.0) + value_ms

    @contextmanager
    def timer(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self.observe_ms(name, (time.perf_counter() - start) * 1000.0)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self.counters),
                "timings_ms": dict(self.timings_ms),
            }

    def reset(self) -> None:
        with self._lock:
            self.counters.clear()
            self.timings_ms.clear()


_GLOBAL_METRICS = Metrics()


def get_metrics() -> Metrics:
    """Return the process-wide metrics aggregator."""
    return _GLOBAL_METRICS


def _resolve_logger() -> Any:
    """Best-effort resolution of the existing project logger.

    Falls back to a no-op when imports fail so the package can be used
    in isolation (e.g., during unit tests run outside the main app).
    """
    try:
        from shared.telemetry.logger import log
        return log
    except Exception:  # pragma: no cover - defensive fallback
        try:
            from AnimeManager.shared.telemetry.logger import log  # type: ignore
            return log
        except Exception:
            return None


_LOGGER = _resolve_logger()


def structured_log(
    event: str,
    request_id: Optional[str] = None,
    level: str = "FILE_SEARCH",
    **fields: Any,
) -> None:
    """Emit a single-line structured record.

    Args:
        event: Short, machine-friendly event name (e.g. ``request_start``).
        request_id: Correlation id for the request.
        level: Log channel used by the project logger.
        **fields: Arbitrary key/value pairs to include.
    """
    pieces = [f"event={event}"]
    if request_id is not None:
        pieces.append(f"rid={request_id}")
    for key, value in fields.items():
        rendered = str(value).replace("\n", " ").replace("=", "_")
        if len(rendered) > 256:
            rendered = rendered[:253] + "..."
        pieces.append(f"{key}={rendered}")
    line = " ".join(pieces)

    if _LOGGER is not None:
        try:
            _LOGGER(level, line)
            return
        except Exception:  # pragma: no cover - logger should not break search
            pass
    # Fallback for unit-test or standalone use. Kept silent under typical
    # production usage where the project logger is available.
    print(f"[{level}] {line}")
