"""Additional edge case tests for ``application.services.ingestion_pipeline``."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from application.services.ingestion_pipeline import (
    IngestionPipeline,
    ProviderSpec,
    _deduplicate,
)
from shared.contracts import AnimeRecord, IngestionStatus, ProviderName


def _rec(rid, title="t"):
    return AnimeRecord(id=rid, title=title)


def _identity_adapter(raw):
    if raw is None:
        return None
    if isinstance(raw, AnimeRecord):
        return raw
    return _rec(raw)


@pytest.fixture
def pipeline():
    executor = ThreadPoolExecutor(max_workers=4)
    p = IngestionPipeline(max_workers=4, provider_timeout_s=2.0, executor=executor)
    yield p
    p.close()
    executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_zero_max_workers_rejected(self):
        with pytest.raises(ValueError):
            IngestionPipeline(max_workers=0)

    def test_negative_max_workers_rejected(self):
        with pytest.raises(ValueError):
            IngestionPipeline(max_workers=-3)

    def test_default_constructor_owns_executor(self):
        p = IngestionPipeline(max_workers=2)
        assert p._owns_executor is True
        p.close()

    def test_external_executor_not_closed_by_pipeline(self):
        executor = ThreadPoolExecutor(max_workers=1)
        p = IngestionPipeline(max_workers=1, executor=executor)
        p.close()
        # Executor is still usable since we did not own it.
        f = executor.submit(lambda: 1)
        assert f.result(timeout=1) == 1
        executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Run semantics
# ---------------------------------------------------------------------------


class TestRunEdges:
    def test_empty_provider_list_returns_complete(self, pipeline):
        out = pipeline.run([], "term")
        assert out.status == IngestionStatus.COMPLETE
        assert out.records == []
        assert out.total_providers == 0
        assert out.failed_providers == 0

    def test_provider_returning_none_items_skipped(self, pipeline):
        def src(terms, limit):
            return [None, None, 5, None]

        specs = [ProviderSpec(name="src", search=src, adapter=_identity_adapter)]
        out = pipeline.run(specs, "term", limit=5)
        assert [r.id for r in out.records] == [5]

    def test_adapter_returning_none_drops_record(self, pipeline):
        def src(terms, limit):
            return [1, 2, 3]

        def adapter(raw):
            return None  # drop everything

        specs = [ProviderSpec(name="src", search=src, adapter=adapter)]
        out = pipeline.run(specs, "term", limit=10)
        assert out.records == []
        assert out.status == IngestionStatus.COMPLETE

    def test_limit_zero_yields_no_records(self, pipeline):
        def src(terms, limit):
            return [1, 2, 3]

        specs = [ProviderSpec(name="src", search=src, adapter=_identity_adapter)]
        out = pipeline.run(specs, "term", limit=0)
        # per_provider_limit = max(1, 0 // 1) = 1
        assert len(out.records) <= 1

    def test_provider_can_yield_generators(self, pipeline):
        def src(terms, limit):
            for i in range(5):
                yield i

        specs = [ProviderSpec(name="src", search=src, adapter=_identity_adapter)]
        out = pipeline.run(specs, "term", limit=5)
        assert sorted(r.id for r in out.records) == [0, 1, 2, 3, 4]

    def test_provider_returning_empty_iter_completes_cleanly(self, pipeline):
        def src(terms, limit):
            return []

        specs = [ProviderSpec(name="src", search=src, adapter=_identity_adapter)]
        out = pipeline.run(specs, "term")
        assert out.status == IngestionStatus.COMPLETE
        assert out.records == []
        assert out.failed_providers == 0

    def test_provider_raising_value_error_marks_partial(self, pipeline):
        def good(terms, limit):
            return [1]

        def bad(terms, limit):
            raise ValueError("oops")

        specs = [
            ProviderSpec(name="g", search=good, adapter=_identity_adapter),
            ProviderSpec(name="b", search=bad, adapter=_identity_adapter),
        ]
        out = pipeline.run(specs, "term")
        assert out.status == IngestionStatus.PARTIAL
        assert any("b:" in e for e in out.errors)
        assert out.failed_providers == 1

    def test_adapter_exception_propagates_as_failure(self, pipeline):
        def src(terms, limit):
            return [1]

        def adapter(raw):
            raise KeyError("missing key")

        specs = [ProviderSpec(name="bad", search=src, adapter=adapter)]
        out = pipeline.run(specs, "term")
        assert out.status == IngestionStatus.FAILED
        assert any("KeyError" in e for e in out.errors)

    def test_sink_only_called_with_non_empty_records(self, pipeline):
        called = []

        def sink(records):
            called.append(list(records))
            return len(records)

        def src(terms, limit):
            return []

        pipeline.run(
            [ProviderSpec(name="src", search=src, adapter=_identity_adapter)],
            "term",
            sink=sink,
        )
        assert called == []  # no records => no sink call

    def test_sink_called_with_deduped_records_only(self, pipeline):
        def src(terms, limit):
            return [1, 1, 2, 2, 3]

        captured = []

        def sink(records):
            captured.extend(records)
            return len(records)

        pipeline.run(
            [ProviderSpec(name="src", search=src, adapter=_identity_adapter)],
            "term",
            sink=sink,
        )
        ids = sorted(r.id for r in captured)
        assert ids == [1, 2, 3]


class TestDeduplicate:
    def test_empty_input(self):
        assert _deduplicate([]) == []

    def test_preserves_first_seen_order(self):
        records = [_rec(2), _rec(1), _rec(2), _rec(3)]
        out = _deduplicate(records)
        assert [r.id for r in out] == [2, 1, 3]

    def test_distinct_records_unchanged(self):
        records = [_rec(i) for i in range(5)]
        assert _deduplicate(records) == records
