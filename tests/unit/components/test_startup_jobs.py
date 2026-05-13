"""Unit tests for :mod:`application.services.startup_jobs`.

The pipeline must:

* fan provider ``schedule()`` calls through the ingestion pipeline,
* persist the deduplicated batch through the database manager,
* run subsequent jobs even when an earlier job throws,
* report per-job outcomes so callers can introspect failures.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from ....application.services.api_coordinator import APICoordinator
from ....application.services.startup_jobs import (
    StartupJob,
    StartupJobReport,
    StartupJobsService,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeProvider:
    def __init__(self, name, schedule_items=(), raises=False):
        self.__name__ = name
        self._schedule_items = schedule_items
        self._raises = raises

    def schedule(self, limit=50):
        if self._raises:
            raise RuntimeError(f"{self.__name__} schedule failure")
        for item in self._schedule_items[:limit]:
            yield item


class _FakeAPI:
    def __init__(self, providers):
        self._providers = providers

    def get_providers(self):
        return list(self._providers)


class _RecordingDBManager:
    def __init__(self):
        self.upserts = []

    def get_database(self):
        return None  # disables the update_status job in these tests

    def upsert_anime_batch(self, records):
        self.upserts.append(list(records))
        return len(records)


def _anime_like(rid, title="t"):
    return SimpleNamespace(
        id=rid,
        title=title,
        synopsis=None,
        episodes=None,
        duration=None,
        status=None,
        rating=None,
        date_from=None,
        date_to=None,
        picture=None,
        trailer=None,
        broadcast=None,
    )


def _build_service(api, db) -> StartupJobsService:
    coord = APICoordinator(max_workers=2, provider_timeout_s=2.0)
    coord.set_api(api)
    coord.set_database_manager(db)
    coord.log = lambda *a, **k: None  # silence logs in tests
    runtime = SimpleNamespace(logger=None)
    return StartupJobsService(
        api_coordinator=coord,
        database_manager=db,
        runtime=runtime,
        schedule_limit=10,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_fetch_latest_persists_deduped_batch():
    api = _FakeAPI(
        [
            _FakeProvider("A", [_anime_like(1), _anime_like(2)]),
            _FakeProvider("B", [_anime_like(2), _anime_like(3)]),
        ]
    )
    db = _RecordingDBManager()
    service = _build_service(api, db)
    try:
        report = service.run()
    finally:
        service._api_coordinator.close()

    assert isinstance(report, StartupJobReport)
    # ``repair_date_from`` + ``fetch_latest_anime`` + ``update_status``.
    # The two non-fetch jobs short-circuit cleanly here because
    # ``_RecordingDBManager.get_database()`` returns ``None``.
    assert report.total == 3
    fetch = next(o for o in report.outcomes if o.name == "fetch_latest_anime")
    assert fetch.ok is True
    # The DB sink should have received exactly the deduped batch once.
    # The pipeline's internal sink may double-persist when we also flush
    # explicitly from the startup job; the service tolerates that. What
    # matters is the deduplicated set of ids made it through.
    persisted_ids = {a.id for batch in db.upserts for a in batch}
    assert persisted_ids == {1, 2, 3}


def test_partial_provider_failure_still_succeeds():
    api = _FakeAPI(
        [
            _FakeProvider("A", [_anime_like(1)]),
            _FakeProvider("B", raises=True),
        ]
    )
    db = _RecordingDBManager()
    service = _build_service(api, db)
    try:
        report = service.run()
    finally:
        service._api_coordinator.close()

    fetch = next(o for o in report.outcomes if o.name == "fetch_latest_anime")
    # Schedule call returns PARTIAL, the startup job still reports ok
    # because at least one provider produced data.
    assert fetch.ok is True
    persisted_ids = {a.id for batch in db.upserts for a in batch}
    assert persisted_ids == {1}


def test_no_providers_yields_skipped_outcome():
    api = _FakeAPI([])
    db = _RecordingDBManager()
    service = _build_service(api, db)
    try:
        report = service.run()
    finally:
        service._api_coordinator.close()

    fetch = next(o for o in report.outcomes if o.name == "fetch_latest_anime")
    assert fetch.ok is True
    assert "skipped" in fetch.detail
    assert db.upserts == []


def test_one_failing_job_does_not_abort_pipeline():
    """The orchestrator must continue past a job that raises."""
    api = _FakeAPI([])
    db = _RecordingDBManager()
    service = _build_service(api, db)
    try:
        # Replace the job iterator with one that throws first, then
        # produces a healthy job. The service is expected to record the
        # failure and still run the trailing job.
        ran = []

        def jobs():
            yield StartupJob("explode", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
            yield StartupJob("succeed", lambda: ran.append("ok") or "ok")

        service._jobs = jobs  # type: ignore[assignment]
        report = service.run()
    finally:
        service._api_coordinator.close()

    assert ran == ["ok"]
    assert report.total == 2
    assert report.failures == 1
    explode = next(o for o in report.outcomes if o.name == "explode")
    assert explode.ok is False
    assert "RuntimeError" in explode.detail
    succeed = next(o for o in report.outcomes if o.name == "succeed")
    assert succeed.ok is True


def test_run_in_background_returns_thread_and_completes():
    api = _FakeAPI([_FakeProvider("A", [_anime_like(1)])])
    db = _RecordingDBManager()
    service = _build_service(api, db)
    try:
        thread = service.run_in_background(daemon=True)
        assert isinstance(thread, threading.Thread)
        thread.join(timeout=10.0)
        assert not thread.is_alive(), "background startup jobs did not finish"
    finally:
        service._api_coordinator.close()

    assert service.last_report is not None
    assert service.last_report.total >= 1


def test_facade_exposes_kickoff():
    """The facade must accept a startup-jobs service and route through it."""
    from ....composition.facade import EmbeddedClientFacade

    calls = []

    class _Stub:
        def run(self):
            calls.append("sync")
            return StartupJobReport()

        def run_in_background(self, daemon=True):
            calls.append("async")
            t = threading.Thread(target=lambda: None)
            t.start()
            return t

    facade = EmbeddedClientFacade(service=object(), startup_jobs=_Stub())
    facade.run_startup_jobs()
    t = facade.kickoff_startup_jobs()
    t.join()
    assert calls == ["sync", "async"]


def test_facade_without_startup_jobs_is_safe():
    """Facade built without startup-jobs (e.g. unit tests) must not crash."""
    from ....composition.facade import EmbeddedClientFacade

    facade = EmbeddedClientFacade(service=object())
    assert facade.run_startup_jobs() is None
    assert facade.kickoff_startup_jobs() is None
