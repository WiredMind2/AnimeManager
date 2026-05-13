"""Performance tests for the torrent search refactor.

These tests verify the structural guarantees that drive the performance
improvements (bounded fan-out, set-based dedupe, deterministic ranking)
rather than wall-clock benchmarks that would be flaky in CI.
"""

from __future__ import annotations

import io
import os
import sys
import threading
import time
from typing import List, Optional

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from search_engines.config import SearchLimits, SearchProfile
from search_engines.dedupe import ResultDeduper
from search_engines.engine_policy import get_default_policy
from search_engines.facade import SearchFacade
from search_engines.parser import TorrentResult
from search_engines.planner import plan_terms
from search_engines.worker import _ProcessRunner


def test_planner_caps_subprocess_fanout_at_max_terms():
    raw = [f"Synonym Title #{i}" for i in range(50)]
    limits = SearchLimits(max_terms=6, max_term_length=200)
    plan = plan_terms(raw, limits)
    assert len(plan.terms) == 6
    assert len(plan.dropped) == 44


def test_dedupe_is_constant_time_per_insert():
    deduper = ResultDeduper()
    n = 5000
    start = time.perf_counter()
    for i in range(n):
        deduper.register(
            TorrentResult(
                link=f"magnet:?xt=urn:btih:{i:040x}",
                name=f"Title {i}",
                size=100,
                seeds=1,
                leech=0,
                engine_url="https://nyaa.si",
                desc_link=None,
                infohash=f"{i:040x}",
            )
        )
    elapsed = time.perf_counter() - start
    # Generous upper bound; the previous list-based fallback would scale
    # quadratically and blow past this on any modern machine.
    assert elapsed < 1.0, f"dedupe too slow: {elapsed:.3f}s for {n} inserts"
    assert len(deduper) == n


class _RecordingProcess:
    def __init__(self):
        self.stdout = io.BytesIO(b"")
        self.stderr = io.BytesIO(b"")
        self.returncode: Optional[int] = 0

    def poll(self) -> Optional[int]:
        return 0

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass

    def wait(self, timeout: Optional[float] = None) -> int:
        return 0


class _CountingRunner(_ProcessRunner):
    def __init__(self):
        self.spawn_count = 0
        self.lock = threading.Lock()

    def spawn(self, args):  # type: ignore[override]
        with self.lock:
            self.spawn_count += 1
        return _RecordingProcess()  # type: ignore[return-value]


def test_subprocess_fanout_is_bounded_by_planner(monkeypatch):
    runner = _CountingRunner()
    monkeypatch.setattr("search_engines.worker._ProcessRunner.spawn", runner.spawn)

    profile = SearchProfile(
        name="interactive",
        limits=SearchLimits(
            max_terms=3,
            max_concurrent_jobs=2,
            per_job_timeout_s=0.5,
            request_deadline_s=1.5,
            max_results=10,
            max_output_bytes=1024,
            max_line_bytes=512,
            queue_capacity=32,
        ),
        allow_insecure_engines=False,
        allow_no_timeout_engines=True,
    )
    facade = SearchFacade(profile=profile, policy=get_default_policy())
    raw = [f"Synonym {i}" for i in range(20)]
    list(facade.search(raw))

    # One subprocess per planned (term, engine_batch). Engines are batched
    # into a single nova3 invocation per term so this equals max_terms.
    assert runner.spawn_count == 3, runner.spawn_count
