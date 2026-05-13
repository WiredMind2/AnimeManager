"""Secure subprocess worker for nova3 search jobs.

The worker spawns ``python -m nova3.nova2`` with an argument **list** (no
shell interpretation, no string interpolation of user input) and enforces:

  * a per-job wall-clock timeout with hard kill;
  * a global request deadline;
  * bounded stdout reading (per-line and total caps);
  * cooperative cancellation through a shared ``threading.Event``.

The worker emits ``TorrentResult`` records through the supplied parser and
keeps its API minimal so it can be unit tested without spinning up real
subprocesses.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional

from .config import SearchProfile
from .parser import ResultParser, TorrentResult
from .telemetry import get_metrics, structured_log

# nova3 is vendored at the legacy ``search_engines/nova3`` path and
# treated as an immutable black-box dependency. The worker spawns a
# subprocess with that directory as the CWD so ``python -m nova3.nova2``
# resolves against the vendored tree.
_NOVA_CWD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "search_engines",
)
_NOVA_MODULE = "nova3.nova2"


@dataclass(frozen=True)
class SearchJob:
    """All data required to run one nova3 invocation."""

    job_id: str
    term: str
    engines: List[str]
    category: str


@dataclass
class JobOutcome:
    """Outcome of running a single :class:`SearchJob`."""

    job_id: str
    term: str
    started_at: float
    finished_at: float
    exit_reason: str
    exit_code: Optional[int]
    rows_emitted: int
    bytes_read: int
    stderr_excerpt: str


ResultSink = Callable[[TorrentResult, SearchJob], None]


class _ProcessRunner:
    """Thin abstraction over ``subprocess.Popen`` to ease testing.

    Production code uses the default implementation; unit tests inject a
    fake runner via :class:`NovaWorker` to avoid spawning real processes.
    """

    def __init__(self, executable: Optional[str] = None) -> None:
        self._executable = executable or sys.executable

    def spawn(self, args: List[str]) -> subprocess.Popen:
        """Spawn ``[python, -m, nova3.nova2, *args]`` with shell=False."""
        cmd = [self._executable, "-m", _NOVA_MODULE, *args]
        creationflags = 0
        if os.name == "nt":
            # Avoid flashing a console window when invoked from the Tk GUI.
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=_NOVA_CWD,
            shell=False,
            creationflags=creationflags,
            bufsize=1,
        )


class NovaWorker:
    """Runs a single :class:`SearchJob` against ``nova3.nova2``."""

    def __init__(
        self,
        profile: SearchProfile,
        parser: ResultParser,
        sink: ResultSink,
        cancel_event: threading.Event,
        runner: Optional[_ProcessRunner] = None,
        request_id: Optional[str] = None,
    ) -> None:
        self._profile = profile
        self._parser = parser
        self._sink = sink
        self._cancel = cancel_event
        self._runner = runner or _ProcessRunner()
        self._request_id = request_id
        self._metrics = get_metrics()

    def run(self, job: SearchJob, deadline: float) -> JobOutcome:
        """Execute the job and return a structured outcome."""
        limits = self._profile.limits
        per_job_deadline = min(
            deadline,
            time.monotonic() + limits.per_job_timeout_s,
        )

        engines_arg = ",".join(job.engines) if job.engines else "all"
        args = [engines_arg, job.category, job.term]
        started = time.monotonic()
        rows = 0
        bytes_read = 0
        stderr_excerpt = ""
        exit_reason = "completed"
        exit_code: Optional[int] = None

        if self._cancel.is_set():
            return JobOutcome(
                job_id=job.job_id,
                term=job.term,
                started_at=started,
                finished_at=started,
                exit_reason="cancelled_before_start",
                exit_code=None,
                rows_emitted=0,
                bytes_read=0,
                stderr_excerpt="",
            )

        process: Optional[subprocess.Popen] = None
        try:
            process = self._runner.spawn(args)
        except FileNotFoundError as exc:
            structured_log(
                "worker_spawn_failed",
                request_id=self._request_id,
                job=job.job_id,
                error=str(exc),
            )
            self._metrics.incr("worker_spawn_failed")
            return JobOutcome(
                job_id=job.job_id,
                term=job.term,
                started_at=started,
                finished_at=time.monotonic(),
                exit_reason="spawn_failed",
                exit_code=None,
                rows_emitted=0,
                bytes_read=0,
                stderr_excerpt=str(exc),
            )

        assert process.stdout is not None  # for type checkers
        try:
            for line in self._iterate_stdout(process, per_job_deadline):
                bytes_read += len(line)
                if bytes_read > limits.max_output_bytes:
                    exit_reason = "output_cap_exceeded"
                    self._metrics.incr("worker_output_cap")
                    break

                result = self._parser.parse(line)
                if result is None:
                    continue
                try:
                    self._sink(result, job)
                except Exception as exc:  # pragma: no cover - sink errors are logged
                    structured_log(
                        "worker_sink_error",
                        request_id=self._request_id,
                        job=job.job_id,
                        error=str(exc),
                    )
                    self._metrics.incr("worker_sink_error")
                    continue
                rows += 1
                if rows >= limits.max_results:
                    exit_reason = "result_cap_reached"
                    break

            if self._cancel.is_set() and exit_reason == "completed":
                exit_reason = "cancelled"
        finally:
            exit_code, captured_stderr = self._terminate(process, exit_reason)
            stderr_excerpt = _excerpt(captured_stderr)

        finished = time.monotonic()
        structured_log(
            "worker_finished",
            request_id=self._request_id,
            job=job.job_id,
            term_len=len(job.term),
            duration_ms=int((finished - started) * 1000),
            rows=rows,
            bytes=bytes_read,
            exit_reason=exit_reason,
            exit_code=exit_code,
        )
        return JobOutcome(
            job_id=job.job_id,
            term=job.term,
            started_at=started,
            finished_at=finished,
            exit_reason=exit_reason,
            exit_code=exit_code,
            rows_emitted=rows,
            bytes_read=bytes_read,
            stderr_excerpt=stderr_excerpt,
        )

    def _iterate_stdout(
        self, process: subprocess.Popen, deadline: float
    ) -> Iterable[bytes]:
        stdout = process.stdout
        assert stdout is not None
        max_line = self._profile.limits.max_line_bytes
        while True:
            if self._cancel.is_set():
                return
            if time.monotonic() >= deadline:
                self._metrics.incr("worker_timeout")
                return
            line = stdout.readline(max_line + 1)
            if not line:
                if process.poll() is not None:
                    return
                # No data available; yield control and re-check deadline.
                time.sleep(0.01)
                continue
            if len(line) > max_line:
                self._metrics.incr("worker_dropped_oversize_line")
                # Drain the rest of the over-long line so we stay aligned.
                _drain_overflow(stdout, max_line)
                continue
            yield line

    def _terminate(
        self,
        process: Optional[subprocess.Popen],
        exit_reason: str,
    ) -> tuple[Optional[int], bytes]:
        if process is None:
            return None, b""

        if process.poll() is None:
            self._metrics.incr(f"worker_terminate_{exit_reason}")
            try:
                process.terminate()
                try:
                    process.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=1.5)
                    except subprocess.TimeoutExpired:
                        pass
            except Exception as exc:  # pragma: no cover - defensive
                structured_log(
                    "worker_terminate_failed",
                    request_id=self._request_id,
                    error=str(exc),
                )

        stderr = b""
        try:
            if process.stderr is not None:
                stderr = process.stderr.read() or b""
        except Exception:
            stderr = b""
        return process.returncode, stderr


def _drain_overflow(stream, chunk: int) -> None:
    """Skip the rest of an oversize line without unbounded reads."""
    remaining = chunk * 8
    while remaining > 0:
        data = stream.readline(chunk)
        if not data or data.endswith(b"\n"):
            return
        remaining -= len(data)


def _excerpt(blob: bytes, limit: int = 512) -> str:
    if not blob:
        return ""
    try:
        text = blob.decode("utf-8", errors="replace")
    except Exception:
        return ""
    return text if len(text) <= limit else text[: limit - 3] + "..."
