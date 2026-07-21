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
composition graph (``APICoordinator``, ``DatabaseManager``, config,
torrent manager, logger). Each job is independent and surrounded by a
try/except so that a single failure (e.g. an offline provider, a
read-only database) never prevents the rest of the pipeline from
running.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, List, Optional

from adapters.persistence.models import Anime
from application.services.api_coordinator import APICoordinator
from application.services.anime_write_service import WriteSource
from application.services.database_manager import DatabaseManager, safe_db_counter
from shared.contracts import IngestionResult, IngestionStatus
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

    Jobs run on startup (lean pipeline):

    * ``repair_date_from`` -- one-shot ordinal date migration (skipped
      after ``startup_migrations.repair_date_from``).
    * ``fetch_latest_anime`` -- pull the current season / trending
      lists from every metadata provider that exposes a ``schedule``
      endpoint (at most once per :attr:`_SCHEDULE_MIN_INTERVAL_S`).
    * ``update_status`` -- transition stale lifecycle rows
      (``UPCOMING`` / ``AIRING``) based on airing dates.
    * ``purge_deleted_torrents`` -- remove resume artifacts for DB-
      deleted torrents before session restore.
    * ``reconcile_deleted_torrents`` -- mark completed torrents whose
      files are missing as ``deleted`` (before LibTorrent restore).
    * ``restore_libtorrent_sessions`` -- restore embedded LibTorrent
      torrents after missing-file reconcile.

    Heavy backlog work (catalog enrichment, synonym backfill, duplicate
    repair) is intentionally **not** run here; it is handled by post-
    ingest enrichment, :class:`~application.services.anime_hydration.AnimeHydrationService`,
    and the daily schedule refresh loop.

    The orchestrator never raises; callers inspect
    :class:`StartupJobReport` if they need to react to failures.
    """

    # Provider schedule pulls are expensive and metadata changes slowly;
    # never fetch more often than once per day regardless of settings.
    _SCHEDULE_MIN_INTERVAL_S = 86_400

    # Hard ceiling for the schedule-loop sleep. ``threading.Event.wait`` on
    # Windows ultimately calls ``WaitForSingleObject`` with a 32-bit DWORD
    # timeout (~49.7 days); an unbounded sleep computed from a bogus or
    # future ``lastSchedule`` (negative elapsed) or an oversized
    # ``scheduleTimeout`` overflows that and raises ``OverflowError``,
    # killing the ``AM-ScheduleRefresh`` thread on every startup.
    _SCHEDULE_SLEEP_MAX_S = 7 * 86_400

    def __init__(
        self,
        *,
        api_coordinator: APICoordinator,
        database_manager: DatabaseManager,
        config: Any,
        torrent_manager: Any,
        logger: Any,
        download_adapter: Any = None,
        write_service: Any = None,
        schedule_limit: int = 50,
    ) -> None:
        self._api_coordinator = api_coordinator
        self._database_manager = database_manager
        self._config = config
        self._torrent_manager = torrent_manager
        self._logger = logger
        self._download_adapter = download_adapter
        self._write_service = write_service
        self._schedule_limit = max(1, int(schedule_limit))
        self._telemetry = get_telemetry()
        self._lock = threading.Lock()
        self._last_report: Optional[StartupJobReport] = None
        self._running = False
        self._background_thread: Optional[threading.Thread] = None
        self._schedule_loop_thread: Optional[threading.Thread] = None
        self._schedule_loop_stop = threading.Event()

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

        Idempotent: a second call while the background thread is alive
        returns the existing thread instead of spawning a duplicate
        pipeline.
        """
        with self._lock:
            if self._background_thread is not None and self._background_thread.is_alive():
                return self._background_thread
            thread = threading.Thread(
                target=self.run,
                name="AM-StartupJobs",
                daemon=daemon,
            )
            self._background_thread = thread
        thread.start()
        return thread

    def run_schedule_refresh(self) -> StartupJobReport:
        """Run provider fetch (when due) plus local status maintenance."""
        with self._lock:
            if self._running:
                return self._last_report or StartupJobReport()
            self._running = True

        report = StartupJobReport()
        total_start = time.perf_counter()
        try:
            if self._should_fetch_schedule():
                self._run_one(
                    StartupJob("fetch_latest_anime", self._job_fetch_latest),
                    report,
                )
            else:
                report.add(
                    StartupJobOutcome(
                        name="fetch_latest_anime",
                        ok=True,
                        detail="skipped (recent fetch)",
                        elapsed_ms=0,
                    )
                )
            self._run_one(
                StartupJob("update_status", self._job_update_status),
                report,
            )
        finally:
            report.elapsed_ms = int(
                (time.perf_counter() - total_start) * 1000
            )
            with self._lock:
                self._running = False
                self._last_report = report

        self._log(
            f"Schedule refresh complete: {report.total - report.failures}"
            f"/{report.total} jobs ok in {report.elapsed_ms} ms"
        )
        return report

    def start_schedule_loop(self, *, daemon: bool = True) -> threading.Thread:
        """Start a daemon thread that refreshes schedule data at most daily."""
        with self._lock:
            if (
                self._schedule_loop_thread is not None
                and self._schedule_loop_thread.is_alive()
            ):
                return self._schedule_loop_thread
            self._schedule_loop_stop.clear()

        thread = threading.Thread(
            target=self._schedule_loop_worker,
            name="AM-ScheduleRefresh",
            daemon=daemon,
        )
        with self._lock:
            self._schedule_loop_thread = thread
        thread.start()
        return thread

    def stop_schedule_loop(self) -> None:
        """Signal the daily schedule refresh loop to exit."""
        self._schedule_loop_stop.set()
        thread = self._schedule_loop_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def _schedule_loop_worker(self) -> None:
        while not self._schedule_loop_stop.is_set():
            try:
                self.run_schedule_refresh()
            except Exception as exc:  # noqa: BLE001
                self._log(
                    f"Schedule refresh loop error: {type(exc).__name__}: {exc}"
                )

            if self._schedule_loop_stop.is_set():
                break

            sleep_s = self._next_schedule_sleep_s()
            if self._schedule_loop_stop.wait(timeout=sleep_s):
                break

    def _next_schedule_sleep_s(self) -> float:
        """Seconds to wait before the next schedule refresh.

        Bounded to ``[60, _SCHEDULE_SLEEP_MAX_S]`` so a bogus or future
        ``lastSchedule`` (negative elapsed) or an oversized ``scheduleTimeout``
        never overflows the OS-level wait used by ``threading.Event.wait``.
        """
        timeout_s, _, _ = self._read_schedule_config()
        elapsed = time.time() - self._last_schedule_epoch()
        remaining = float(timeout_s) - max(0.0, elapsed)
        return min(max(60.0, remaining), float(timeout_s), self._SCHEDULE_SLEEP_MAX_S)

    def _anime_settings(self) -> dict[str, Any]:
        settings = getattr(self._config, "settings", None) or {}
        anime_cfg = settings.get("anime")
        if isinstance(anime_cfg, dict):
            return anime_cfg
        return {}

    def _read_schedule_config(self) -> tuple[int, int, int]:
        """Return ``(timeout_s, last_schedule, limit)`` from runtime settings."""
        anime_cfg = self._anime_settings()
        try:
            configured = int(anime_cfg.get("scheduleTimeout", self._SCHEDULE_MIN_INTERVAL_S))
        except (TypeError, ValueError):
            configured = self._SCHEDULE_MIN_INTERVAL_S
        timeout_s = max(configured, self._SCHEDULE_MIN_INTERVAL_S)
        try:
            last_schedule = int(anime_cfg.get("lastSchedule", 0))
        except (TypeError, ValueError):
            last_schedule = 0
        try:
            limit = int(anime_cfg.get("maxTrendingAnime", self._schedule_limit))
        except (TypeError, ValueError):
            limit = self._schedule_limit
        return timeout_s, last_schedule, max(1, limit)

    def _last_schedule_epoch(self) -> float:
        _, last_schedule, _ = self._read_schedule_config()
        return float(last_schedule)

    def _should_fetch_schedule(self) -> bool:
        timeout_s, last_schedule, _ = self._read_schedule_config()
        if last_schedule <= 0:
            return True
        return time.time() - float(last_schedule) >= float(timeout_s)

    def _mark_schedule_fetched(self) -> None:
        updater = getattr(self._config, "update_settings", None)
        if not callable(updater):
            return
        try:
            updater({"anime": {"lastSchedule": int(time.time())}})
        except Exception as exc:  # noqa: BLE001
            self._log(
                f"Failed persisting lastSchedule: {type(exc).__name__}: {exc}"
            )

    def _run_one(
        self, job: StartupJob, report: StartupJobReport
    ) -> None:
        start = time.perf_counter()
        db = self._database_manager.get_database()
        commits_before = safe_db_counter(db, "_commit_count")
        queries_before = safe_db_counter(db, "_query_count")
        try:
            detail = job.fn()
            elapsed = int((time.perf_counter() - start) * 1000)
            commits_after = safe_db_counter(db, "_commit_count")
            queries_after = safe_db_counter(db, "_query_count")
            self._telemetry.increment(
                f"startup.job.{job.name}_commits", max(0, commits_after - commits_before)
            )
            self._telemetry.increment(
                f"startup.job.{job.name}_queries", max(0, queries_after - queries_before)
            )
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
                f"Startup job '{job.name}' ok: {detail} ({elapsed} ms, "
                f"{commits_after - commits_before} commits, "
                f"{queries_after - queries_before} queries)"
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
        yield StartupJob(
            "purge_provisional_anime", self._job_purge_provisional_anime
        )
        if self._should_fetch_schedule():
            yield StartupJob("fetch_latest_anime", self._job_fetch_latest)
        else:
            yield StartupJob(
                "fetch_latest_anime",
                lambda: "skipped (recent fetch)",
            )
        yield StartupJob("update_status", self._job_update_status)
        yield StartupJob(
            "purge_deleted_torrents", self._job_purge_deleted_torrents
        )
        yield StartupJob(
            "reconcile_seen_anime_torrents",
            self._job_reconcile_seen_anime_torrents,
        )
        yield StartupJob(
            "reconcile_deleted_torrents", self._job_reconcile_deleted_torrents
        )
        yield StartupJob(
            "restore_libtorrent_sessions", self._job_restore_libtorrent_sessions
        )
        yield StartupJob("repair_torrent_index", self._job_repair_torrent_index)

    def _job_purge_deleted_torrents(self) -> str:
        adapter = self._download_adapter
        if adapter is None:
            return "skipped (no download adapter)"
        purge = getattr(adapter, "purge_deleted_torrents", None)
        if not callable(purge):
            return "skipped (no purge_deleted_torrents)"
        try:
            count = int(purge())
        except Exception as exc:
            return f"purge failed: {exc}"
        if count == 0:
            return "no deleted torrent resume files purged"
        return f"purged {count} deleted torrent artifact(s)"

    def _job_reconcile_seen_anime_torrents(self) -> str:
        adapter = self._download_adapter
        if adapter is None:
            return "skipped (no download adapter)"
        reconcile = getattr(adapter, "reconcile_seen_anime_torrents", None)
        if not callable(reconcile):
            return "skipped (no reconcile_seen_anime_torrents)"
        try:
            count = int(reconcile())
        except Exception as exc:
            return f"reconcile seen failed: {exc}"
        if count == 0:
            return "no SEEN anime torrents cleaned"
        return f"marked {count} torrent(s) deleted for SEEN anime"

    def _job_reconcile_deleted_torrents(self) -> str:
        adapter = self._download_adapter
        if adapter is None:
            return "skipped (no download adapter)"
        reconcile = getattr(adapter, "reconcile_deleted_torrents", None)
        if not callable(reconcile):
            return "skipped (no reconcile_deleted_torrents)"
        try:
            count = int(reconcile())
        except Exception as exc:
            return f"reconcile failed: {exc}"
        if count == 0:
            return "no torrents marked deleted"
        return f"marked {count} torrent(s) deleted"

    def _job_repair_torrent_index(self) -> str:
        adapter = self._download_adapter
        if adapter is None:
            return "skipped (no download adapter)"
        repair = getattr(adapter, "repair_torrent_index", None)
        if not callable(repair):
            return "skipped (no repair_torrent_index)"
        try:
            return str(repair())
        except Exception as exc:
            return f"repair failed: {exc}"

    def _job_restore_libtorrent_sessions(self) -> str:
        """Ensure embedded LibTorrent finished restore (idempotent)."""
        tm = self._torrent_manager
        if tm is None or getattr(tm, "name", None) != "LibTorrent":
            return "skipped (not LibTorrent)"
        ensure = getattr(tm, "ensure_restored", None)
        if not callable(ensure):
            return "skipped (no ensure_restored)"
        try:
            ensure()
        except Exception as exc:
            return f"restore failed: {exc}"
        count = len(getattr(tm, "handles", {}) or {})
        return f"session ready ({count} torrent(s))"

    def _read_enrich_catalog_limit(self) -> int:
        anime_cfg = self._anime_settings()
        try:
            limit = int(anime_cfg.get("enrichCatalogLimit", 200))
        except (TypeError, ValueError):
            limit = 200
        return max(1, limit)

    def _job_enrich_catalog_ids(self) -> str:
        """Backfill cross-provider ids for legacy single-provider index rows."""
        # Defer heavy enrichment so first HTTP/SSR requests are not competing
        # with hundreds of catalog lookups immediately after process start.
        time.sleep(8)
        result = self._database_manager.enrich_catalog_identities(
            limit=self._read_enrich_catalog_limit()
        )
        if result.looked_up == 0:
            return "no single-provider rows to enrich"
        return (
            f"enriched {result.enriched} row(s), merged {result.merged} duplicate(s)"
        )

    def _job_backfill_title_synonyms(self) -> str:
        """Hydrate catalogue rows that have a title but no saved synonyms."""
        api = getattr(self._api_coordinator, "_api", None)
        anime_fn = getattr(api, "anime", None) if api is not None else None
        if not callable(anime_fn):
            return "skipped (no API)"
        if self._write_service is None:
            return "skipped (no write service)"

        db = self._database_manager.get_database()
        if db is None:
            return "skipped (database not initialized)"

        limit = 50
        try:
            rows = db.sql(
                "SELECT a.id FROM anime a "
                "WHERE a.title IS NOT NULL AND TRIM(a.title) <> '' "
                "AND NOT EXISTS (SELECT 1 FROM title_synonyms ts WHERE ts.id = a.id) "
                "ORDER BY a.id DESC LIMIT ?",
                (limit,),
            )
        except Exception as exc:
            return f"scan failed: {exc}"

        ids = [int(row[0]) for row in rows or []]
        if not ids:
            return "no rows to backfill"

        hydrated = 0
        for catalog_id in ids:
            try:
                result = anime_fn(catalog_id, _persist=False)
            except Exception:
                continue
            if not result:
                continue
            persisted = self._write_service.persist_legacy_anime(
                result,
                source=WriteSource.BACKFILL,
                catalog_id=catalog_id,
            )
            if not persisted:
                continue
            try:
                synonyms = db.sql(
                    "SELECT 1 FROM title_synonyms WHERE id=? LIMIT 1",
                    (catalog_id,),
                )
            except Exception:
                synonyms = []
            if synonyms:
                hydrated += 1

        return f"hydrated {hydrated}/{len(ids)} row(s) missing synonyms"

    def _migration_done(self, key: str) -> bool:
        settings = getattr(self._config, "settings", None) or {}
        migrations = settings.get("startup_migrations") or {}
        if not isinstance(migrations, dict):
            return False
        return bool(migrations.get(key))

    def _mark_migration_done(self, key: str) -> None:
        updater = getattr(self._config, "update_settings", None)
        if not callable(updater):
            return
        try:
            updater({"startup_migrations": {key: True}})
        except Exception as exc:  # noqa: BLE001
            self._log(
                f"Failed persisting startup migration '{key}': "
                f"{type(exc).__name__}: {exc}"
            )

    def _job_repair_duplicate_anime(self) -> str:
        """Collapse duplicate ``indexList`` / ``anime`` rows left from pre-merge ingest."""
        merged = self._database_manager.repair_duplicate_anime_entries()
        if self._migration_done("repair_duplicate_anime"):
            if merged == 0:
                return "no provider duplicate rows to repair"
            return f"merged {merged} provider duplicate row(s)"

        title_merged = self._database_manager.repair_duplicate_anime_entries(
            title_only=True
        )
        self._mark_migration_done("repair_duplicate_anime")
        total = merged + title_merged
        if total == 0:
            return "no duplicate rows to repair"
        return (
            f"merged {total} duplicate row(s) "
            f"(provider={merged}, title={title_merged})"
        )

    def _job_purge_provisional_anime(self) -> str:
        """Remove orphan anime rows whose id is a leaked provisional fingerprint."""
        deleted = self._database_manager.purge_provisional_anime_rows()
        if deleted == 0:
            return "no provisional anime rows to purge"
        return f"purged {deleted} provisional anime row(s)"

    # Any ``date_from`` / ``date_to`` value smaller than this threshold
    # is treated as a legacy ``datetime.toordinal()`` value (days since
    # year 1, ~1e6 for modern dates) and converted to a UTC Unix
    # timestamp. ``2_000_000`` keeps a wide safety margin around the
    # largest plausible ordinal date (~3.65e6 for year 9999) while
    # being orders of magnitude below the smallest plausible Unix
    # timestamp the codebase ever stored (1.0e8 ~ 1973).
    _ORDINAL_THRESHOLD = 2_000_000

    _DATE_REPAIR_BATCH_SIZE = 100

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
        if self._migration_done("repair_date_from"):
            return "skipped (migration complete)"

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
            self._mark_migration_done("repair_date_from")
            return "no rows to repair"

        repaired_from = 0
        repaired_to = 0
        pending: list[tuple[list[str], list[Any]]] = []
        pinned_ctx = getattr(db, "pinned_pool_connection", None)
        use_pool = bool(getattr(db, "USE_CONNECTION_POOL", False))

        def _flush_repairs(batch: list[tuple[list[str], list[Any]]]) -> None:
            if not batch:
                return

            def _apply() -> None:
                for sets, params in batch:
                    db.sql(
                        f"UPDATE anime SET {', '.join(sets)} WHERE id=%s",
                        params,
                        save=False,
                    )
                commit_pinned = getattr(db, "commit_pinned_connection", None)
                if callable(commit_pinned):
                    commit_pinned()
                elif hasattr(db, "save"):
                    db.save()

            if pinned_ctx is not None and use_pool:
                with pinned_ctx():
                    _apply()
            else:
                with db.get_lock():
                    _apply()

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
            pending.append((sets, params))
            if len(pending) >= self._DATE_REPAIR_BATCH_SIZE:
                try:
                    _flush_repairs(pending)
                except Exception as exc:
                    self._log(
                        f"date_from repair batch failed: "
                        f"{type(exc).__name__}: {exc}"
                    )
                else:
                    pending.clear()

        if pending:
            try:
                _flush_repairs(pending)
            except Exception as exc:
                self._log(
                    f"date_from repair batch failed: "
                    f"{type(exc).__name__}: {exc}"
                )

        self._mark_migration_done("repair_date_from")
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

    def _db_gateway_writes_only(self) -> bool:
        settings = getattr(self._config, "settings", None) or {}
        flags = settings.get("feature_flags") or {}
        if not isinstance(flags, dict):
            return True
        return bool(flags.get("db_gateway_writes_only", True))

    def _job_fetch_latest(self) -> str:
        """Pull the latest anime data from every provider's schedule."""
        self._wait_for_api_providers_ready()
        _, _, limit = self._read_schedule_config()
        effective_limit = max(limit, self._schedule_limit)
        result: Optional[IngestionResult] = (
            self._api_coordinator.fetch_latest(
                limit=effective_limit,
                per_provider=False,
            )
        )
        if result is None:
            return "skipped (no providers / API unavailable)"

        records = result.records or []
        persisted = int(getattr(result, "persisted_count", 0) or 0)

        # When ``db_gateway_writes_only`` is on the ingestion pipeline
        # sink already persisted the deduplicated batch. Re-running
        # ``upsert_anime_batch`` here doubled pool pressure and, under
        # MariaDB's small connection pool, caused every row to fail with
        # ``pool exhausted`` while still marking ``lastSchedule``.
        if (
            records
            and self._database_manager is not None
            and not self._db_gateway_writes_only()
        ):
            try:
                animes = [
                    APICoordinator._record_to_anime(record) for record in records
                ]
                persisted = self._database_manager.upsert_anime_batch(animes)
            except Exception as exc:  # noqa: BLE001 - logged at top level
                raise RuntimeError(
                    f"Schedule persistence failed: {type(exc).__name__}: {exc}"
                ) from exc

        if result.status == IngestionStatus.FAILED:
            return (
                f"providers={result.total_providers} failed="
                f"{result.failed_providers} records=0"
            )

        if records and persisted <= 0:
            return (
                f"providers={result.total_providers} failed="
                f"{result.failed_providers} records={len(records)} "
                f"persisted=0 (will retry on next startup)"
            )

        self._mark_schedule_fetched()
        return (
            f"providers={result.total_providers} failed="
            f"{result.failed_providers} records={len(records)} "
            f"persisted={persisted}"
        )

    def _wait_for_api_providers_ready(self, *, timeout: float = 120.0) -> None:
        """Block until background API provider loading finishes."""
        api = getattr(self._api_coordinator, "_api", None)
        if api is None:
            return
        init_thread = getattr(api, "init_thread", None)
        if init_thread is not None and init_thread.is_alive():
            init_thread.join(timeout=timeout)
            if init_thread.is_alive():
                self._log(
                    f"API provider init still running after {timeout:.0f}s timeout"
                )
                return
        providers = []
        if hasattr(api, "get_providers"):
            providers = [p for p in api.get_providers() if p is not None]
        if providers:
            self._log(f"API providers ready: {len(providers)}")

    def _job_update_status(self) -> str:
        """Transition stale ``UPCOMING`` / ``AIRING`` rows by airing dates."""
        from shared.config.getters import Getters

        db = self._database_manager.get_database()
        if db is None:
            return "skipped (database not initialized)"

        now_ts = datetime.now(timezone.utc).timestamp()
        transitions: dict[str, list[int]] = {}

        try:
            upcoming_rows = db.sql(
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

        for row in upcoming_rows:
            anime_id, _status, date_from, date_to, episodes = (
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
                    break
            except (TypeError, ValueError):
                continue

            anime = Anime(
                {
                    "id": anime_id,
                    "status": None,
                    "date_from": date_from,
                    "date_to": date_to,
                    "episodes": episodes,
                }
            )
            new_status = Getters.getStatus(anime)
            if not new_status or new_status == "UPCOMING":
                continue
            transitions.setdefault(new_status, []).append(int(anime_id))

        try:
            airing_rows = db.sql(
                "SELECT id, status, date_from, date_to, episodes "
                "FROM anime "
                "WHERE status='AIRING' "
                "AND date_to IS NOT NULL "
                "AND date_to <= %s",
                [now_ts],
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed reading airing anime rows: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        for row in airing_rows:
            anime_id = int(row[0])
            transitions.setdefault("FINISHED", []).append(anime_id)

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
        log_fn = getattr(self._logger, "log", None)
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
