"""Tests for `application.services.ingestion_pipeline.IngestionPipeline`."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from ....shared.contracts import AnimeRecord, IngestionStatus, ProviderName
from ....application.services.ingestion_pipeline import IngestionPipeline, ProviderSpec


def _record(rid, title="t", source=ProviderName.UNKNOWN):
    return AnimeRecord(id=rid, title=title, source_provider=source)


def _adapter(raw):
    if raw is None:
        return None
    if isinstance(raw, AnimeRecord):
        return raw
    return _record(raw)


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
    assert out.records == []
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
    ids = sorted(r.id for r in out.records)
    assert ids == [1, 2, 3, 4]
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
    assert [r.id for r in out.records] == [1, 2]


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

    def sink(records):
        received.extend(records)
        return len(records)

    def s1(terms, limit):
        return [1, 2, 2]

    out = pipeline.run(
        [ProviderSpec(name="s1", search=s1, adapter=_adapter)],
        "term",
        sink=sink,
    )
    assert sorted(r.id for r in received) == [1, 2]
    assert out.status == IngestionStatus.COMPLETE


def test_sink_failure_marks_partial(pipeline):
    def s(terms, limit):
        return [1]

    def sink(records):
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


def test_limit_distributed_across_providers(pipeline):
    seen = {}

    def make_search(name):
        def s(terms, limit):
            seen[name] = limit
            return [(name, i) for i in range(limit)]

        return s

    specs = [
        ProviderSpec(name=name, search=make_search(name), adapter=lambda raw: _record(hash(raw)))
        for name in ("a", "b", "c", "d")
    ]
    pipeline.run(specs, "term", limit=12)
    # 12 / 4 = 3 per provider (floor); should be at least 1
    assert all(v >= 1 for v in seen.values())
    assert max(seen.values()) <= 12
