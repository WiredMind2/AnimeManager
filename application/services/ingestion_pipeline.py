"""
Canonical API->DB ingestion pipeline.

Adapters fan out into provider workers (bounded concurrency), produce
typed `AnimeRecord` instances, are deduplicated by id, and then handed
to a single persistence sink. The pipeline is the only legal way for
API-originated data to reach the database.
"""

from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Optional, Sequence

from shared.contracts import AnimeRecord, IngestionResult, IngestionStatus
from shared.telemetry import get_telemetry


ProviderCallable = Callable[[str, int], Iterable[Any]]
RecordAdapter = Callable[[Any], Optional[AnimeRecord]]
PersistenceSink = Callable[[Sequence[AnimeRecord]], int]


@dataclass(frozen=True)
class ProviderSpec:
    """A single provider plus the adapter that normalizes its output."""

    name: str
    search: ProviderCallable
    adapter: RecordAdapter


class IngestionPipeline:
    """Bounded-concurrency search + dedupe + persistence sink.

    The pipeline is intentionally infrastructure-free: no DB clients, no
    network clients. It accepts callables, so it is trivially testable
    with in-memory fakes and survives provider churn.
    """

    def __init__(
        self,
        *,
        max_workers: int = 4,
        provider_timeout_s: float = 20.0,
        executor: Optional[ThreadPoolExecutor] = None,
    ) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        self._max_workers = max_workers
        self._provider_timeout = provider_timeout_s
        self._executor = executor or ThreadPoolExecutor(max_workers=max_workers)
        self._owns_executor = executor is None
        self._telemetry = get_telemetry()

    def close(self) -> None:
        if self._owns_executor and self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None  # type: ignore[assignment]

    def stream(
        self,
        providers: Sequence[ProviderSpec],
        terms: str,
        *,
        limit: int = 50,
        sink: Optional[PersistenceSink] = None,
    ) -> Iterable[tuple[str, List[AnimeRecord]]]:
        """Yield ``(provider_name, records)`` batches as each provider returns.

        Identical concurrency / dedupe semantics to :meth:`run`, but the
        caller is fed partial results as soon as the first provider
        finishes instead of waiting for the slowest one. The
        persistence sink, when provided, runs at the very end with the
        full deduplicated set -- callers that want per-batch persistence
        can wire their own sink into the consumer loop.
        """
        if not providers:
            return
        per_provider_limit = max(1, limit // max(1, len(providers)))
        start_ns = time.perf_counter()
        futures = {
            self._executor.submit(self._run_one, spec, terms, per_provider_limit): spec
            for spec in providers
        }
        collected: List[AnimeRecord] = []
        seen_ids: set = set()
        try:
            for future in as_completed(futures, timeout=self._provider_timeout):
                spec = futures[future]
                try:
                    batch = future.result(timeout=0)
                except (FutureTimeoutError, Exception):  # noqa: BLE001
                    continue
                fresh: List[AnimeRecord] = []
                for record in batch:
                    rid = record.id
                    if rid in seen_ids:
                        continue
                    seen_ids.add(rid)
                    fresh.append(record)
                    collected.append(record)
                if fresh:
                    yield spec.name, fresh
        except FutureTimeoutError:
            self._cancel_pending(futures)

        elapsed_ms = int((time.perf_counter() - start_ns) * 1000)
        self._telemetry.record_ms("ingestion.total_ms", elapsed_ms)
        self._telemetry.increment(
            "ingestion.records_collected", len(collected)
        )
        if sink is not None and collected:
            try:
                with self._telemetry.time("ingestion.sink_flush_ms"):
                    persisted_count = sink(collected)
                self._telemetry.increment(
                    "ingestion.records_persisted", persisted_count
                )
            except Exception:  # noqa: BLE001 - best-effort persistence
                pass

    def run(
        self,
        providers: Sequence[ProviderSpec],
        terms: str,
        *,
        limit: int = 50,
        sink: Optional[PersistenceSink] = None,
    ) -> IngestionResult:
        if not providers:
            return IngestionResult(status=IngestionStatus.COMPLETE, total_providers=0)

        per_provider_limit = max(1, limit // max(1, len(providers)))
        start_ns = time.perf_counter()
        futures = {
            self._executor.submit(self._run_one, spec, terms, per_provider_limit): spec
            for spec in providers
        }
        collected: List[AnimeRecord] = []
        errors: List[str] = []
        failed = 0
        partial = False
        try:
            for future in as_completed(futures, timeout=self._provider_timeout):
                spec = futures[future]
                try:
                    collected.extend(future.result(timeout=0))
                except FutureTimeoutError:
                    failed += 1
                    partial = True
                    errors.append(f"{spec.name}:timeout")
                except Exception as exc:
                    failed += 1
                    errors.append(f"{spec.name}:{type(exc).__name__}")
        except FutureTimeoutError:
            partial = True
            for future, spec in futures.items():
                if not future.done():
                    failed += 1
                    errors.append(f"{spec.name}:deadline")
            self._cancel_pending(futures)

        deduped = _deduplicate(collected)
        persisted_count = 0
        if sink is not None and deduped:
            try:
                with self._telemetry.time("ingestion.sink_flush_ms"):
                    persisted_count = sink(deduped)
            except Exception as exc:
                errors.append(f"sink:{type(exc).__name__}")
                partial = True

        elapsed_ms = int((time.perf_counter() - start_ns) * 1000)
        self._telemetry.record_ms("ingestion.total_ms", elapsed_ms)
        self._telemetry.increment("ingestion.records_collected", len(collected))
        self._telemetry.increment("ingestion.records_persisted", persisted_count)
        if failed:
            self._telemetry.increment("ingestion.failed_providers", failed)

        status = IngestionStatus.COMPLETE
        if not deduped and failed == len(providers):
            status = IngestionStatus.FAILED
        elif partial or failed:
            status = IngestionStatus.PARTIAL

        return IngestionResult(
            status=status,
            records=deduped,
            failed_providers=failed,
            total_providers=len(providers),
            elapsed_ms=elapsed_ms,
            errors=errors,
        )

    def _run_one(self, spec: ProviderSpec, terms: str, limit: int) -> List[AnimeRecord]:
        out: List[AnimeRecord] = []
        with self._telemetry.time(f"ingestion.provider.{spec.name}_ms"):
            raw_iter = spec.search(terms, limit)
            for idx, raw in enumerate(raw_iter):
                if raw is None:
                    continue
                normalized = spec.adapter(raw)
                if normalized is None:
                    continue
                out.append(normalized)
                if idx + 1 >= limit:
                    break
        return out

    @staticmethod
    def _cancel_pending(futures: "dict[Future, ProviderSpec]") -> None:
        for future in futures:
            if not future.done():
                future.cancel()


def _deduplicate(records: Sequence[AnimeRecord]) -> List[AnimeRecord]:
    """Dedupe by `AnimeRecord.id`, preserving first-seen order."""
    seen: set = set()
    out: List[AnimeRecord] = []
    for record in records:
        rid = record.id
        if rid in seen:
            continue
        seen.add(rid)
        out.append(record)
    return out
