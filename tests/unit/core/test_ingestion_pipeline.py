"""Tests for `application.services.ingestion_pipeline.IngestionPipeline`."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from ....shared.contracts import (
    IngestionStatus,
    ProviderAnimePayload,
    ProviderName,
)
from ....application.services.ingestion_pipeline import IngestionPipeline, ProviderSpec


def _payload(raw, title="t", source=ProviderName.UNKNOWN):
    if isinstance(raw, ProviderAnimePayload):
        return raw
    return ProviderAnimePayload(
        title=title,
        external_ids={"mal_id": int(raw)},
        source_provider=source,
    )


def _adapter(raw):
    if raw is None:
        return None
    return _payload(raw)


@pytest.fixture
def pipeline():
    executor = ThreadPoolExecutor(max_workers=4)
    p = IngestionPipeline(max_workers=4, provider_timeout_s=2.0, executor=executor)
    yield p
    p.close()
    executor.shutdown(wait=True)


def test_no_providers_returns_complete(pipeline):
    out = pipeline.run([], "anything")
    assert out.status == IngestionStatus.COMPLETE
    assert out.payloads == []
    assert out.total_providers == 0


def test_collects_and_dedupes(pipeline):
    def s1(terms, limit):
        return [1, 2, 3]

    def s2(terms, limit):
        return [3, 4]

    specs = [
        ProviderSpec(name="s1", search=s1, adapter=_adapter),
        ProviderSpec(name="s2", search=s2, adapter=_adapter),
    ]
    out = pipeline.run(specs, "term", limit=10)
    mal_ids = sorted(p.external_ids["mal_id"] for p in out.payloads)
    assert mal_ids == [1, 2, 3, 4]
    assert out.status == IngestionStatus.COMPLETE
    assert out.failed_providers == 0


def test_failed_provider_marks_partial(pipeline):
    def good(terms, limit):
        return [1, 2]

    def bad(terms, limit):
        raise RuntimeError("boom")

    specs = [
        ProviderSpec(name="good", search=good, adapter=_adapter),
        ProviderSpec(name="bad", search=bad, adapter=_adapter),
    ]
    out = pipeline.run(specs, "term", limit=10)
    assert out.status == IngestionStatus.PARTIAL
    assert out.failed_providers == 1
    assert any(e.startswith("bad:") for e in out.errors)
    assert [p.external_ids["mal_id"] for p in out.payloads] == [1, 2]


def test_all_providers_fail_marks_failed(pipeline):
    def bad(terms, limit):
        raise RuntimeError("boom")

    specs = [
        ProviderSpec(name=f"bad{i}", search=bad, adapter=_adapter) for i in range(3)
    ]
    out = pipeline.run(specs, "term", limit=10)
    assert out.status == IngestionStatus.FAILED
    assert out.failed_providers == 3


def test_sink_receives_dedup_records(pipeline):
    received = []

    def sink(payloads):
        received.extend(payloads)
        return len(payloads)

    def s1(terms, limit):
        return [1, 2, 2]

    out = pipeline.run(
        [ProviderSpec(name="s1", search=s1, adapter=_adapter)],
        "term",
        sink=sink,
    )
    assert sorted(p.external_ids["mal_id"] for p in received) == [1, 2]
    assert out.status == IngestionStatus.COMPLETE


def test_sink_failure_marks_partial(pipeline):
    def s(terms, limit):
        return [1]

    def sink(payloads):
        raise RuntimeError("flush failed")

    out = pipeline.run(
        [ProviderSpec(name="s", search=s, adapter=_adapter)],
        "term",
        sink=sink,
    )
    assert out.status == IngestionStatus.PARTIAL
    assert any(e.startswith("sink:") for e in out.errors)


def test_respects_provider_timeout():
    executor = ThreadPoolExecutor(max_workers=2)
    try:
        pipe = IngestionPipeline(
            max_workers=2,
            provider_timeout_s=0.2,
            executor=executor,
        )
        try:
            def slow(terms, limit):
                time.sleep(2)
                return [1]

            specs = [ProviderSpec(name="slow", search=slow, adapter=_adapter)]
            out = pipe.run(specs, "term", limit=1)
            assert out.status in {IngestionStatus.PARTIAL, IngestionStatus.FAILED}
            assert out.failed_providers >= 1
        finally:
            pipe.close()
    finally:
        executor.shutdown(wait=False)


def test_run_one_stops_iterating_slow_generator_after_deadline():
    """A paginating provider must release the worker once the deadline passes.

    Abandoned futures used to keep iterating (and fetching pages) for
    minutes, hogging the shared executor and starving later requests.
    """
    pipe = IngestionPipeline(max_workers=1, provider_timeout_s=0.2)
    try:
        pulled = []

        def slow_gen(terms, limit):
            for i in range(100):
                pulled.append(i)
                yield i
                time.sleep(0.05)

        spec = ProviderSpec(name="slow", search=slow_gen, adapter=_adapter)
        start = time.perf_counter()
        out = pipe._run_one(spec, "term", 100)
        elapsed = time.perf_counter() - start
        assert len(pulled) < 100
        assert len(out) < 100
        assert elapsed < 2.0
    finally:
        pipe.close()


def test_run_one_bails_immediately_when_deadline_already_passed():
    pipe = IngestionPipeline(max_workers=1, provider_timeout_s=5.0)
    try:
        called = []

        def search(terms, limit):
            called.append(True)
            return [1, 2, 3]

        spec = ProviderSpec(name="s", search=search, adapter=_adapter)
        out = pipe._run_one(spec, "term", 3, deadline=time.perf_counter() - 1.0)
        assert out == []
        assert not called
    finally:
        pipe.close()


def test_abandoned_slow_provider_frees_worker_for_next_run():
    """After a timed-out run, the single worker must become available again."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        pipe = IngestionPipeline(
            max_workers=1,
            provider_timeout_s=0.3,
            executor=executor,
        )
        try:
            def slow_gen(terms, limit):
                for i in range(200):
                    yield i
                    time.sleep(0.05)

            def fast(terms, limit):
                return [1]

            start = time.perf_counter()
            out1 = pipe.run(
                [ProviderSpec(name="slow", search=slow_gen, adapter=_adapter)],
                "term",
                limit=200,
            )
            # The provider self-terminates at the deadline: the run ends
            # promptly with whatever was collected instead of hogging the
            # worker for the full 200-item iteration (~10s).
            assert time.perf_counter() - start < 2.0
            assert len(out1.payloads) < 200

            out2 = pipe.run(
                [ProviderSpec(name="fast", search=fast, adapter=_adapter)],
                "term",
                limit=1,
            )
            assert [p.external_ids["mal_id"] for p in out2.payloads] == [1]
        finally:
            pipe.close()
    finally:
        executor.shutdown(wait=True)


def test_limit_distributed_across_providers(pipeline):
    seen = {}

    def make_search(name):
        def s(terms, limit):
            seen[name] = limit
            return [(name, i) for i in range(limit)]

        return s

    def adapter(raw):
        name, idx = raw
        return ProviderAnimePayload(
            title=f"{name}-{idx}",
            external_ids={"mal_id": hash((name, idx)) % 1_000_000},
            source_provider=ProviderName.UNKNOWN,
        )

    specs = [
        ProviderSpec(name=name, search=make_search(name), adapter=adapter)
        for name in ("a", "b", "c", "d")
    ]
    pipeline.run(specs, "term", limit=12)
    # 12 / 4 = 3 per provider (floor); should be at least 1
    assert all(v >= 1 for v in seen.values())
    assert max(seen.values()) <= 12
