"""One-shot catalogue identity enrichment + duplicate repair.

Usage (from repo root, with venv Python):
    .\\.venv\\Scripts\\python.exe scripts/repair_catalog_identities.py
    .\\.venv\\Scripts\\python.exe scripts/repair_catalog_identities.py --limit 50
    .\\.venv\\Scripts\\python.exe scripts/repair_catalog_identities.py --limit 0

Run repeatedly with the default (--limit 50). The script auto-advances
through the queue via ``.repair_catalog_identities.cursor`` so skipped
rows at the head do not block progress. Use ``--reset-cursor`` to start
over. Stop the web app (run.py) during repair to avoid MariaDB lock contention.
"""

from __future__ import annotations

import argparse
import atexit
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.metadata.catalog_mapping_adapter import CatalogMappingAdapter
from application.services.catalog_enrichment import CatalogEnrichmentService
from application.services.database_manager import DatabaseManager
from shared.config.constants import Constants
from shared.config.getters import Getters

_LOCK_PATH = ROOT / ".repair_catalog_identities.lock"
_CURSOR_PATH = ROOT / ".repair_catalog_identities.cursor"
_SLOW_ROW_S = 15.0


class _DbHost:
    def __init__(self) -> None:
        self.constants = Constants()


class _ProcessLock:
    """Best-effort single-instance guard (works on Windows and Unix)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fh = None

    def acquire(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self._path, "a+", encoding="utf-8")
        try:
            if os.name == "nt":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise SystemExit(
                "Another repair_catalog_identities run is already active "
                f"({self._path}). Stop it first."
            ) from exc
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(str(os.getpid()))
        self._fh.flush()
        atexit.register(self.release)

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            self._fh.close()
        except OSError:
            pass
        self._fh = None
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            pass


def _count_single_provider(db) -> int:
    rows = db.sql(
        "SELECT COUNT(*) FROM indexList WHERE ("
        "(mal_id IS NOT NULL) + (kitsu_id IS NOT NULL) + "
        "(anilist_id IS NOT NULL) + (anidb_id IS NOT NULL)"
        ") = 1"
    )
    return int(rows[0][0]) if rows else 0


def _count_index_rows(db) -> int:
    rows = db.sql("SELECT COUNT(*) FROM indexList")
    return int(rows[0][0]) if rows else 0


def _read_cursor() -> int:
    try:
        text = _CURSOR_PATH.read_text(encoding="utf-8").strip()
        return max(0, int(text))
    except (OSError, ValueError):
        return 0


def _write_cursor(offset: int) -> None:
    _CURSOR_PATH.write_text(str(max(0, int(offset))), encoding="utf-8")


def _list_single_provider_ids(
    db, *, limit: int = 0, offset: int = 0
) -> list[int]:
    sql = (
        "SELECT id FROM indexList WHERE ("
        "(mal_id IS NOT NULL) + (kitsu_id IS NOT NULL) + "
        "(anilist_id IS NOT NULL) + (anidb_id IS NOT NULL)"
        ") = 1 ORDER BY id DESC"
    )
    params: list[int] = []
    if limit > 0:
        sql += " LIMIT ?"
        params.append(int(limit))
    if offset > 0:
        sql += " OFFSET ?"
        params.append(int(offset))
    rows = db.sql(sql, tuple(params))
    return [int(row[0]) for row in rows or []]


def _render_progress(
    current: int,
    total: int,
    *,
    catalog_id: int,
    enriched: int,
    merged: int,
    skipped: int,
    width: int = 40,
) -> str:
    if total <= 0:
        pct = 100.0
        filled = width
    else:
        pct = (current / total) * 100.0
        filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    return (
        f"[{bar}] {current}/{total} ({pct:5.1f}%) id={catalog_id} "
        f"enriched={enriched} merged={merged} skipped={skipped}"
    )


def _print_progress(line: str) -> None:
    sys.stdout.write("\r" + line)
    sys.stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill cross-provider ids and repair duplicate catalogue rows."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max single-provider rows to process per run (default: 50). Use 0 for all.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.05,
        help="Seconds between row lookups (default: 0.05).",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=-1,
        help="Skip this many single-provider rows (default: auto from cursor file).",
    )
    parser.add_argument(
        "--reset-cursor",
        action="store_true",
        help="Start again from offset 0 instead of continuing the saved cursor.",
    )
    args = parser.parse_args()

    lock = _ProcessLock(_LOCK_PATH)
    lock.acquire()

    if args.reset_cursor:
        _write_cursor(0)

    batch_limit = int(args.limit)
    if batch_limit == 0:
        cursor_offset = 0
    elif args.offset >= 0:
        cursor_offset = int(args.offset)
    else:
        cursor_offset = _read_cursor()

    print("Connecting to database...", flush=True)
    host = _DbHost()
    db = Getters.getDatabase(host)
    print("Connected.", flush=True)

    db_manager = DatabaseManager()
    db_manager.set_database(db)
    db_manager.set_mapping_port(CatalogMappingAdapter())

    index_rows = _count_index_rows(db)
    single_before = _count_single_provider(db)
    print(f"indexList rows: {index_rows}")
    print(f"single-provider rows to process: {single_before}", flush=True)

    if single_before == 0:
        print("Nothing to enrich.")
    else:
        pending_ids = _list_single_provider_ids(
            db,
            limit=batch_limit if batch_limit > 0 else 0,
            offset=cursor_offset if batch_limit > 0 else 0,
        )
        total = len(pending_ids)
        if total == 0:
            print(
                f"No rows at offset {cursor_offset}. "
                "Use --reset-cursor to start over."
            )
        else:
            print(
                f"Processing {total} row(s) at offset {cursor_offset}...",
                flush=True,
            )

        enriched = merged = skipped = looked_up = 0
        start = time.perf_counter()
        mapping = CatalogMappingAdapter()
        log_ctx = {"catalog_id": 0}

        def _log_fn(msg: str) -> None:
            print(
                f"\nWARN id={log_ctx['catalog_id']}: {msg}",
                flush=True,
            )

        service = CatalogEnrichmentService(db, mapping, log_fn=_log_fn)
        slow_rows: list[tuple[int, float]] = []
        processed = 0

        try:
            for idx, catalog_id in enumerate(pending_ids, start=1):
                processed = idx
                log_ctx["catalog_id"] = catalog_id
                row_start = time.perf_counter()
                row = service.enrich_ids([catalog_id])
                row_elapsed = time.perf_counter() - row_start
                if row_elapsed >= _SLOW_ROW_S:
                    slow_rows.append((catalog_id, row_elapsed))
                    print(
                        f"\nSLOW id={catalog_id} took {row_elapsed:.1f}s",
                        flush=True,
                    )

                looked_up += row.looked_up
                enriched += row.enriched
                merged += row.merged
                if row.looked_up == 0:
                    skipped += 1
                _print_progress(
                    _render_progress(
                        idx,
                        total,
                        catalog_id=catalog_id,
                        enriched=enriched,
                        merged=merged,
                        skipped=skipped,
                    )
                )
                if args.sleep > 0:
                    time.sleep(args.sleep)
        except KeyboardInterrupt:
            print("\nInterrupted.", flush=True)
            if batch_limit > 0 and processed > 0:
                next_offset = cursor_offset + processed
                _write_cursor(next_offset)
                print(
                    f"Saved cursor at offset {next_offset} "
                    f"({processed}/{total} row(s) processed).",
                    flush=True,
                )
            raise SystemExit(130) from None

        elapsed = time.perf_counter() - start
        print()
        if total > 0:
            print(
                f"Enrichment done in {elapsed:.1f}s: "
                f"looked_up={looked_up} enriched={enriched} merged={merged} skipped={skipped}"
            )
            if slow_rows:
                print(f"slow rows (>={_SLOW_ROW_S:.0f}s): {len(slow_rows)}")
            print(f"single-provider rows remaining: {_count_single_provider(db)}")
            if batch_limit > 0:
                next_offset = cursor_offset + total
                _write_cursor(next_offset)
                print(f"next offset: {next_offset}")

    print("Running duplicate repair...", flush=True)
    repaired = db_manager.repair_duplicate_anime_entries()
    print(f"repair_duplicate merged: {repaired}")
    print(f"indexList rows after: {_count_index_rows(db)}")
    print(f"single-provider rows after: {_count_single_provider(db)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
