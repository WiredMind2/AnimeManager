"""One-shot cleanup: remove torrents and library folders for SEEN anime.

Usage (from repo root, with venv Python):
    .\\.venv\\Scripts\\python.exe scripts/cleanup_seen_anime_folders.py --dry-run
    .\\.venv\\Scripts\\python.exe scripts/cleanup_seen_anime_folders.py

Stop the web app (run.py) during the live run to avoid MariaDB lock contention
and torrent-client races.
"""

from __future__ import annotations

import argparse
import atexit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.persistence.user_actions_repository import UserActionsRepository
from adapters.torrent.download_adapter import DownloadAdapter
from composition.bootstrap import bootstrap_embedded_deps

_LOCK_PATH = ROOT / ".cleanup_seen_anime_folders.lock"


def _acquire_lock() -> None:
    if _LOCK_PATH.exists():
        raise SystemExit(
            f"Lock file exists ({_LOCK_PATH}). Another cleanup may be running."
        )
    _LOCK_PATH.write_text("locked", encoding="utf-8")

    def _release() -> None:
        try:
            _LOCK_PATH.unlink(missing_ok=True)
        except OSError:
            pass

    atexit.register(_release)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete torrents and library folders for anime tagged SEEN."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List SEEN anime and folders that would be deleted; make no changes.",
    )
    args = parser.parse_args()

    _acquire_lock()
    deps = bootstrap_embedded_deps()
    user_actions = UserActionsRepository(deps.database)
    adapter = DownloadAdapter(
        torrent_manager=deps.torrent_manager,
        file_manager=deps.file_manager,
        db_manager=deps.db_manager,
        scanner=deps.scanner,
        user_actions=user_actions,
        repository=None,
    )

    anime_ids = user_actions.list_anime_ids_with_tag("SEEN")
    anime_path = str(deps.anime_path or "").strip()
    print(f"Animes root: {anime_path or '(unset)'}")
    print(f"SEEN anime: {len(anime_ids)}")

    if not anime_ids:
        print("Nothing to clean.")
        return 0

    would_delete = 0
    for anime_id in anime_ids:
        folder = ""
        try:
            folder = str(deps.scanner.resolve_anime_folder(int(anime_id)) or "").strip()
        except Exception as exc:
            print(f"  anime={anime_id} resolve_failed={exc}")
            continue

        exists = False
        if folder and deps.file_manager is not None:
            try:
                exists = bool(deps.file_manager.exists(folder))
            except Exception:
                exists = False

        if exists:
            would_delete += 1
        print(
            f"  anime={anime_id} folder={folder or '(none)'} "
            f"exists={'yes' if exists else 'no'}"
        )

        if args.dry_run:
            continue

        try:
            marked = adapter.mark_torrents_deleted_for_seen_anime(int(anime_id))
            print(f"    cleaned torrents={marked}")
        except Exception as exc:
            print(f"    cleanup_failed={exc}")

    if args.dry_run:
        print(f"Dry run: {would_delete} existing folder(s) would be deleted.")
        return 0

    print(f"Cleanup finished for {len(anime_ids)} SEEN anime.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
