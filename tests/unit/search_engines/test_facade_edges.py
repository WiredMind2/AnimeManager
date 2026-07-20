"""Additional edge-case tests for ``adapters.search.facade``."""

from __future__ import annotations

import io
import time
from typing import Dict, List, Optional

import pytest

from search_engines.config import SearchLimits, SearchProfile
from search_engines.facade import (
    DEFAULT_PROFILES,
    SearchFacade,
    SearchSummary,
    search,
    search_strict,
)
from search_engines.worker import _ProcessRunner


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
    def __init__(self, scripts: Dict[str, bytes]):
        self._scripts = scripts
        self.invocations: List[List[str]] = []

    def spawn(self, args):  # type: ignore[override]
        self.invocations.append(list(args))
        term = args[-1]
        payload = self._scripts.get(term, b"")
        return _ScriptedProcess(payload)  # type: ignore[return-value]


def _profile(**overrides) -> SearchProfile:
    base = dict(
        name="interactive",
        limits=SearchLimits(
            max_terms=2,
            max_concurrent_jobs=1,
            per_job_timeout_s=2.0,
            request_deadline_s=3.0,
            max_results_per_term=10,
            max_output_bytes=4096,
            max_line_bytes=2048,
            queue_capacity=32,
        ),
        allow_insecure_engines=False,
        allow_no_timeout_engines=True,
    )
    base.update(overrides)
    return SearchProfile(**base)


# ---------------------------------------------------------------------------
# Empty / degenerate inputs
# ---------------------------------------------------------------------------


class TestEmptyInputs:
    def test_empty_term_list_yields_empty(self, monkeypatch, policy_factory):
        policy = policy_factory(engines={"nyaasi": {"enabled": True}})
        facade = SearchFacade(profile=_profile(), policy=policy)

        runner = _ScriptedRunner({})
        monkeypatch.setattr(
            "search_engines.worker._ProcessRunner.spawn", runner.spawn
        )

        assert list(facade.search([])) == []
        # No process should have been spawned
        assert runner.invocations == []

    def test_terms_collapsing_to_zero_yields_empty(self, monkeypatch, policy_factory):
        policy = policy_factory(engines={"nyaasi": {"enabled": True}})
        facade = SearchFacade(profile=_profile(), policy=policy)

        runner = _ScriptedRunner({})
        monkeypatch.setattr(
            "search_engines.worker._ProcessRunner.spawn", runner.spawn
        )

        assert list(facade.search(["", "  ", "!!!"])) == []

    def test_iterable_without_len_succeeds(self, monkeypatch, policy_factory):
        policy = policy_factory(engines={"nyaasi": {"enabled": True}})
        facade = SearchFacade(profile=_profile(), policy=policy)
        runner = _ScriptedRunner({})
        monkeypatch.setattr(
            "search_engines.worker._ProcessRunner.spawn", runner.spawn
        )

        gen = (term for term in [])
        assert list(facade.search(gen)) == []

    def test_empty_results_completes_before_deadline(
        self, monkeypatch, policy_factory
    ):
        """Regression: empty searches must not block until ``request_deadline_s``.

        Previously the streaming consumer kept polling the result queue
        until the full deadline elapsed, so a search for a term that no
        engine recognised would feel frozen for ~120 s in the
        interactive profile. The pool thread now closes the stream when
        the workers finish, so the consumer should exit promptly.
        """
        policy = policy_factory(engines={"nyaasi": {"enabled": True}})
        # Use a generous deadline so a regression would be visible: the
        # assertion below is well under it but well above realistic
        # worker dispatch overhead.
        profile = _profile(
            limits=SearchLimits(
                max_terms=2,
                max_concurrent_jobs=1,
                per_job_timeout_s=2.0,
                request_deadline_s=10.0,
                max_results_per_term=10,
                max_output_bytes=4096,
                max_line_bytes=2048,
                queue_capacity=32,
            )
        )
        facade = SearchFacade(profile=profile, policy=policy)

        runner = _ScriptedRunner({"unknown title": b""})
        monkeypatch.setattr(
            "search_engines.worker._ProcessRunner.spawn", runner.spawn
        )

        start = time.monotonic()
        results = list(facade.search(["unknown title"]))
        elapsed = time.monotonic() - start

        assert results == []
        # The pool should signal completion well before the 10 s
        # deadline. Two seconds is a comfortable margin that still
        # catches the previous "wait the full deadline" behaviour.
        assert elapsed < 2.0, f"empty search took {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# Module level helpers / exports
# ---------------------------------------------------------------------------


class TestExports:
    def test_default_profiles_keys(self):
        assert set(DEFAULT_PROFILES.keys()) == {"interactive", "strict"}

    def test_search_returns_iterator(self, monkeypatch):
        # We can't safely run real subprocess, so just ensure the entry-point
        # constructs a SearchFacade and returns something iterable.
        captured = {}

        original = SearchFacade.search

        def fake_search(self, terms):
            captured["terms"] = list(terms)
            return iter(())

        monkeypatch.setattr(SearchFacade, "search", fake_search)
        result = search(["a", "b"])
        assert list(result) == []
        assert captured["terms"] == ["a", "b"]

    def test_search_strict_returns_list(self, monkeypatch):
        def fake_search(self, terms):
            return iter([{"name": "x"}])

        monkeypatch.setattr(SearchFacade, "search", fake_search)
        out = search_strict(["t"])
        assert out == [{"name": "x"}]


# ---------------------------------------------------------------------------
# SearchSummary
# ---------------------------------------------------------------------------


class TestSearchSummary:
    def test_duration_is_zero_for_same_timestamps(self):
        s = SearchSummary(
            request_id="rid",
            profile="p",
            terms_in=0,
            terms_planned=0,
            terms_dropped=0,
            engines_used=0,
            results_emitted=0,
            duplicates_dropped=0,
            started_at=10.0,
            finished_at=10.0,
        )
        assert s.duration_s == 0.0

    def test_duration_positive(self):
        s = SearchSummary(
            request_id="rid",
            profile="p",
            terms_in=1,
            terms_planned=1,
            terms_dropped=0,
            engines_used=1,
            results_emitted=2,
            duplicates_dropped=0,
            started_at=10.0,
            finished_at=12.5,
        )
        assert s.duration_s == 2.5

    def test_for_profile_classmethod(self):
        facade = SearchFacade.for_profile("strict")
        assert facade.profile.name == "strict"

    def test_for_profile_unknown_falls_back_to_interactive(self):
        facade = SearchFacade.for_profile("does-not-exist")
        assert facade.profile.name == "interactive"
