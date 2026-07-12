"""Background queue that hydrates incomplete anime catalogue metadata."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, replace
from typing import Callable, Iterable, Optional

from domain.entities import AnimeEntity
from domain.policies.anime_metadata import is_anime_metadata_missing
from ports.interfaces import AnimeHydrationPort, AnimeRepositoryPort

PRIORITY_USER = 0
PRIORITY_PREFETCH = 1

CatalogEnrichFn = Callable[[list[int]], object]


@dataclass(frozen=True)
class AnimeDetailsResult:
    """Anime detail payload plus hydration state for clients."""

    entity: AnimeEntity
    metadata_pending: bool
    metadata_refreshing: bool = False


class AnimeHydrationService:
    """Deduped priority queue for on-demand metadata fetches."""

    _SUCCESS_TTL_S = 300.0
    _DEFAULT_AWAIT_TIMEOUT_S = 12.0
    _DETAIL_REFRESH_TIMEOUT_S = 45.0
    _DEFAULT_POLL_INTERVAL_S = 0.25

    def __init__(
        self,
        hydration_port: AnimeHydrationPort,
        repository: AnimeRepositoryPort,
        *,
        catalog_enrich_fn: Optional[CatalogEnrichFn] = None,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._hydration = hydration_port
        self._repository = repository
        self._catalog_enrich_fn = catalog_enrich_fn
        self._log = log_fn
        self._queue: queue.PriorityQueue[tuple[int, int, int, bool]] = (
            queue.PriorityQueue()
        )
        self._seq = 0
        self._seq_lock = threading.Lock()
        self._pending: set[int] = set()
        self._in_flight: set[int] = set()
        self._best_priority: dict[int, int] = {}
        self._state_lock = threading.Lock()
        self._recent_success: dict[int, float] = {}
        self._detail_refresh_in_flight: set[int] = set()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._worker is not None:
            return
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._run,
            name="AnimeHydrationService",
            daemon=True,
        )
        self._worker.start()

    def stop(self, *, drain: bool = True, timeout: float = 5.0) -> None:
        self._stop_event.set()
        worker = self._worker
        self._worker = None
        if worker is None:
            return
        if drain:
            worker.join(timeout=timeout)

    def schedule(
        self,
        catalog_ids: Iterable[int],
        *,
        priority: int = PRIORITY_PREFETCH,
        force: bool = False,
    ) -> None:
        for raw_id in catalog_ids:
            catalog_id = int(raw_id)
            if catalog_id <= 0:
                continue
            if not self._hydration.catalog_id_exists(catalog_id):
                continue
            if not force:
                if self._repository.anime_row_exists(catalog_id):
                    entity = self._repository.get_anime(catalog_id)
                    if entity is not None and not is_anime_metadata_missing(
                        entity, catalog_id=catalog_id
                    ):
                        continue
                if self._recently_succeeded(catalog_id):
                    continue
            with self._state_lock:
                best = self._best_priority.get(catalog_id)
                if catalog_id in self._in_flight:
                    if best is None or priority < best:
                        self._best_priority[catalog_id] = priority
                    continue
                if catalog_id in self._pending:
                    if best is not None and priority >= best:
                        continue
                    self._best_priority[catalog_id] = priority
                else:
                    self._pending.add(catalog_id)
                    self._best_priority[catalog_id] = priority
            with self._seq_lock:
                self._seq += 1
                seq = self._seq
            self._queue.put((int(priority), seq, catalog_id, bool(force)))

    def schedule_entities(
        self,
        entities: Iterable[AnimeEntity],
        *,
        priority: int = PRIORITY_PREFETCH,
    ) -> None:
        to_schedule: list[int] = []
        for entity in entities:
            if entity is None:
                continue
            catalog_id = entity.id if entity.id > 0 else 0
            if catalog_id <= 0:
                continue
            if is_anime_metadata_missing(entity, catalog_id=catalog_id):
                to_schedule.append(catalog_id)
        if to_schedule:
            self.schedule(to_schedule, priority=priority)

    def await_hydration(
        self,
        catalog_id: int,
        *,
        timeout_s: float | None = None,
    ) -> bool:
        catalog_id = int(catalog_id)
        timeout = (
            float(timeout_s)
            if timeout_s is not None
            else self._DEFAULT_AWAIT_TIMEOUT_S
        )
        self.schedule([catalog_id], priority=PRIORITY_USER)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            entity = self._repository.get_anime(catalog_id)
            if entity is not None and not is_anime_metadata_missing(
                entity, catalog_id=catalog_id
            ):
                return True
            time.sleep(self._DEFAULT_POLL_INTERVAL_S)
        return False

    def build_details_result(
        self,
        catalog_id: int,
        *,
        await_timeout_s: float | None = None,
    ) -> AnimeDetailsResult:
        catalog_id = int(catalog_id)
        entity = self._repository.get_anime(catalog_id)

        if entity is not None and not is_anime_metadata_missing(
            entity, catalog_id=catalog_id
        ):
            return AnimeDetailsResult(entity=entity, metadata_pending=False)

        if not self._hydration.catalog_id_exists(catalog_id):
            from domain.errors import NotFoundError

            raise NotFoundError(f"Anime with id={catalog_id} not found")

        self._schedule_catalog_enrichment([catalog_id])
        self.await_hydration(catalog_id, timeout_s=await_timeout_s)
        entity = self._repository.get_anime(catalog_id)
        if entity is None:
            entity = AnimeEntity(id=catalog_id, title="")
        elif entity.id <= 0:
            entity = replace(entity, id=catalog_id)

        pending = is_anime_metadata_missing(entity, catalog_id=catalog_id)
        return AnimeDetailsResult(entity=entity, metadata_pending=pending)

    def is_detail_refreshing(self, catalog_id: int) -> bool:
        with self._state_lock:
            return int(catalog_id) in self._detail_refresh_in_flight

    def catalog_id_exists(self, catalog_id: int) -> bool:
        return self._hydration.catalog_id_exists(int(catalog_id))

    def kickoff_detail_refresh(
        self,
        catalog_id: int,
        *,
        after_hydrate: Callable[[int], None] | None = None,
        await_timeout_s: float | None = None,
    ) -> None:
        catalog_id = int(catalog_id)
        if catalog_id <= 0:
            return
        if not self._hydration.catalog_id_exists(catalog_id):
            return

        with self._state_lock:
            if catalog_id in self._detail_refresh_in_flight:
                return
            self._detail_refresh_in_flight.add(catalog_id)

        self.schedule([catalog_id], priority=PRIORITY_USER, force=True)

        def _run_refresh() -> None:
            if self._catalog_enrich_fn is not None:
                try:
                    self._catalog_enrich_fn([catalog_id])
                except Exception as exc:
                    if self._log:
                        self._log(
                            f"catalog enrich error for {catalog_id}: {exc}"
                        )
            try:
                self._wait_for_hydration_worker(
                    catalog_id,
                    timeout_s=(
                        await_timeout_s
                        if await_timeout_s is not None
                        else self._DETAIL_REFRESH_TIMEOUT_S
                    ),
                )
            except Exception as exc:
                if self._log:
                    self._log(
                        f"detail refresh error for {catalog_id}: {exc}"
                    )
            finally:
                with self._state_lock:
                    self._detail_refresh_in_flight.discard(catalog_id)

            if after_hydrate is None:
                return

            def _run_extras() -> None:
                try:
                    after_hydrate(catalog_id)
                except Exception as exc:
                    if self._log:
                        self._log(
                            f"detail extras error for {catalog_id}: {exc}"
                        )

            threading.Thread(
                target=_run_extras,
                name=f"detail-extras-{catalog_id}",
                daemon=True,
            ).start()

        threading.Thread(
            target=_run_refresh,
            name=f"detail-refresh-{catalog_id}",
            daemon=True,
        ).start()

    def _wait_for_hydration_worker(
        self,
        catalog_id: int,
        *,
        timeout_s: float | None = None,
    ) -> None:
        catalog_id = int(catalog_id)
        timeout = (
            float(timeout_s)
            if timeout_s is not None
            else self._DEFAULT_AWAIT_TIMEOUT_S
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._state_lock:
                busy = (
                    catalog_id in self._pending
                    or catalog_id in self._in_flight
                )
            if not busy:
                return
            time.sleep(self._DEFAULT_POLL_INTERVAL_S)

    def _schedule_catalog_enrichment(self, catalog_ids: list[int]) -> None:
        if self._catalog_enrich_fn is None or not catalog_ids:
            return
        ids = list(catalog_ids)
        threading.Thread(
            target=lambda: self._catalog_enrich_fn(ids),
            name="catalog-enrich-detail",
            daemon=True,
        ).start()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                _priority, _seq, catalog_id, force = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue

            if not force:
                entity = self._repository.get_anime(catalog_id)
                if entity is not None and not is_anime_metadata_missing(
                    entity, catalog_id=catalog_id
                ):
                    with self._state_lock:
                        self._pending.discard(catalog_id)
                        self._best_priority.pop(catalog_id, None)
                    continue

            with self._state_lock:
                self._pending.discard(catalog_id)
                self._in_flight.add(catalog_id)

            try:
                ok = self._hydration.hydrate_anime(catalog_id)
                if ok:
                    with self._state_lock:
                        self._recent_success[catalog_id] = time.monotonic()
            except Exception as exc:
                if self._log:
                    self._log(f"hydration worker error for {catalog_id}: {exc}")
            finally:
                with self._state_lock:
                    self._in_flight.discard(catalog_id)
                    self._best_priority.pop(catalog_id, None)

    def _recently_succeeded(self, catalog_id: int) -> bool:
        with self._state_lock:
            ts = self._recent_success.get(catalog_id)
            if ts is None:
                return False
            if time.monotonic() - ts > self._SUCCESS_TTL_S:
                self._recent_success.pop(catalog_id, None)
                return False
            return True
