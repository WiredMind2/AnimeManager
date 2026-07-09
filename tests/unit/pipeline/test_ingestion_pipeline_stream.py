"""Streaming-focused tests for ``IngestionPipeline.stream``."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from application.services.ingestion_pipeline import IngestionPipeline, ProviderSpec
from shared.contracts import AnimeRecord


def _adapter(raw):
    if isinstance(raw, AnimeRecord):
        return raw
    return AnimeRecord(id=int(raw), title=f"anime-{raw}")


def _build_pipeline():
    executor = ThreadPoolExecutor(max_workers=3)
    pipeline = IngestionPipeline(
        max_workers=3,
        provider_timeout_s=2.0,
        executor=executor,
    )
    return pipeline, executor


def test_stream_yields_batches_and_flushes_sink_once():
    pipeline, executor = _build_pipeline()
    try:
        specs = [
            ProviderSpec(name="A", search=lambda _t, _l: [1, 2], adapter=_adapter),
            ProviderSpec(name="B", search=lambda _t, _l: [2, 3], adapter=_adapter),
        ]
        sink_calls = []

        def sink(records):
            sink_calls.append([record.id for record in records])
            return len(records)

        seen_ids = []
        for _provider, records in pipeline.stream(specs, "term", limit=10, sink=sink):
            seen_ids.extend(record.id for record in records)

        assert sorted(set(seen_ids)) == [1, 2, 3]
        assert len(sink_calls) == 1
        assert sorted(sink_calls[0]) == [1, 2, 3]
    finally:
        pipeline.close()
        executor.shutdown(wait=False)


def test_stream_survives_provider_failure_and_keeps_good_records():
    pipeline, executor = _build_pipeline()
    try:
        def _bad(_t, _l):
            raise RuntimeError("boom")

        specs = [
            ProviderSpec(name="Good", search=lambda _t, _l: [5], adapter=_adapter),
            ProviderSpec(name="Bad", search=_bad, adapter=_adapter),
        ]
        sink_ids = []

        for _provider, batch in pipeline.stream(
            specs,
            "term",
            limit=5,
            sink=lambda records: sink_ids.extend([r.id for r in records]) or len(records),
        ):
            assert all(record.id == 5 for record in batch)

        assert sink_ids == [5]
    finally:
        pipeline.close()
        executor.shutdown(wait=False)


def test_stream_with_no_providers_is_empty():
    pipeline, executor = _build_pipeline()
    try:
        assert list(pipeline.stream([], "term", limit=5)) == []
    finally:
        pipeline.close()
        executor.shutdown(wait=False)
