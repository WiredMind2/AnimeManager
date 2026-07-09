"""Tests for background anime metadata hydration."""

from __future__ import annotations

import threading
import time

import pytest

from application.services.anime_hydration import AnimeHydrationService
from domain.entities import AnimeEntity
from domain.errors import NotFoundError


class FakeHydrationPort:
    def __init__(self, *, catalog_ids: set[int] | None = None):
        self.catalog_ids = catalog_ids or {1932}
        self.hydrated: list[int] = []
        self._lock = threading.Lock()
        self._on_hydrate = None

    def catalog_id_exists(self, catalog_id: int) -> bool:
        return int(catalog_id) in self.catalog_ids

    def hydrate_anime(self, catalog_id: int) -> bool:
        catalog_id = int(catalog_id)
        with self._lock:
            self.hydrated.append(catalog_id)
        if self._on_hydrate:
            self._on_hydrate(catalog_id)
        return True


class FakeRepository:
    def __init__(self):
        self._rows: dict[int, AnimeEntity] = {}
        self._lock = threading.Lock()

    def seed(self, catalog_id: int, entity: AnimeEntity | None) -> None:
        with self._lock:
            if entity is None:
                self._rows.pop(int(catalog_id), None)
            else:
                self._rows[int(catalog_id)] = entity

    def anime_row_exists(self, catalog_id: int) -> bool:
        with self._lock:
            entity = self._rows.get(int(catalog_id))
            return entity is not None and bool((entity.title or "").strip())

    def get_anime(self, catalog_id: int):
        with self._lock:
            return self._rows.get(int(catalog_id))


def test_schedule_deduplicates_pending_ids():
    port = FakeHydrationPort()
    repo = FakeRepository()
    service = AnimeHydrationService(port, repo)
    service.start()
    try:
        service.schedule([1932, 1932, 1932])
        time.sleep(0.05)
        assert port.hydrated.count(1932) <= 1
    finally:
        service.stop()


def test_priority_zero_runs_before_background():
    port = FakeHydrationPort(catalog_ids={1, 2})
    repo = FakeRepository()
    service = AnimeHydrationService(port, repo)
    service.start()
    try:
        service.schedule([2], priority=1)
        service.schedule([1], priority=0)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if 1 in port.hydrated:
                break
            time.sleep(0.02)
        assert port.hydrated and port.hydrated[0] == 1
    finally:
        service.stop()


def test_priority_bump_requeues_pending_id():
    port = FakeHydrationPort(catalog_ids={1, 2, 3})
    repo = FakeRepository()
    service = AnimeHydrationService(port, repo)
    service.start()
    try:
        service.schedule([2, 3], priority=1)
        service.schedule([1], priority=1)
        service.schedule([1], priority=0)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if port.hydrated.count(1) >= 1 and 1 == port.hydrated[0]:
                break
            time.sleep(0.02)
        assert port.hydrated[0] == 1
    finally:
        service.stop()


def test_await_hydration_waits_for_repository_row():
    port = FakeHydrationPort()
    repo = FakeRepository()

    def on_hydrate(catalog_id: int):
        repo.seed(
            catalog_id,
            AnimeEntity(
                id=catalog_id,
                title="Skeleton Knight S2",
                title_synonyms=["Skeleton Knight S2"],
            ),
        )

    port._on_hydrate = on_hydrate
    service = AnimeHydrationService(port, repo)
    service.start()
    try:
        ok = service.await_hydration(1932, timeout_s=2.0)
        assert ok is True
        entity = repo.get_anime(1932)
        assert entity is not None
        assert entity.title == "Skeleton Knight S2"
    finally:
        service.stop()


def test_build_details_result_marks_pending_when_still_empty():
    port = FakeHydrationPort()
    repo = FakeRepository()
    service = AnimeHydrationService(port, repo)
    service.start()
    try:
        result = service.build_details_result(1932, await_timeout_s=0.1)
        assert result.entity.id == 1932
        assert result.metadata_pending is True
    finally:
        service.stop()


