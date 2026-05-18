"""Tests for startup job date repair and status transitions."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from application.services.api_coordinator import APICoordinator
from application.services.startup_jobs import StartupJobsService


class _SqliteDB:
    def __init__(self) -> None:
        self.con = sqlite3.connect(":memory:")
        self.cur = self.con.cursor()
        self.cur.executescript(
            """
            CREATE TABLE anime (
                id INTEGER PRIMARY KEY,
                status TEXT,
                date_from REAL,
                date_to REAL,
                episodes INTEGER
            );
            """
        )
        self.con.commit()

    def sql(self, query, params=(), save=False):
        if "%s" in query:
            query = query.replace("%s", "?")
        self.cur.execute(query, params)
        if save:
            self.con.commit()
        if query.lstrip().upper().startswith("SELECT"):
            return self.cur.fetchall()
        return []

    @contextmanager
    def get_lock(self):
        yield


class _DBManager:
    def __init__(self, db: _SqliteDB) -> None:
        self._db = db

    def get_database(self):
        return self._db


def _build_service(db: _SqliteDB) -> StartupJobsService:
    coord = APICoordinator(max_workers=1, provider_timeout_s=1.0)
    coord.set_api(SimpleNamespace(get_providers=lambda: []))
    coord.set_database_manager(_DBManager(db))
    coord.log = lambda *a, **k: None
    runtime = SimpleNamespace(logger=None)
    return StartupJobsService(
        api_coordinator=coord,
        database_manager=_DBManager(db),
        runtime=runtime,
    )


def test_ordinal_to_unix_converts_legacy_ordinals():
    ordinal = datetime(2020, 6, 1, tzinfo=timezone.utc).toordinal()
    unix = StartupJobsService._ordinal_to_unix(ordinal)
    expected = int(datetime(2020, 6, 1, tzinfo=timezone.utc).timestamp())
    assert unix == expected


def test_ordinal_to_unix_leaves_unix_values():
    assert StartupJobsService._ordinal_to_unix(1_600_000_000) == 1_600_000_000


def test_ordinal_to_unix_handles_none_and_garbage():
    assert StartupJobsService._ordinal_to_unix(None) is None
    assert StartupJobsService._ordinal_to_unix("bad") is None


def test_repair_date_from_migrates_ordinal_rows():
    db = _SqliteDB()
    ordinal = datetime(2019, 1, 1, tzinfo=timezone.utc).toordinal()
    db.sql(
        "INSERT INTO anime (id, status, date_from, date_to, episodes) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, "AIRING", ordinal, None, 12),
        save=True,
    )
    service = _build_service(db)
    try:
        report = service.run()
    finally:
        service._api_coordinator.close()

    repair = next(o for o in report.outcomes if o.name == "repair_date_from")
    assert repair.ok is True
    assert "repaired date_from=1" in repair.detail
    row = db.sql("SELECT date_from FROM anime WHERE id=1")[0]
    assert int(row[0]) >= StartupJobsService._ORDINAL_THRESHOLD


def test_update_status_transitions_stale_upcoming_rows():
    db = _SqliteDB()
    past = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
    future = datetime(2099, 1, 1, tzinfo=timezone.utc).timestamp()
    db.sql(
        "INSERT INTO anime (id, status, date_from, date_to, episodes) "
        "VALUES (1, 'UPCOMING', ?, NULL, 12), (2, 'UPCOMING', ?, NULL, 12)",
        (past, future),
        save=True,
    )
    service = _build_service(db)
    try:
        report = service.run()
    finally:
        service._api_coordinator.close()

    status_job = next(o for o in report.outcomes if o.name == "update_status")
    assert status_job.ok is True
    assert "updated=" in status_job.detail
    row1 = db.sql("SELECT status FROM anime WHERE id=1")[0][0]
    row2 = db.sql("SELECT status FROM anime WHERE id=2")[0][0]
    assert row1 != "UPCOMING"
    assert row2 == "UPCOMING"


def test_concurrent_run_returns_last_report():
    db = _SqliteDB()
    service = _build_service(db)
    service._running = True
    service._last_report = None
    report = service.run()
    assert report.total == 0
    try:
        service._running = False
        full = service.run()
    finally:
        service._api_coordinator.close()
    assert full.total >= 1
