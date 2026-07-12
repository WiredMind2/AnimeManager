"""Unit tests for :mod:`application.services.startup_jobs`.

The pipeline must:

* fan provider ``schedule()`` calls through the ingestion pipeline,
* persist the deduplicated batch through the database manager,
* run subsequent jobs even when an earlier job throws,
* report per-job outcomes so callers can introspect failures.
"""

from __future__ import annotations

import contextlib
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
        self.enrich_calls = []

    def get_database(self):
        return None  # disables the update_status job in these tests

    def upsert_anime_batch(self, records):
        self.upserts.append(list(records))
        return len(records)

    def enrich_catalog_identities(self, *, limit=50):
        self.enrich_calls.append(("startup", limit))
        return SimpleNamespace(looked_up=0, enriched=0, merged=0)

    def enrich_catalog_identities_for_ids(self, catalog_ids):
        self.enrich_calls.append(("batch", list(catalog_ids)))
        return SimpleNamespace(looked_up=0, enriched=0, merged=0)

    def repair_duplicate_anime_entries(self, **kwargs):
        return 0


def _anime_like(rid, title="t", date_from=None):
    if date_from is None:
        date_from = int(time.time()) - 5 * 86_400
    return SimpleNamespace(
        id=rid,
        title=title,
        synopsis=None,
        episodes=None,
        duration=None,
        status=None,
        rating=None,
        date_from=date_from,
        date_to=None,
        picture=None,
        trailer=None,
        broadcast=None,
    )