def test_build_details_result_raises_when_catalog_missing():
    port = FakeHydrationPort(catalog_ids=set())
    repo = FakeRepository()
    service = AnimeHydrationService(port, repo)

    with pytest.raises(NotFoundError):
        service.build_details_result(999)


def test_build_details_result_returns_complete_entity():
    port = FakeHydrationPort(catalog_ids={7})
    repo = FakeRepository()
    repo.seed(7, AnimeEntity(id=7, title="Complete", title_synonyms=["Complete"]))
    service = AnimeHydrationService(port, repo)

    result = service.build_details_result(7, await_timeout_s=0.1)
    assert result.metadata_pending is False
    assert result.entity.title == "Complete"


def test_force_schedule_refreshes_complete_metadata():
    port = FakeHydrationPort(catalog_ids={7})
    repo = FakeRepository()
    repo.seed(7, AnimeEntity(id=7, title="Complete", title_synonyms=["Complete"]))
    service = AnimeHydrationService(port, repo)
    service.start()
    try:
        service.schedule([7], priority=1, force=True)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if port.hydrated.count(7) >= 1:
                break
            time.sleep(0.02)
        assert 7 in port.hydrated
    finally:
        service.stop()


def test_force_schedule_bypasses_recent_success_ttl():
    port = FakeHydrationPort(catalog_ids={7})
    repo = FakeRepository()
    service = AnimeHydrationService(port, repo)
    service.start()
    try:
        service.schedule([7], force=False)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if port.hydrated.count(7) >= 1:
                break
            time.sleep(0.02)
        port.hydrated.clear()
        service.schedule([7], force=False)
        time.sleep(0.05)
        assert port.hydrated.count(7) == 0
        service.schedule([7], force=True)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if port.hydrated.count(7) >= 1:
                break
            time.sleep(0.02)
        assert 7 in port.hydrated
    finally:
        service.stop()


def test_kickoff_detail_refresh_tracks_in_flight():
    port = FakeHydrationPort(catalog_ids={9})
    repo = FakeRepository()
    service = AnimeHydrationService(port, repo)
    service.start()
    seen: list[int] = []
    release = threading.Event()

    def on_hydrate(catalog_id: int) -> None:
        release.wait(timeout=2.0)

    port._on_hydrate = on_hydrate

    def after_hydrate(catalog_id: int) -> None:
        seen.append(catalog_id)

    try:
        service.kickoff_detail_refresh(9, after_hydrate=after_hydrate)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if service.is_detail_refreshing(9):
                break
            time.sleep(0.01)
        assert service.is_detail_refreshing(9) is True
        release.set()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if not service.is_detail_refreshing(9):
                break
            time.sleep(0.02)
        assert service.is_detail_refreshing(9) is False
        assert 9 in port.hydrated
        assert seen == [9]
    finally:
        release.set()
        service.stop()


def test_kickoff_detail_refresh_deduplicates():
    port = FakeHydrationPort(catalog_ids={9})
    repo = FakeRepository()
    service = AnimeHydrationService(port, repo)
    service.start()
    calls: list[int] = []
    release = threading.Event()

    def on_hydrate(catalog_id: int) -> None:
        release.wait(timeout=2.0)

    port._on_hydrate = on_hydrate

    def after_hydrate(catalog_id: int) -> None:
        calls.append(catalog_id)

    try:
        service.kickoff_detail_refresh(9, after_hydrate=after_hydrate)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if service.is_detail_refreshing(9):
                break
            time.sleep(0.01)
        service.kickoff_detail_refresh(9, after_hydrate=after_hydrate)
        release.set()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if not service.is_detail_refreshing(9):
                break
            time.sleep(0.02)
        assert calls.count(9) == 1
    finally:
        release.set()
        service.stop()
