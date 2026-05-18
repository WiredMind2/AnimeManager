"""Startup processing pipeline.

This module hosts :class:`StartupJobsService`, the orchestrator that
runs the periodic processing tasks the legacy ``Manager`` class used to
drive from ``Manager.__init__`` (via ``UpdateUtils.updateAllProgression``).
The legacy chain was lost during the Phase 0-7 architecture refactor
when ``Manager`` and ``UpdateUtils`` were deleted; this service is the
modern replacement and is invoked from :mod:`bootstrap` once the
composition root has finished wiring the dependency graph.

The service is intentionally infrastructure-light: every job is a
small callable that closes over collaborators already living in the
composition graph (``APICoordinator``, ``DatabaseManager``, the
``LegacyRuntime``). Each job is independent and surrounded by a
try/except so that a single failure (e.g. an offline provider, a
read-only database) never prevents the rest of the pipeline from
running.
"""

from __future__ import annotations

import threading
import time
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, List, Optional

from application.bridges.legacy_entities import Anime
from application.services.api_coordinator import APICoordinator
from application.services.database_manager import DatabaseManager
from shared.contracts import IngestionResult, IngestionStatus
from shared.config.getters import Getters
from shared.telemetry import get_telemetry


@dataclass(frozen=True)
class StartupJob:
    """A single startup processing task."""

    name: str
    fn: Callable[[], Any]


@dataclass
class StartupJobOutcome:
    """Per-job execution record."""

    name: str
    ok: bool
    detail: str = ""
    elapsed_ms: int = 0


@dataclass
class StartupJobReport:
    """Aggregate report of a startup-jobs run."""

    outcomes: List[StartupJobOutcome] = field(default_factory=list)
    elapsed_ms: int = 0

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def failures(self) -> int:
        return sum(1 for o in self.outcomes if not o.ok)

    def add(self, outcome: StartupJobOutcome) -> None:
        self.outcomes.append(outcome)


