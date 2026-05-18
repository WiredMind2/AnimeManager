"""Provider health tracking with circuit-breaker semantics for metadata ingestion."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ProviderHealthState:
    """Mutable health snapshot for one provider."""

    name: str
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    last_failure_at: Optional[float] = None
    last_success_at: Optional[float] = None
    quarantined_until: Optional[float] = None


class ProviderHealthTracker:
    """Circuit-breaker style tracker for metadata provider wrappers.

    Providers that exceed ``failure_threshold`` consecutive failures are
    quarantined for ``quarantine_seconds`` and skipped by the coordinator.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        quarantine_seconds: float = 300.0,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        self._failure_threshold = failure_threshold
        self._quarantine_seconds = quarantine_seconds
        self._lock = threading.Lock()
        self._states: Dict[str, ProviderHealthState] = {}

    def _state(self, name: str) -> ProviderHealthState:
        key = str(name or "unknown")
        if key not in self._states:
            self._states[key] = ProviderHealthState(name=key)
        return self._states[key]

    def record_success(self, name: str) -> None:
        with self._lock:
            st = self._state(name)
            st.consecutive_failures = 0
            st.total_successes += 1
            st.last_success_at = time.time()
            st.quarantined_until = None

    def record_failure(self, name: str) -> None:
        with self._lock:
            st = self._state(name)
            st.consecutive_failures += 1
            st.total_failures += 1
            st.last_failure_at = time.time()
            if st.consecutive_failures >= self._failure_threshold:
                st.quarantined_until = time.time() + self._quarantine_seconds

    def is_available(self, name: str, *, now: Optional[float] = None) -> bool:
        ts = time.time() if now is None else now
        with self._lock:
            st = self._state(name)
            until = st.quarantined_until
            if until is None:
                return True
            if ts >= until:
                st.quarantined_until = None
                st.consecutive_failures = 0
                return True
            return False

    def quarantined_names(self, *, now: Optional[float] = None) -> List[str]:
        ts = time.time() if now is None else now
        with self._lock:
            out: List[str] = []
            for name, st in self._states.items():
                until = st.quarantined_until
                if until is not None and ts < until:
                    out.append(name)
            return sorted(out)

    def snapshot(self) -> Dict[str, Dict[str, object]]:
        with self._lock:
            return {
                name: {
                    "consecutive_failures": st.consecutive_failures,
                    "total_failures": st.total_failures,
                    "total_successes": st.total_successes,
                    "quarantined_until": st.quarantined_until,
                }
                for name, st in self._states.items()
            }


__all__ = ["ProviderHealthState", "ProviderHealthTracker"]
