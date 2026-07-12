"""One-shot torrent index repair for on-disk anime libraries.

Usage (from repo root, with venv Python):
    .\\.venv\\Scripts\\python.exe scripts/repair_torrent_index.py --dry-run
    .\\.venv\\Scripts\\python.exe scripts/repair_torrent_index.py

Stop the web app (run.py) during repair to avoid MariaDB lock contention.
"""

from __future__ import annotations

import argparse
import atexit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.torrent.download_adapter import DownloadAdapter
from application.services.database_manager import DatabaseManager
from application.services.torrent_index_repair import TorrentIndexRepairService
from composition.bootstrap import bootstrap_embedded_deps

_LOCK_PATH = ROOT / ".repair_torrent_index.lock"


def _acquire_lock() -> None:
    if _LOCK_PATH.exists():
        raise SystemExit(
            f"Lock file exists ({_LOCK_PATH}). Another repair may be running."
        )
    _LOCK_PATH.write_text("locked", encoding="utf-8")

    def _release() -> None:
        try:
            _LOCK_PATH.unlink(missing_ok=True)
        except OSError:
            pass

    atexit.register(_release)


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair missing torrentsIndex rows.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report issues and planned repairs without writing to the database.",
    )
    args = parser.parse_args()

    _acquire_lock()
    deps = bootstrap_embedded_deps()
    adapter = DownloadAdapter(
        torrent_manager=deps.torrent_manager,
        file_manager=deps.file_manager,
        db_manager=deps.db_manager,
        scanner=deps.scanner,
        user_actions=None,
        repository=None,
    )
    service = TorrentIndexRepairService(
        db_manager=deps.db_manager,
        scanner=deps.scanner,
        torrent_manager=deps.torrent_manager,
        file_manager=deps.file_manager,
        anime_path=deps.anime_path,
        log_fn=lambda cat, msg: print(f"[{cat}] {msg}"),
    )

    issues = service.detect_issues()
    if issues:
        print(f"Detected {len(issues)} issue(s):")
        for issue in issues:
            print(
                f"  anime={issue.anime_id} kind={issue.kind} "
                f"folder={issue.folder} {issue.detail}"
            )
    else:
        print("No library issues detected.")

    if args.dry_run:
        summary = adapter.repair_torrent_index(dry_run=True)
        print(summary)
        return 0

    summary = adapter.repair_torrent_index(dry_run=False)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