class StartupJobsService:
    """Run the startup processing pipeline.

    The service is the modern replacement for the legacy
    ``UpdateUtils.updateAllProgression`` chain. It fans the work across
    short, well-scoped jobs that each survive their own errors.

    Jobs currently implemented:

    * ``fetch_latest_anime`` -- pull the current season / trending
      lists from every metadata provider that exposes a ``schedule``
      endpoint and persist them through the canonical ingestion
      pipeline.
    * ``update_status`` -- transition ``UPCOMING`` rows whose
      ``date_from`` is in the past to the status implied by their
      airing window (``AIRING`` / ``FINISHED``).

    The orchestrator never raises; callers inspect
    :class:`StartupJobReport` if they need to react to failures.
    """

    def __init__(
        self,
        *,
        api_coordinator: APICoordinator,
        database_manager: DatabaseManager,
        runtime: Any,
        schedule_limit: int = 50,
    ) -> None:
        self._api_coordinator = api_coordinator
        self._database_manager = database_manager
        self._runtime = runtime
        self._schedule_limit = max(1, int(schedule_limit))
        self._telemetry = get_telemetry()
        self._lock = threading.Lock()
        self._last_report: Optional[StartupJobReport] = None
        self._running = False

    @property
    def last_report(self) -> Optional[StartupJobReport]:
        return self._last_report

    @property
    def is_running(self) -> bool:
        return self._running

    def run(self) -> StartupJobReport:
        """Execute every startup job in order. Always returns a report."""
        with self._lock:
            if self._running:
                # Defensive: a second concurrent invocation would race
                # against the API/DB collaborators. The caller is
                # expected to gate on :attr:`is_running` for that case;
                # we return the most recent report to keep the contract
                # non-blocking.
                return self._last_report or StartupJobReport()
            self._running = True

        report = StartupJobReport()
        total_start = time.perf_counter()
        try:
            for job in self._jobs():
                self._run_one(job, report)
        finally:
            report.elapsed_ms = int(
                (time.perf_counter() - total_start) * 1000
            )
            with self._lock:
                self._running = False
                self._last_report = report

        self._telemetry.record_ms("startup.total_ms", report.elapsed_ms)
        self._telemetry.set_gauge(
            "startup.failed_jobs", float(report.failures)
        )
        self._telemetry.set_gauge(
            "startup.total_jobs", float(report.total)
        )
        self._log(
            f"Startup pipeline complete: {report.total - report.failures}"
            f"/{report.total} jobs ok in {report.elapsed_ms} ms"
        )
        return report

    def run_in_background(
        self, daemon: bool = True
    ) -> threading.Thread:
        """Run :meth:`run` on a worker thread and return immediately.

        The caller never needs to join the thread; it is daemonic by
        default so it does not block process exit. The thread name is
        prefixed with ``AM-StartupJobs`` so it is easy to identify in
        thread dumps.
        """
        thread = threading.Thread(
            target=self.run,
            name="AM-StartupJobs",
            daemon=daemon,
        )
        thread.start()
        return thread

    def _run_one(
        self, job: StartupJob, report: StartupJobReport
    ) -> None:
        start = time.perf_counter()
        try:
            detail = job.fn()
            elapsed = int((time.perf_counter() - start) * 1000)
            report.add(
                StartupJobOutcome(
                    name=job.name,
                    ok=True,
                    detail=str(detail) if detail is not None else "",
                    elapsed_ms=elapsed,
                )
            )
            self._telemetry.record_ms(
                f"startup.job.{job.name}_ms", elapsed
            )
            self._log(
                f"Startup job '{job.name}' ok: {detail} ({elapsed} ms)"
            )
        except Exception as exc:  # noqa: BLE001 - jobs must not abort the pipeline
            elapsed = int((time.perf_counter() - start) * 1000)
            report.add(
                StartupJobOutcome(
                    name=job.name,
                    ok=False,
                    detail=f"{type(exc).__name__}: {exc}",
                    elapsed_ms=elapsed,
                )
            )
            self._telemetry.increment(
                f"startup.job.{job.name}_errors"
            )
            self._log(
                f"Startup job '{job.name}' FAILED: "
                f"{type(exc).__name__}: {exc}"
            )

    def _jobs(self) -> Iterable[StartupJob]:
        yield StartupJob("repair_date_from", self._job_repair_date_from)
        yield StartupJob("fetch_latest_anime", self._job_fetch_latest)
        yield StartupJob("update_status", self._job_update_status)

    # Any ``date_from`` / ``date_to`` value smaller than this threshold
    # is treated as a legacy ``datetime.toordinal()`` value (days since
    # year 1, ~1e6 for modern dates) and converted to a UTC Unix
    # timestamp. ``2_000_000`` keeps a wide safety margin around the
    # largest plausible ordinal date (~3.65e6 for year 9999) while
    # being orders of magnitude below the smallest plausible Unix
    # timestamp the codebase ever stored (1.0e8 ~ 1973).
    _ORDINAL_THRESHOLD = 2_000_000

    def _job_repair_date_from(self) -> str:
        """One-shot migration: turn ordinal ``date_from`` values into Unix.

        Historically the Jikan adapter persisted ``date_from`` as
        ``datetime(**v).toordinal()`` (days since year 1) while every
        other producer used Unix timestamps. The persistence layer was
        independently broken on MariaDB pools so the bad values rarely
        landed in the DB, but now that writes actually commit we have
        to reconcile the two formats; otherwise the ordinal rows sort
        catastrophically below the Unix rows in
        ``ORDER BY date_from DESC`` and never reach the main page.

        The conversion is conservative and idempotent: values already
        in Unix range stay untouched, rows with ``NULL`` are skipped,
        and ordinal values are re-interpreted through
        :meth:`datetime.fromordinal` -> ``timestamp()``.
        """
        db = self._database_manager.get_database()
        if db is None:
            return "skipped (database not initialized)"

        try:
            rows = db.sql(
                "SELECT id, date_from, date_to FROM anime "
                "WHERE (date_from IS NOT NULL AND date_from < %s) "
                "   OR (date_to   IS NOT NULL AND date_to   < %s)",
                [self._ORDINAL_THRESHOLD, self._ORDINAL_THRESHOLD],
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed scanning anime for ordinal dates: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        if not rows:
            return "no rows to repair"

        repaired_from = 0
        repaired_to = 0
        for row in rows:
            anime_id, date_from, date_to = row[0], row[1], row[2]
            new_from = self._ordinal_to_unix(date_from)
            new_to = self._ordinal_to_unix(date_to)
            sets: list[str] = []
            params: list[Any] = []
            if new_from is not None and new_from != date_from:
                sets.append("date_from=%s")
                params.append(new_from)
                repaired_from += 1
            if new_to is not None and new_to != date_to:
                sets.append("date_to=%s")
                params.append(new_to)
                repaired_to += 1
            if not sets:
                continue
            params.append(int(anime_id))
            try:
                db.sql(
                    f"UPDATE anime SET {', '.join(sets)} WHERE id=%s",
                    params,
                    save=True,
                )
            except Exception as exc:
                # Skip-and-keep-going: a single bad row should not
                # poison the migration for the rest of the table.
                self._log(
                    f"date_from repair skipped id={anime_id}: "
                    f"{type(exc).__name__}: {exc}"
                )

        return f"repaired date_from={repaired_from} date_to={repaired_to}"

    @classmethod
    def _ordinal_to_unix(cls, value: Any) -> Optional[int]:
        """Coerce an ordinal ``date_from`` value into a Unix timestamp.

        Returns ``None`` when ``value`` is ``None`` or unparseable, and
        echoes the input untouched when the value is already in Unix
        range (``>= _ORDINAL_THRESHOLD``).
        """
        if value is None:
            return None
        try:
            n = int(value)
        except (TypeError, ValueError):
            return None
        if n >= cls._ORDINAL_THRESHOLD:
            return n
        try:
            d = datetime.fromordinal(n).replace(tzinfo=timezone.utc)
            return int(d.timestamp())
        except (ValueError, OverflowError):
            return None

    def _job_fetch_latest(self) -> str:
        """Pull the latest anime data from every provider's schedule."""
        result: Optional[IngestionResult] = (
            self._api_coordinator.fetch_latest(limit=self._schedule_limit)
        )
        if result is None:
            return "skipped (no providers / API unavailable)"

        # The ingestion pipeline auto-persists when the
        # ``db_gateway_writes_only`` flag is on; the legacy fallback
        # path (flag off) still relies on the caller to drive a sink.
        # We explicitly persist here too, so the behaviour is the same
        # in either configuration. Records are already deduplicated by
        # the pipeline.
        persisted_extra = 0
        records = result.records or []
        if records and self._database_manager is not None:
            try:
                animes = [self._record_to_anime(record) for record in records]
                persisted_extra = self._database_manager.upsert_anime_batch(
                    animes
                )
            except Exception as exc:  # noqa: BLE001 - logged at top level
                # Surface the persistence failure but keep the pipeline
                # status -- the schedule fetch itself succeeded.
                raise RuntimeError(
                    f"Schedule persistence failed: {type(exc).__name__}: {exc}"
                ) from exc

        backfill_detail = self._maybe_run_merge_backfill()
        if result.status == IngestionStatus.FAILED:
            return (
                f"providers={result.total_providers} failed="
                f"{result.failed_providers} records=0 {backfill_detail}"
            )

        return (
            f"providers={result.total_providers} failed="
            f"{result.failed_providers} records={len(records)} "
            f"persisted={persisted_extra} {backfill_detail}"
        )

    def _maybe_run_merge_backfill(self) -> str:
        flag = self._read_feature_flag("anime_merge_backfill_enabled", default=False)
        if not flag:
            return "merge_backfill=disabled"

        marker_path = self._merge_backfill_marker_path()
        if marker_path and os.path.exists(marker_path):
            return "merge_backfill=already_done"

        backfill_fn = getattr(self._database_manager, "backfill_external_id_duplicates", None)
        if not callable(backfill_fn):
            return "merge_backfill=unsupported"

        stats = backfill_fn()
        merged = int((stats or {}).get("merged", 0))
        groups = int((stats or {}).get("groups", 0))
        passes = int((stats or {}).get("passes", 0))

        if marker_path:
            try:
                os.makedirs(os.path.dirname(marker_path), exist_ok=True)
                with open(marker_path, "w", encoding="utf-8") as f:
                    f.write(
                        f"merged={merged}\n"
                        f"groups={groups}\n"
                        f"passes={passes}\n"
                    )
            except Exception as exc:
                self._log(f"merge backfill marker write failed: {exc}")
        return f"merge_backfill=merged:{merged},groups:{groups},passes:{passes}"

    def _read_feature_flag(self, name: str, default: bool = False) -> bool:
        runtime = self._runtime
        getter = getattr(runtime, "getFeatureFlag", None)
        if callable(getter):
            try:
                return bool(getter(name, default))
            except Exception:
                return bool(default)
        settings = getattr(runtime, "settings", None)
        if isinstance(settings, dict):
            return Getters.getFeatureFlag(runtime, name, default)
        return bool(default)

    def _merge_backfill_marker_path(self) -> Optional[str]:
        runtime = self._runtime
        fm = getattr(runtime, "fm", None)
        fm_settings = getattr(fm, "settings", None)
        if isinstance(fm_settings, dict):
            data_path = fm_settings.get("dataPath")
            if isinstance(data_path, str) and data_path.strip():
                return os.path.join(data_path, ".anime_merge_backfill.done")
        settings = getattr(runtime, "settings", None)
        if isinstance(settings, dict):
            fm_settings = (
                settings.get("file_managers", {})
                .get(settings.get("file_managers", {}).get("last_fm_used", ""), {})
            )
            data_path = fm_settings.get("dataPath") if isinstance(fm_settings, dict) else None
            if isinstance(data_path, str) and data_path.strip():
                return os.path.join(data_path, ".anime_merge_backfill.done")
        return None

    def _job_update_status(self) -> str:
        """Transition stale ``UPCOMING`` rows whose air date has passed.

        The legacy ``UpdateUtils.updateStatus`` walked the table and
        applied ``Getters.getStatus()`` -- a pure helper based on the
        current date and the anime's ``date_from`` / ``date_to`` /
        ``episodes`` columns. We re-use that helper directly so the
        derivation stays in sync with the rest of the codebase.
        """
        from shared.config.getters import Getters

        db = self._database_manager.get_database()
        if db is None:
            return "skipped (database not initialized)"

        try:
            rows = db.sql(
                "SELECT id, status, date_from, date_to, episodes "
                "FROM anime "
                "WHERE status='UPCOMING' "
                "AND date_from IS NOT NULL "
                "ORDER BY date_from ASC"
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed reading upcoming anime rows: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        if not rows:
            return "no rows to update"

        now_ts = datetime.now(timezone.utc).timestamp()
        transitions: dict[str, list[int]] = {}
        for row in rows:
            anime_id, status, date_from, date_to, episodes = (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
            )
            if date_from is None:
                continue
            try:
                if float(date_from) > now_ts:
                    # Rows are ordered ASC by ``date_from``; everything
                    # that follows is still in the future.
                    break
            except (TypeError, ValueError):
                continue

            anime = Anime(
                {
                    "id": anime_id,
                    "status": None,  # force getStatus to derive
                    "date_from": date_from,
                    "date_to": date_to,
                    "episodes": episodes,
                }
            )
            new_status = Getters.getStatus(anime)
            if not new_status or new_status == "UPCOMING":
                continue
            transitions.setdefault(new_status, []).append(int(anime_id))

        if not transitions:
            return "no rows to update"

        updated = 0
        try:
            with db.get_lock():
                items = list(transitions.items())
                last = len(items) - 1
                # ``db.save()`` only commits the long-lived main
                # connection, but ``db.sql`` calls run on per-call
                # pool connections (see ``EmbeddedMariaDB.insert``).
                # Asking the final statement to commit on its own
                # pool connection is the only durable path.
                for idx, (new_status, ids) in enumerate(items):
                    placeholders = ",".join(["?"] * len(ids))
                    db.sql(
                        f"UPDATE anime SET status=? WHERE id IN ({placeholders})",
                        [new_status, *ids],
                        save=(idx == last),
                    )
                    updated += len(ids)
        except Exception as exc:
            raise RuntimeError(
                f"Failed updating anime statuses: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        breakdown = ", ".join(
            f"{status}={len(ids)}" for status, ids in transitions.items()
        )
        return f"updated={updated} ({breakdown})"

    @staticmethod
    def _record_to_anime(record: Any) -> Anime:
        """Project an :class:`AnimeRecord` back into a legacy ``Anime``."""
        anime = Anime()
        for key in (
            "id",
            "title",
            "synopsis",
            "episodes",
            "duration",
            "status",
            "rating",
            "date_from",
            "date_to",
            "picture",
            "trailer",
            "broadcast",
        ):
            value = getattr(record, key, None)
            if value is None:
                continue
            try:
                setattr(anime, key, value)
            except Exception:
                # Some attributes are managed by the legacy class; ignore.
                pass
        return anime

    # ``MAIN_STATE`` is the legacy "lifecycle" category that the shared
    # logger is already configured to surface to the console (see
    # ``shared.telemetry.logger.Logger.logs``). Custom categories like
    # ``STARTUP_JOBS`` would be silently filtered to file-only, which is
    # why the original wiring looked like nothing was running. We tag
    # every line so operators can still grep for the pipeline output.
    _LOG_CATEGORY = "MAIN_STATE"
    _LOG_PREFIX = "[STARTUP_JOBS]"

    def _log(self, message: str) -> None:
        text = f"{self._LOG_PREFIX} {message}"
        logger = getattr(self._runtime, "logger", None)
        log_fn = getattr(logger, "log", None) if logger is not None else None
        delivered = False
        try:
            if callable(log_fn):
                log_fn(self._LOG_CATEGORY, text)
                delivered = True
        except Exception:
            delivered = False
        if not delivered:
            try:
                print(text, flush=True)
            except Exception:
                # Logging must never break the pipeline.
                pass


__all__ = [
    "StartupJob",
    "StartupJobOutcome",
    "StartupJobReport",
    "StartupJobsService",
]
