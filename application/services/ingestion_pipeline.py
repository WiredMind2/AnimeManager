"""
Canonical API->DB ingestion pipeline.

Adapters fan out into provider workers (bounded concurrency), produce
typed ``ProviderAnimePayload`` instances, are deduplicated by external-id
fingerprint, and are handed to the coordinator for catalogue identity
assignment before persistence.
"""

from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from shared.contracts import (
    AnimeRecord,
    IngestionResult,
    IngestionStatus,
    ProviderAnimePayload,
    payload_fingerprint,
)
from shared.telemetry import get_telemetry
from domain.catalog import preferred_catalog_id


ProviderCallable = Callable[[str, int], Iterable[Any]]
RecordAdapter = Callable[[Any], Optional[ProviderAnimePayload]]
PersistenceSink = Callable[[Sequence[ProviderAnimePayload]], int]


@dataclass(frozen=True)
class ProviderSpec:
    """A single provider plus the adapter that normalizes its output."""

    name: str
    search: ProviderCallable
    adapter: RecordAdapter


class IngestionPipeline:
    """Bounded-concurrency search + dedupe + optional payload sink.

    The pipeline is intentionally infrastructure-free: no DB clients, no
    network clients. It accepts callables, so it is trivially testable
    with in-memory fakes and survives provider churn.

    Catalogue identity is **not** resolved here — the coordinator batch-
    assigns ids after collection.
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
    ) -> Iterable[tuple[str, List[ProviderAnimePayload]]]:
        """Yield ``(provider_name, payloads)`` batches as each provider returns."""
        if not providers:
            return
        per_provider_limit = max(1, limit // max(1, len(providers)))
        start_ns = time.perf_counter()
        deadline = start_ns + self._provider_timeout
        futures = {
            self._executor.submit(
                self._run_one, spec, terms, per_provider_limit, deadline
            ): spec
            for spec in providers
        }
        collected: List[ProviderAnimePayload] = []
        seen: set = set()
        try:
            for future in as_completed(futures, timeout=self._provider_timeout):
                spec = futures[future]
                try:
                    batch = future.result(timeout=0)
                except (FutureTimeoutError, Exception):  # noqa: BLE001
                    continue
                fresh: List[ProviderAnimePayload] = []
                for payload in batch:
                    fp = payload_fingerprint(payload)
                    if fp in seen:
                        continue
                    seen.add(fp)
                    fresh.append(payload)
                    collected.append(payload)
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
        limit_per_provider: bool = False,
        parallel: bool = True,
    ) -> IngestionResult:
        if not providers:
            return IngestionResult(status=IngestionStatus.COMPLETE, total_providers=0)

        if limit_per_provider:
            per_provider_limit = max(1, limit)
        else:
            per_provider_limit = max(1, limit // max(1, len(providers)))
        start_ns = time.perf_counter()
        deadline = start_ns + self._provider_timeout
        collected: List[ProviderAnimePayload] = []
        errors: List[str] = []
        failed = 0
        partial = False

        if parallel:
            futures = {
                self._executor.submit(
                    self._run_one, spec, terms, per_provider_limit, deadline
                ): spec
                for spec in providers
            }
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
        else:
            for spec in providers:
                try:
                    collected.extend(
                        self._run_one(spec, terms, per_provider_limit)
                    )
                except Exception as exc:
                    failed += 1
                    partial = True
                    errors.append(f"{spec.name}:{type(exc).__name__}")

        deduped = _deduplicate_payloads(collected)
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
            payloads=deduped,
            failed_providers=failed,
            total_providers=len(providers),
            elapsed_ms=elapsed_ms,
            errors=errors,
            persisted_count=persisted_count,
        )

    def _run_one(
        self,
        spec: ProviderSpec,
        terms: str,
        limit: int,
        deadline: Optional[float] = None,
    ) -> List[ProviderAnimePayload]:
        out: List[ProviderAnimePayload] = []
        if deadline is None:
            deadline = time.perf_counter() + self._provider_timeout
        with self._telemetry.time(f"ingestion.provider.{spec.name}_ms"):
            if time.perf_counter() > deadline:
                self._telemetry.increment("ingestion.provider_deadline_stops")
                return out
            raw_iter = spec.search(terms, limit)
            for idx, raw in enumerate(raw_iter):
                if time.perf_counter() > deadline:
                    self._telemetry.increment("ingestion.provider_deadline_stops")
                    break
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


def _deduplicate_payloads(
    payloads: Sequence[ProviderAnimePayload],
) -> List[ProviderAnimePayload]:
    """Dedupe by external-id fingerprint, preserving first-seen order."""
    seen: set = set()
    out: List[ProviderAnimePayload] = []
    for payload in payloads:
        fp = payload_fingerprint(payload)
        if fp in seen:
            continue
        seen.add(fp)
        out.append(payload)
    return out


def _deduplicate(records: Sequence[AnimeRecord]) -> List[AnimeRecord]:
    """Dedupe by canonical `AnimeRecord.id`, preserving first-seen order."""
    seen: set = set()
    out: List[AnimeRecord] = []
    for record in records:
        rid = record.id
        if rid in seen:
            continue
        seen.add(rid)
        out.append(record)
    return out


def deduplicate_records(records: Sequence[AnimeRecord]) -> List[AnimeRecord]:
    """Dedupe by catalog id, then collapse rows sharing provider external ids.

    When collapsing, prefer the smallest **positive** catalogue id so
    provisional (negative) fingerprints never beat a real ``indexList`` id.
    """
    by_id = _deduplicate(records)
    if len(by_id) <= 1:
        return by_id

    parent: Dict[int, int] = {record.id: record.id for record in by_id}

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: int, b: int) -> None:
        root_a, root_b = find(a), find(b)
        if root_a == root_b:
            return
        winner = preferred_catalog_id(root_a, root_b)
        loser = root_b if winner == root_a else root_a
        parent[loser] = winner

    ext_index: Dict[tuple[str, int], int] = {}
    for record in by_id:
        for key, value in (record.external_ids or {}).items():
            pair = (str(key), int(value))
            if pair in ext_index:
                union(record.id, ext_index[pair])
            else:
                ext_index[pair] = record.id

    winners: Dict[int, AnimeRecord] = {}
    order: List[int] = []
    for record in by_id:
        root = find(record.id)
        candidate = record if record.id == root else replace(record, id=root)
        existing = winners.get(root)
        if existing is None:
            winners[root] = candidate
        else:
            keep_id = preferred_catalog_id(existing.id, candidate.id)
            winners[root] = candidate if candidate.id == keep_id else existing
        if root not in order:
            order.append(root)

    return [winners[root] for root in order]
