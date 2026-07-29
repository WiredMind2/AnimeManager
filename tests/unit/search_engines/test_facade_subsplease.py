"""Facade tests for first-party SubsPlease interactive search."""

from __future__ import annotations

import io
import json
from typing import Dict, List, Optional

import pytest

from adapters.search.subsplease_api import SubsPleaseSearchAdapter
from search_engines.config import SearchLimits, SearchProfile
from search_engines.facade import SearchFacade
from search_engines.worker import _ProcessRunner

_SAMPLE = {
    "Demo Show - 01": {
        "show": "Demo Show",
        "episode": "01",
        "page": "demo-show",
        "downloads": [
            {
                "res": "720",
                "magnet": "magnet:?xt=urn:btih:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb&dn=720&xl=2048",
            },
            {
                "res": "1080",
                "magnet": "magnet:?xt=urn:btih:cccccccccccccccccccccccccccccccc&dn=1080&xl=4096",
            },
        ],
    },
}


VALID_MAGNET_TEMPLATE = "magnet:?xt=urn:btih:{hash}&dn={name}"


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

    def poll(self) -> Optional[int]:
        if self.returncode is None and self.stdout.tell() == len(self.stdout.getvalue()):
            self.returncode = 0
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

    def wait(self, timeout: Optional[float] = None) -> int:
        return self.returncode or 0


class _ScriptedRunner(_ProcessRunner):
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
    return (
        "|".join(
            [
                magnet,
                name,
                "1024",
                str(seeds),
                "1",
                "https://nyaa.si",
                f"https://nyaa.si/view/{infohash[:4]}",
            ]
        )
        + "\n"
    ).encode("utf-8")


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


def _fake_sp_adapter() -> SubsPleaseSearchAdapter:
    def opener(url: str, timeout_s: float) -> str:
        if "p=0" in url:
            return json.dumps(_SAMPLE)
        return "{}"

    return SubsPleaseSearchAdapter(opener=opener, max_pages=2)


def test_facade_emits_subsplease_rows_without_nova(monkeypatch, policy_factory):
    policy = policy_factory(engines={})
    facade = SearchFacade(
        profile=_profile(),
        policy=policy,
        subsplease_search=_fake_sp_adapter(),
    )
    runner = _ScriptedRunner({})
    monkeypatch.setattr("search_engines.worker._ProcessRunner.spawn", runner.spawn)

    out = list(facade.search(["Demo Show"]))
    assert runner.invocations == []
    assert len(out) == 2
    assert all("[SubsPlease]" in row["name"] for row in out)
    assert {row["infohash"] for row in out} == {
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "cccccccccccccccccccccccccccccccc",
    }
    assert all(row["engine_url"] == "https://subsplease.org/" for row in out)


def test_facade_dedupes_subsplease_against_nova(monkeypatch, policy_factory):
    policy = policy_factory(
        engines={"nyaasi": {"enabled": True, "risk_level": "low"}}
    )
    # Nova emits the same 720p infohash as SubsPlease sample.
    payload = _row("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "Nova Dup", seeds=50)
    runner = _ScriptedRunner({"Demo Show": payload})
    monkeypatch.setattr("search_engines.worker._ProcessRunner.spawn", runner.spawn)

    facade = SearchFacade(
        profile=_profile(),
        policy=policy,
        subsplease_search=_fake_sp_adapter(),
    )
    out = list(facade.search(["Demo Show"]))
    hashes = [row["infohash"] for row in out]
    assert hashes.count("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb") == 1
    assert "cccccccccccccccccccccccccccccccc" in hashes
