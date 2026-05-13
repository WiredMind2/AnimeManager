"""Public orchestration entry-point for the torrent search subsystem.

``SearchFacade`` composes the pipeline stages (planner, engine policy,
worker pool, parser, dedupe, ranking, streaming) into a single, profile
driven API. Callers (GUI and REST API) only depend on this module; the
nova3 vendor code is invoked exclusively through :mod:`search_engines.worker`.

Two convenience APIs are exposed:

* :class:`SearchFacade` -- the rich, profile-aware orchestrator.
* :func:`search` -- a backward compatible generator that mimics the
  legacy ``search_engines.search(terms)`` signature.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, List, Optional, Sequence

from .config import (
    DEFAULT_PROFILE,
    DEFAULT_PROFILES,
    INTERACTIVE_PROFILE,
    STRICT_PROFILE,
    SearchProfile,
    load_profile,
)
from .dedupe import ResultDeduper
from .engine_policy import EnginePolicy, get_default_policy
from .parser import ResultParser, TorrentResult
from .planner import QueryPlanner, plan_terms
from .ranking import sort_results
from .telemetry import get_metrics, new_request_id, structured_log
from .worker import JobOutcome, NovaWorker, SearchJob

_SENTINEL = object()


@dataclass
class SearchSummary:
    """Final accounting for a completed search request.

    Mirrors operational dashboards: total counts and outcomes per engine
    are surfaced so callers can react to partial failures (e.g. log a
    warning if more than half the engines timed out).
    """

    request_id: str
    profile: str
    terms_in: int
    terms_planned: int
    terms_dropped: int
    engines_used: int
    results_emitted: int
    duplicates_dropped: int
    started_at: float
    finished_at: float
    outcomes: List[JobOutcome] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return self.finished_at - self.started_at


class _ResultStream:
    """Bounded, thread-safe queue used to back the streaming generator."""

    def __init__(self, capacity: int) -> None:
        self._queue: queue.Queue = queue.Queue(maxsize=capacity)
        self._closed = False

    def put(self, item: object) -> None:
        if self._closed:
            return
        # Block briefly so a runaway worker cannot pin memory if the
        # consumer stalls; if the queue stays full we drop newest items
        # rather than crash.
        try:
            self._queue.put(item, timeout=1.0)
        except queue.Full:
            get_metrics().incr("stream_dropped_full")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._queue.put_nowait(_SENTINEL)
        except queue.Full:
            # Make room by discarding one item; the consumer will still
            # see the sentinel afterwards.
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(_SENTINEL)
            except queue.Full:
                pass

    def iter_until_done(self, deadline: float) -> Iterator[object]:
        while True:
            timeout = max(0.0, deadline - time.monotonic())
            try:
                item = self._queue.get(timeout=timeout if timeout > 0 else 0.05)
            except queue.Empty:
                if time.monotonic() >= deadline:
                    return
                continue
            if item is _SENTINEL:
                return
            yield item


class SearchFacade:
    """Profile-aware orchestrator for nova3 torrent search."""

    def __init__(
        self,
        profile: Optional[SearchProfile] = None,
        policy: Optional[EnginePolicy] = None,
    ) -> None:
        self._profile = profile or load_profile(DEFAULT_PROFILE)
        self._policy = policy or get_default_policy()
        self._metrics = get_metrics()

    @property
    def profile(self) -> SearchProfile:
        return self._profile

    def search(self, terms: Sequence[str]) -> Iterator[dict]:
        """Stream torrent dicts compatible with the legacy consumer.

        Each yielded dict mirrors the keys produced by the previous
        wrapper: ``link``, ``name``, ``size``, ``seeds``, ``leech``,
        ``engine_url``, ``desc_link``. An ``infohash`` field is added
        for downstream dedupe.
        """
        for result in self.search_results(terms):
            yield result.as_dict()

    def search_results(
        self,
        terms: Sequence[str],
        *,
        on_outcome: Optional[Callable[[JobOutcome], None]] = None,
    ) -> Iterator[TorrentResult]:
        """Stream :class:`TorrentResult` records under the active profile."""
        request_id = new_request_id()
        plan = plan_terms(terms, self._profile.limits)
        candidate_engines = self._policy.filter(
            self._policy.known_engines(),
            self._profile,
            request_id=request_id,
        )

        started_at = time.monotonic()
        structured_log(
            "request_start",
            request_id=request_id,
            profile=self._profile.name,
            terms_in=len(terms) if hasattr(terms, "__len__") else -1,
            terms_planned=len(plan.terms),
            engines=len(candidate_engines),
        )

        if not plan.terms or not candidate_engines:
            structured_log(
                "request_empty",
                request_id=request_id,
                profile=self._profile.name,
                reason="no_terms" if not plan.terms else "no_engines",
            )
            yield from ()
            return

        parser = ResultParser(max_line_bytes=self._profile.limits.max_line_bytes)
        deduper = ResultDeduper()
        cancel = threading.Event()
        stream = _ResultStream(self._profile.limits.queue_capacity)
        outcomes: List[JobOutcome] = []
        results_emitted = 0
        max_results = self._profile.limits.max_results

        def sink(result: TorrentResult, job: SearchJob) -> None:
            nonlocal results_emitted
            if cancel.is_set():
                return
            if deduper.register(result) is None:
                self._metrics.incr("dedupe_dropped")
                return
            stream.put(result)
            results_emitted += 1
            if results_emitted >= max_results:
                cancel.set()

        jobs = [
            SearchJob(
                job_id=f"{request_id}-{idx}",
                term=plan.terms[idx].normalized,
                engines=list(candidate_engines),
                category=self._profile.category,
            )
            for idx in range(len(plan.terms))
        ]

        request_deadline = time.monotonic() + self._profile.limits.request_deadline_s
        pool_thread = threading.Thread(
            target=self._run_pool,
            name=f"search-pool-{request_id}",
            args=(jobs, parser, sink, cancel, request_deadline, outcomes, request_id, stream),
            daemon=True,
        )
        pool_thread.start()

        try:
            if self._profile.rank_results:
                buffered: List[TorrentResult] = []
                for item in stream.iter_until_done(request_deadline):
                    buffered.append(item)  # type: ignore[arg-type]
                for ordered in sort_results(buffered):
                    yield ordered
            else:
                for item in stream.iter_until_done(request_deadline):
                    yield item  # type: ignore[misc]
        finally:
            cancel.set()
            stream.close()
            pool_thread.join(timeout=2.0)
            finished_at = time.monotonic()
            summary = SearchSummary(
                request_id=request_id,
                profile=self._profile.name,
                terms_in=len(terms) if hasattr(terms, "__len__") else -1,
                terms_planned=len(plan.terms),
                terms_dropped=len(plan.dropped),
                engines_used=len(candidate_engines),
                results_emitted=results_emitted,
                duplicates_dropped=len(deduper) - results_emitted
                if len(deduper) >= results_emitted
                else 0,
                started_at=started_at,
                finished_at=finished_at,
                outcomes=list(outcomes),
            )
            structured_log(
                "request_done",
                request_id=request_id,
                profile=self._profile.name,
                duration_ms=int(summary.duration_s * 1000),
                results=results_emitted,
                timeouts=sum(
                    1 for o in outcomes if o.exit_reason.startswith("timed_out")
                ),
                jobs=len(outcomes),
            )
            if on_outcome is not None:
                for outcome in outcomes:
                    try:
                        on_outcome(outcome)
                    except Exception:  # pragma: no cover - defensive
                        pass

    def _run_pool(
        self,
        jobs: List[SearchJob],
        parser: ResultParser,
        sink: Callable[[TorrentResult, SearchJob], None],
        cancel: threading.Event,
        deadline: float,
        outcomes: List[JobOutcome],
        request_id: str,
        stream: "_ResultStream",
    ) -> None:
        threads: List[threading.Thread] = []
        max_concurrent = max(1, self._profile.limits.max_concurrent_jobs)
        semaphore = threading.BoundedSemaphore(max_concurrent)
        outcome_lock = threading.Lock()

        def runner(job: SearchJob) -> None:
            try:
                semaphore.acquire()
                if cancel.is_set() or time.monotonic() >= deadline:
                    with outcome_lock:
                        outcomes.append(
                            JobOutcome(
                                job_id=job.job_id,
                                term=job.term,
                                started_at=time.monotonic(),
                                finished_at=time.monotonic(),
                                exit_reason="skipped_after_deadline",
                                exit_code=None,
                                rows_emitted=0,
                                bytes_read=0,
                                stderr_excerpt="",
                            )
                        )
                    return
                worker = NovaWorker(
                    self._profile,
                    parser,
                    sink,
                    cancel,
                    request_id=request_id,
                )
                outcome = worker.run(job, deadline)
                with outcome_lock:
                    outcomes.append(outcome)
            finally:
                semaphore.release()

        try:
            for job in jobs:
                thread = threading.Thread(
                    target=runner,
                    args=(job,),
                    name=f"nova-{job.job_id}",
                    daemon=True,
                )
                thread.start()
                threads.append(thread)

            for thread in threads:
                remaining = max(0.0, deadline - time.monotonic())
                thread.join(timeout=remaining + 1.0)
        finally:
            # Wake the consumer immediately once every worker has finished
            # (or the deadline elapsed). Without this signal the streaming
            # generator would keep polling the result queue until the full
            # ``request_deadline_s`` budget is consumed even when the pool
            # is already idle -- which makes empty-result searches feel
            # frozen for the entire deadline. ``stream.close()`` is
            # idempotent so the outer ``finally`` block can still call it
            # safely without enqueuing duplicate sentinels.
            stream.close()

    @classmethod
    def for_profile(cls, name: str) -> "SearchFacade":
        return cls(profile=load_profile(name))


def search(terms: Iterable[str]) -> Iterator[dict]:
    """Backward-compatible streaming search.

    Mirrors the legacy ``search_engines.search`` signature so existing
    callers do not need to change. Internally delegates to
    :class:`SearchFacade` with the interactive profile.
    """
    facade = SearchFacade(profile=INTERACTIVE_PROFILE)
    return facade.search(list(terms))


def search_strict(terms: Iterable[str]) -> List[dict]:
    """Materialized search that uses the ``strict`` API profile.

    Returns a ranked list rather than a generator so REST handlers can
    serialize it directly. Honors the strict profile's caps.
    """
    facade = SearchFacade(profile=STRICT_PROFILE)
    return list(facade.search(list(terms)))


__all__ = [
    "SearchFacade",
    "SearchSummary",
    "search",
    "search_strict",
    "DEFAULT_PROFILES",
    "INTERACTIVE_PROFILE",
    "STRICT_PROFILE",
]
