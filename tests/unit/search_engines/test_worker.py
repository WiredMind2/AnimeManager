"""Worker-level tests using a fake process runner.

These exercise the orchestration semantics (timeouts, byte caps, line
caps, cancellation, sink dispatch) without spawning real Python
subprocesses, keeping the test suite fast and platform independent.
"""

from __future__ import annotations

import io
import threading
import time
from typing import List, Optional

import pytest

from search_engines.config import SearchLimits, SearchProfile
from search_engines.parser import ResultParser, TorrentResult
from search_engines.worker import NovaWorker, SearchJob, _ProcessRunner


VALID_MAGNET = (
    "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567"
    "&dn=Example"
)


class _FakeStdout(io.BytesIO):
    """BytesIO that supports ``readline(n)`` semantics like a pipe."""

    def readline(self, limit: int = -1) -> bytes:  # type: ignore[override]
        if limit is None or limit < 0:
            return super().readline()
        return super().readline(limit)


class _FakeProcess:
    def __init__(self, stdout_bytes: bytes, stderr_bytes: bytes = b"", hang: bool = False):
        self.stdout = _FakeStdout(stdout_bytes)
        self.stderr = io.BytesIO(stderr_bytes)
        self._hang = hang
        self._terminated = False
        self.returncode: Optional[int] = None

    def poll(self) -> Optional[int]:
        if self._hang and not self._terminated:
            return None
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def terminate(self) -> None:
        self._terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self._terminated = True
        self.returncode = -9

    def wait(self, timeout: Optional[float] = None) -> int:
        if self._terminated:
            return self.returncode or 0
        return 0


class _FakeRunner(_ProcessRunner):
    def __init__(self, process: _FakeProcess):
        self._process = process
        self.last_args: Optional[List[str]] = None

    def spawn(self, args):  # type: ignore[override]
        self.last_args = list(args)
        return self._process  # type: ignore[return-value]


def _profile(**overrides) -> SearchProfile:
    base = dict(
        name="test",
        limits=SearchLimits(
            max_terms=4,
            max_concurrent_jobs=2,
            per_job_timeout_s=1.0,
            request_deadline_s=2.0,
            max_results_per_term=10,
            max_output_bytes=4096,
            max_line_bytes=512,
            queue_capacity=32,
        ),
        allow_insecure_engines=False,
        allow_no_timeout_engines=False,
        engines=None,
        category="anime",
        rank_results=False,
    )
    base.update(overrides)
    return SearchProfile(**base)


def _job(term: str = "demo") -> SearchJob:
    return SearchJob(job_id="job-1", term=term, engines=["nyaasi"], category="anime")


def test_worker_invokes_subprocess_with_argument_list(reset_metrics):
    process = _FakeProcess(
        stdout_bytes=("|".join([
            VALID_MAGNET,
            "Title",
            "1024",
            "10",
            "1",
            "https://nyaa.si",
            "https://nyaa.si/view/1",
        ]) + "\n").encode("utf-8")
    )
    runner = _FakeRunner(process)
    results: List[TorrentResult] = []

    def sink(result, job):
        results.append(result)

    worker = NovaWorker(
        _profile(),
        ResultParser(max_line_bytes=512),
        sink,
        threading.Event(),
        runner=runner,
    )
    outcome = worker.run(_job("safe term"), deadline=time.monotonic() + 2.0)

    assert runner.last_args == ["nyaasi", "anime", "safe term"]
    assert outcome.rows_emitted == 1
    assert outcome.exit_reason == "completed"
    assert results and results[0].name == "Title"


def test_worker_terminates_on_timeout(reset_metrics):
    process = _FakeProcess(stdout_bytes=b"", hang=True)
    runner = _FakeRunner(process)
    worker = NovaWorker(
        _profile(limits=SearchLimits(per_job_timeout_s=0.05, request_deadline_s=0.2)),
        ResultParser(max_line_bytes=512),
        lambda r, j: None,
        threading.Event(),
        runner=runner,
    )
    deadline = time.monotonic() + 1.0
    outcome = worker.run(_job(), deadline)
    assert outcome.rows_emitted == 0
    assert process._terminated is True


def test_worker_respects_output_cap(reset_metrics):
    payload = ("|".join([
        VALID_MAGNET,
        "Title",
        "1024",
        "10",
        "1",
        "https://nyaa.si",
        "https://nyaa.si/view/1",
    ]) + "\n").encode("utf-8")
    big_stream = payload * 10
    process = _FakeProcess(stdout_bytes=big_stream)
    profile = _profile()
    profile = SearchProfile(
        name="cap",
        limits=SearchLimits(
            **{**profile.limits.__dict__, "max_output_bytes": len(payload) + 5}
        ),
    )
    runner = _FakeRunner(process)
    collected: List[TorrentResult] = []
    worker = NovaWorker(
        profile,
        ResultParser(max_line_bytes=512),
        lambda r, j: collected.append(r),
        threading.Event(),
        runner=runner,
    )
    outcome = worker.run(_job(), deadline=time.monotonic() + 2.0)
    assert outcome.exit_reason == "output_cap_exceeded"
    assert outcome.rows_emitted < 10


def test_worker_skips_oversize_lines(reset_metrics):
    huge = b"x" * 2048 + b"\n"
    valid = ("|".join([
        VALID_MAGNET,
        "Title",
        "10",
        "1",
        "1",
        "https://nyaa.si",
        "https://nyaa.si/view/1",
    ]) + "\n").encode("utf-8")
    process = _FakeProcess(stdout_bytes=huge + valid)
    runner = _FakeRunner(process)
    collected: List[TorrentResult] = []
    worker = NovaWorker(
        _profile(limits=SearchLimits(max_line_bytes=128, per_job_timeout_s=1.0)),
        ResultParser(max_line_bytes=128),
        lambda r, j: collected.append(r),
        threading.Event(),
        runner=runner,
    )
    outcome = worker.run(_job(), deadline=time.monotonic() + 2.0)
    assert outcome.rows_emitted == 1
    assert collected[0].name == "Title"
