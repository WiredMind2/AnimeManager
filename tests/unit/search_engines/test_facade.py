"""Integration tests for the orchestration facade.

The facade is exercised end-to-end with the real planner, policy, parser,
dedupe and worker stages. Only the subprocess runner is faked so we do
not perform any network I/O.
"""

from __future__ import annotations

import io
import time
from typing import Dict, List, Optional

import pytest

from search_engines.config import SearchLimits, SearchProfile
from search_engines.facade import SearchFacade
from search_engines.worker import _ProcessRunner


VALID_MAGNET_TEMPLATE = (
    "magnet:?xt=urn:btih:{hash}&dn={name}"
)


class _FakeStdout(io.BytesIO):
    def readline(self, limit: int = -1) -> bytes:  # type: ignore[override]
        if limit is None or limit < 0:
            return super().readline()
        return super().readline(limit)


class _ScriptedProcess:
    def __init__(self, payload: bytes):
        self.stdout = _FakeStdout(payload)
        self.stderr = io.BytesIO(b"")
        self.returncode: Optional[int] = None
        self._terminated = False

    def poll(self) -> Optional[int]:
        if self.returncode is None and self.stdout.tell() == len(self.stdout.getvalue()):
            self.returncode = 0
        return self.returncode

    def terminate(self) -> None:
        self._terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self._terminated = True
        self.returncode = -9

    def wait(self, timeout: Optional[float] = None) -> int:
        return self.returncode or 0


class _ScriptedRunner(_ProcessRunner):
    """Returns canned stdout per (engines, term)."""

    def __init__(self, scripts: Dict[str, bytes]):
        self._scripts = scripts
        self.invocations: List[List[str]] = []

    def spawn(self, args):  # type: ignore[override]
        self.invocations.append(list(args))
        term = args[-1]
        payload = self._scripts.get(term, b"")
        return _ScriptedProcess(payload)  # type: ignore[return-value]


def _row(infohash: str, name: str, seeds: int = 10) -> bytes:
    magnet = VALID_MAGNET_TEMPLATE.format(hash=infohash, name=name)
    return ("|".join([
        magnet,
        name,
        "1024",
        str(seeds),
        "1",
        "https://nyaa.si",
        f"https://nyaa.si/view/{infohash[:4]}",
    ]) + "\n").encode("utf-8")


def _profile(**overrides) -> SearchProfile:
    base = dict(
        name="interactive",
        limits=SearchLimits(
            max_terms=3,
            max_concurrent_jobs=2,
            per_job_timeout_s=2.0,
            request_deadline_s=3.0,
            max_results_per_term=20,
            max_output_bytes=8192,
            max_line_bytes=2048,
            queue_capacity=64,
        ),
        allow_insecure_engines=False,
        allow_no_timeout_engines=True,
        engines=None,
        category="anime",
        rank_results=False,
    )
    base.update(overrides)
    return SearchProfile(**base)


@pytest.fixture
def facade(monkeypatch, policy_factory):
    policy = policy_factory(
        engines={"nyaasi": {"enabled": True, "risk_level": "low"}}
    )
    facade = SearchFacade(profile=_profile(), policy=policy)
    # Patch the worker's runner factory through monkeypatching the module-level
    # default. Tests provide a scripted runner per case.
    return facade


def test_facade_streams_dedup_and_emits_dicts(monkeypatch, facade):
    payload = _row("aaaa1111", "First Title") + _row("aaaa1111", "Duplicate") + _row(
        "bbbb2222", "Second Title"
    )
    runner = _ScriptedRunner({"Alpha Title": payload})
    monkeypatch.setattr(
        "search_engines.worker._ProcessRunner.spawn", runner.spawn
    )

    out = list(facade.search(["Alpha Title"]))
    names = sorted(item["name"] for item in out)
    assert names == ["First Title", "Second Title"]
    assert all(item["link"].startswith("magnet:?xt=urn:btih:") for item in out)


def test_facade_caps_results_per_term(monkeypatch, policy_factory):
    policy = policy_factory(
        engines={"nyaasi": {"enabled": True, "risk_level": "low"}}
    )
    profile = _profile(
        limits=SearchLimits(
            max_terms=1,
            max_concurrent_jobs=1,
            per_job_timeout_s=2.0,
            request_deadline_s=3.0,
            max_results_per_term=2,
            max_output_bytes=8192,
            max_line_bytes=2048,
            queue_capacity=64,
        )
    )
    facade = SearchFacade(profile=profile, policy=policy)

    payload = b"".join(_row(f"hash{i:08x}", f"Title {i}") for i in range(10))
    runner = _ScriptedRunner({"Series": payload})
    monkeypatch.setattr(
        "search_engines.worker._ProcessRunner.spawn", runner.spawn
    )

    out = list(facade.search(["Series"]))
    assert len(out) == 2


def test_facade_allows_total_above_per_term_across_terms(monkeypatch, policy_factory):
    """Each term is capped independently; totals scale with term count."""
    policy = policy_factory(
        engines={"nyaasi": {"enabled": True, "risk_level": "low"}}
    )
    profile = _profile(
        limits=SearchLimits(
            max_terms=2,
            max_concurrent_jobs=2,
            per_job_timeout_s=2.0,
            request_deadline_s=3.0,
            max_results_per_term=2,
            max_output_bytes=8192,
            max_line_bytes=2048,
            queue_capacity=64,
        )
    )
    facade = SearchFacade(profile=profile, policy=policy)

    payload_a = b"".join(_row(f"aaaa{i:04x}", f"Alpha {i}") for i in range(10))
    payload_b = b"".join(_row(f"bbbb{i:04x}", f"Beta {i}") for i in range(10))
    runner = _ScriptedRunner({"Alpha": payload_a, "Beta": payload_b})
    monkeypatch.setattr(
        "search_engines.worker._ProcessRunner.spawn", runner.spawn
    )

    out = list(facade.search(["Alpha", "Beta"]))
    assert len(out) == 4


def test_facade_returns_empty_when_no_engines_allowed(monkeypatch, policy_factory):
    policy = policy_factory(engines={})
    facade = SearchFacade(profile=_profile(), policy=policy)

    runner = _ScriptedRunner({})
    monkeypatch.setattr(
        "search_engines.worker._ProcessRunner.spawn", runner.spawn
    )

    out = list(facade.search(["whatever"]))
    assert out == []


def test_facade_strict_profile_ranks_results(monkeypatch, policy_factory):
    policy = policy_factory(
        engines={"nyaasi": {"enabled": True, "risk_level": "low"}}
    )
    profile = _profile(name="strict", rank_results=True)
    facade = SearchFacade(profile=profile, policy=policy)

    payload = (
        _row("aaaa1111", "Low Seeds", seeds=2)
        + _row("bbbb2222", "High Seeds", seeds=99)
        + _row("cccc3333", "Mid Seeds", seeds=50)
    )
    runner = _ScriptedRunner({"Anime Series": payload})
    monkeypatch.setattr(
        "search_engines.worker._ProcessRunner.spawn", runner.spawn
    )

    out = list(facade.search(["Anime Series"]))
    names = [item["name"] for item in out]
    assert names == ["High Seeds", "Mid Seeds", "Low Seeds"]