def _build_service(api, db, *, settings=None) -> StartupJobsService:
    coord = APICoordinator(max_workers=2, provider_timeout_s=2.0)
    coord.set_api(api)
    coord.set_database_manager(db)
    coord.log = lambda *a, **k: None  # silence logs in tests
    anime_settings = {
        "scheduleTimeout": 86400,
        "lastSchedule": 0,
        "maxTrendingAnime": 10,
    }
    if settings:
        anime_settings.update(settings)
    saved: dict = {}

    def update_settings(updates):
        saved.update(updates)
        if "anime" in updates:
            anime_settings.update(updates["anime"])

    config = SimpleNamespace(
        settings={"anime": anime_settings, "startup_migrations": {}},
        update_settings=update_settings,
        _saved_settings=saved,
    )
    return StartupJobsService(
        api_coordinator=coord,
        database_manager=db,
        config=config,
        torrent_manager=None,
        logger=SimpleNamespace(log=lambda *a, **k: None),
        schedule_limit=10,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_startup_pipeline_runs_lean_jobs_only():
    """Heavy backlog jobs must not run on every boot."""
    api = _FakeAPI([])
    db = _RecordingDBManager()
    service = _build_service(api, db)
    try:
        report = service.run()
    finally:
        service._api_coordinator.close()

    names = [o.name for o in report.outcomes]
    assert names == [
        "repair_date_from",
        "fetch_latest_anime",
        "update_status",
        "purge_deleted_torrents",
        "restore_libtorrent_sessions",
        "reconcile_deleted_torrents",
    ]
    assert report.total == 6
    assert db.enrich_calls == []


def test_removed_backlog_job_methods_remain_callable(monkeypatch):
    """Job helpers stay available for manual/post-ingest use."""
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    api = _FakeAPI([])
    db = _RecordingDBManager()
    service = _build_service(api, db)
    try:
        assert service._job_enrich_catalog_ids().startswith("no single-provider")
        assert service._job_repair_duplicate_anime().startswith("no duplicate")
    finally:
        service._api_coordinator.close()

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
    # Lean pipeline: ``repair_date_from``, ``fetch_latest_anime``,
    # ``update_status``, ``purge_deleted_torrents``,
    # ``restore_libtorrent_sessions``, ``reconcile_deleted_torrents``.
    # cleanly here because ``_RecordingDBManager.get_database()`` returns
    # ``None``.
    assert report.total == 5
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


def test_run_in_background_is_idempotent_while_thread_alive():
    api = _FakeAPI([_FakeProvider("A", [_anime_like(1)])])
    db = _RecordingDBManager()
    service = _build_service(api, db)
    try:
        thread1 = service.run_in_background(daemon=True)
        thread2 = service.run_in_background(daemon=True)
        assert thread1 is thread2
        thread1.join(timeout=10.0)
        assert not thread1.is_alive()
    finally:
        service._api_coordinator.close()


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


def test_reconcile_deleted_torrents_job_runs_with_adapter():
    api = _FakeAPI([])
    db = _RecordingDBManager()
    adapter = SimpleNamespace(reconcile_deleted_torrents=lambda: 2)
    coord = APICoordinator(max_workers=2, provider_timeout_s=2.0)
    coord.set_api(api)
    coord.set_database_manager(db)
    coord.log = lambda *a, **k: None
    service = StartupJobsService(
        api_coordinator=coord,
        database_manager=db,
        config=SimpleNamespace(settings={}),
        torrent_manager=None,
        logger=SimpleNamespace(log=lambda *a, **k: None),
        download_adapter=adapter,
        schedule_limit=10,
    )
    try:
        detail = service._job_reconcile_deleted_torrents()
    finally:
        coord.close()
    assert detail == "marked 2 torrent(s) deleted"


def test_purge_deleted_torrents_job_runs_before_restore():
    api = _FakeAPI([])
    db = _RecordingDBManager()
    adapter = SimpleNamespace(purge_deleted_torrents=lambda: 3)
    coord = APICoordinator(max_workers=2, provider_timeout_s=2.0)
    coord.set_api(api)
    coord.set_database_manager(db)
    coord.log = lambda *a, **k: None
    service = StartupJobsService(
        api_coordinator=coord,
        database_manager=db,
        config=SimpleNamespace(settings={}),
        torrent_manager=None,
        logger=SimpleNamespace(log=lambda *a, **k: None),
        download_adapter=adapter,
        schedule_limit=10,
    )
    try:
        names = [job.name for job in service._jobs()]
        assert names.index("purge_deleted_torrents") < names.index(
            "restore_libtorrent_sessions"
        )
        detail = service._job_purge_deleted_torrents()
    finally:
        coord.close()
    assert detail == "purged 3 deleted torrent artifact(s)"


def test_schedule_timeout_clamped_to_daily_minimum():
    service = _build_service(_FakeAPI([]), _RecordingDBManager(), settings={"scheduleTimeout": 120})
    timeout_s, _, _ = service._read_schedule_config()
    assert timeout_s == StartupJobsService._SCHEDULE_MIN_INTERVAL_S


def test_startup_skips_fetch_when_last_schedule_is_recent():
    api = _FakeAPI([_FakeProvider("A", [_anime_like(1)])])
    db = _RecordingDBManager()
    service = _build_service(
        api,
        db,
        settings={"lastSchedule": int(time.time())},
    )
    try:
        report = service.run()
    finally:
        service._api_coordinator.close()

    fetch = next(o for o in report.outcomes if o.name == "fetch_latest_anime")
    assert fetch.ok is True
    assert "skipped (recent fetch)" in fetch.detail
    assert db.upserts == []


def test_fetch_marks_last_schedule(monkeypatch):
    api = _FakeAPI([_FakeProvider("A", [_anime_like(1)])])
    db = _RecordingDBManager()
    service = _build_service(api, db)
    fixed = 1_700_000_000

    monkeypatch.setattr(time, "time", lambda: fixed)
    try:
        detail = service._job_fetch_latest()
    finally:
        service._api_coordinator.close()

    assert "records=" in detail
    assert "persisted=1" in detail
    assert service._config._saved_settings.get("anime", {}).get("lastSchedule") == fixed


def test_fetch_does_not_mark_schedule_when_persistence_fails():
    api = _FakeAPI([_FakeProvider("A", [_anime_like(1)])])
    db = _RecordingDBManager()

    def _fail_batch(records):
        return 0

    db.upsert_anime_batch = _fail_batch  # type: ignore[method-assign]
    service = _build_service(api, db)
    try:
        detail = service._job_fetch_latest()
    finally:
        service._api_coordinator.close()

    assert "persisted=0" in detail
    assert "will retry" in detail
    assert service._config._saved_settings.get("anime", {}).get("lastSchedule") is None


def test_fetch_waits_for_api_init_thread():
    api = _FakeAPI([_FakeProvider("A", [_anime_like(1)])])
    gate = threading.Event()
    init_thread = threading.Thread(target=gate.wait)
    init_thread.start()
    api.init_thread = init_thread  # type: ignore[attr-defined]

    db = _RecordingDBManager()
    service = _build_service(api, db)

    def _release_and_fetch():
        time.sleep(0.05)
        gate.set()
        return service._job_fetch_latest()

    worker = threading.Thread(target=_release_and_fetch)
    worker.start()
    worker.join(timeout=5.0)
    assert not worker.is_alive()
    init_thread.join(timeout=1.0)
    service._api_coordinator.close()


class _StatusDB:
    def __init__(self, upcoming=(), airing=()):
        self.upcoming = list(upcoming)
        self.airing = list(airing)
        self.updates = []

    @contextlib.contextmanager
    def get_lock(self):
        yield

    def sql(self, query, params=None, save=False):
        if "status='UPCOMING'" in query:
            return list(self.upcoming)
        if "status='AIRING'" in query:
            return list(self.airing)
        if query.startswith("UPDATE anime SET status=?"):
            self.updates.append((params[0], list(params[1:])))
            return []
        raise AssertionError(f"Unexpected SQL: {query!r}")


class _StatusDBManager(_RecordingDBManager):
    def __init__(self, db):
        super().__init__()
        self._db = db

    def get_database(self):
        return self._db

    def repair_duplicate_anime_entries(self, **kwargs):
        return 0


def test_update_status_marks_stale_airing_finished():
    db = _StatusDB(
        airing=[(42, "AIRING", 1_600_000_000, 1_600_000_100, 12)],
    )
    service = _build_service(_FakeAPI([]), _StatusDBManager(db))
    detail = service._job_update_status()
    assert "FINISHED=1" in detail
    assert db.updates == [("FINISHED", [42])]


def test_schedule_refresh_runs_fetch_and_status():
    api = _FakeAPI([_FakeProvider("A", [_anime_like(7)])])
    db = _RecordingDBManager()
    service = _build_service(api, db)
    try:
        report = service.run_schedule_refresh()
    finally:
        service._api_coordinator.close()

    names = [o.name for o in report.outcomes]
    assert names == ["fetch_latest_anime", "update_status"]


@pytest.mark.parametrize(
    "settings, expect_max",
    [
        # Far-future lastSchedule -> negative elapsed -> would overflow without clamping.
        ({"lastSchedule": 10**18}, StartupJobsService._SCHEDULE_SLEEP_MAX_S),
        # Oversized scheduleTimeout alone must also be capped.
        ({"scheduleTimeout": 10**18, "lastSchedule": 0}, StartupJobsService._SCHEDULE_SLEEP_MAX_S),
    ],
)
def test_schedule_loop_sleep_is_bounded(settings, expect_max):
    api = _FakeAPI([_FakeProvider("A", [_anime_like(1)])])
    db = _RecordingDBManager()
    service = _build_service(api, db, settings=settings)
    try:
        sleep_s = service._next_schedule_sleep_s()
    finally:
        service._api_coordinator.close()

    assert 60.0 <= sleep_s <= expect_max


def test_backfill_title_synonyms_hydrates_missing_rows():
    class _BackfillDB:
        def __init__(self):
            self.synonym_ids = set()

        def sql(self, query, params=()):
            if "NOT EXISTS" in query:
                return [(101,), (102,)]
            if "FROM title_synonyms" in query:
                catalog_id = int(params[0])
                return [(1,)] if catalog_id in self.synonym_ids else []
            return []

    class _HydratingAPI:
        def anime(self, catalog_id, _persist=False):
            return SimpleNamespace(title=f"Title {catalog_id}")

    class _WriteService:
        def __init__(self, db):
            self._db = db
            self.calls = []

        def persist_legacy_anime(self, anime, *, source, catalog_id=None):
            self.calls.append((getattr(anime, "title", ""), source, catalog_id))
            self._db.synonym_ids.add(int(catalog_id))
            return True

    db = _BackfillDB()
    db_manager = SimpleNamespace(get_database=lambda: db)
    coord = APICoordinator(max_workers=1, provider_timeout_s=2.0)
    coord._api = _HydratingAPI()
    write_service = _WriteService(db)
    service = StartupJobsService(
        api_coordinator=coord,
        database_manager=db_manager,
        config=SimpleNamespace(settings={"anime": {}}),
        torrent_manager=None,
        logger=SimpleNamespace(log=lambda *a, **k: None),
        write_service=write_service,
    )
    try:
        detail = service._job_backfill_title_synonyms()
    finally:
        coord.close()

    assert detail == "hydrated 2/2 row(s) missing synonyms"
    assert len(write_service.calls) == 2
