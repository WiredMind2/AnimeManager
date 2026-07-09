"""Smoke test: library search must return anime data."""

from __future__ import annotations

import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from adapters.metadata.api_coordinator_adapter import ApiCoordinatorAdapter
from adapters.persistence.anime_repository import AnimeRepositoryAdapter
from application.services.anime_service import AnimeApplicationService
from composition.bootstrap import bootstrap_embedded_deps
from domain.dto import SearchRequest
from domain.entities import AnimeEntity


def test_unit_path() -> None:
    class LocalRepo:
        def search(self, q, limit=50):
            return []

        def list_by_genre(self, genre, limit=50):
            return []

        def list_by_airing_season(self, *a, **k):
            return []

    class RemoteProvider:
        def stream_search(self, q, limit=50):
            yield AnimeEntity(id=1001, title="Naruto", status="FINISHED")
            yield AnimeEntity(id=1002, title="Naruto Shippuden", status="FINISHED")

        def search(self, q, limit=50):
            return list(self.stream_search(q, limit))

    svc = AnimeApplicationService(LocalRepo(), RemoteProvider(), object(), object())
    sync = svc.search_anime(SearchRequest(query="naruto", limit=10))
    stream = list(svc.stream_search_anime(SearchRequest(query="naruto", limit=10)))
    print(f"Unit sync: {len(sync)} -> {[e.title for e in sync]}")
    print(f"Unit stream: {len(stream)} -> {[e.title for e in stream]}")
    if not sync or not stream:
        raise AssertionError("unit path returned no data")


def test_live_service_stream(timeout_s: float = 90.0) -> None:
    def run():
        deps = bootstrap_embedded_deps()
        repo = AnimeRepositoryAdapter(deps.db_manager, deps.config, api=deps.api)
        meta = ApiCoordinatorAdapter(deps.api, deps.db_manager)
        svc = AnimeApplicationService(repo, meta, object(), object())
        return [
            (entity.id, entity.title)
            for entity in svc.stream_search_anime(
                SearchRequest(query="naruto", limit=10)
            )
        ]

    started = time.time()
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            rows = pool.submit(run).result(timeout=timeout_s)
        except FuturesTimeout as exc:
            raise TimeoutError(
                f"live service stream timed out after {timeout_s}s"
            ) from exc

    elapsed = time.time() - started
    print(f"Live service stream: {len(rows)} results in {elapsed:.1f}s")
    for row in rows[:5]:
        print(f"  id={row[0]} title={row[1]!r}")

    if not rows:
        raise AssertionError("live service stream returned no data")


def main() -> int:
    print("=== Unit path ===")
    test_unit_path()
    print("Unit path: PASS\n")

    print("=== Live service stream (real providers) ===")
    try:
        test_live_service_stream()
    except TimeoutError as exc:
        print(f"Live service: FAIL - {exc}")
        return 2
    print("Live service: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
