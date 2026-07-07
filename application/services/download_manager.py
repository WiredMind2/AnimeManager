"""
DownloadManager - orchestrates torrent and HTTP file downloads.

The manager is intentionally narrow:

* validate any outbound URL through :func:`shared.security.validate_url`
  before issuing a request,
* delegate torrent persistence to an injected :class:`DatabaseManager`
  (so all DB writes stay behind one gateway),
* expose a small status-queue API for callers waiting on a download.

The legacy event-bus subscriptions that drove ``download.start`` /
``download.cancel`` have been removed; clients now call
:meth:`download_file` / :meth:`cancel_download` directly through
``adapters.torrent.download_adapter.DownloadAdapter``.
"""

import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from shared.base_component import BaseComponent
from shared.security import validate_url
from adapters.persistence.models import Magnet, Torrent


class DownloadManager(BaseComponent):
    """
    Manages file and torrent downloads with progress tracking and error handling.
    Coordinates between torrent managers and file managers.
    """

    # Minimum gap (seconds) between two consecutive torrent-manager polls
    # triggered by status reads. The web UI polls ``/download/active`` every
    # ~4s and the Tk presenter every ~2s, so a 0.5s floor is invisible to
    # users yet keeps a burst of concurrent readers from hammering the
    # torrent client.
    _STATUS_REFRESH_INTERVAL_S: float = 0.5

    def __init__(self, *, max_concurrent_downloads: int = 3):
        super().__init__("DownloadManager")
        self._torrent_manager = None
        self._file_manager = None
        self._database_manager = None
        self._active_downloads: Dict[int, "DownloadTask"] = {}
        self._download_queue: "queue.Queue[DownloadTask]" = queue.Queue()
        self._max_concurrent_downloads = max_concurrent_downloads
        self._lock = threading.RLock()
        self._last_status_refresh: float = 0.0
        self._watching_tag_callback: Optional[Callable[[int, int], None]] = None
        # Self-initialize so adapters don't have to drive a lifecycle.
        self._executor: Optional[ThreadPoolExecutor] = ThreadPoolExecutor(
            max_workers=max_concurrent_downloads
        )
        self._stopping = threading.Event()
        self._processor = threading.Thread(
            target=self._process_download_queue,
            daemon=True,
            name="DownloadProcessor",
        )
        self._processor.start()

    def close(self) -> None:
        """Cancel in-flight downloads and release worker resources."""
        self._stopping.set()
        with self._lock:
            for task in self._active_downloads.values():
                task.cancel()
            self._active_downloads.clear()
        executor = self._executor
        self._executor = None
        if executor is not None:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                executor.shutdown(wait=False)
        self.log("DOWNLOAD_MANAGER", "Download Manager stopped")

    def _stop(self) -> None:
        """Lifecycle alias for :meth:`close`."""
        self.close()

    def set_torrent_manager(self, torrent_manager) -> None:
        """Attach the underlying torrent client manager."""
        self._torrent_manager = torrent_manager

    def set_file_manager(self, file_manager) -> None:
        """Attach the underlying file system manager."""
        self._file_manager = file_manager

    def set_database_manager(self, database_manager) -> None:
        """Attach the database manager used to persist torrent metadata."""
        self._database_manager = database_manager

    def set_watching_tag_callback(
        self, callback: Optional[Callable[[int, int], None]]
    ) -> None:
        """Notify when a download starts so the UI tag can move to ``WATCHING``."""
        self._watching_tag_callback = callback

    def download_file(self, anime_id: int, url: Optional[str] = None,
                     hash_value: Optional[str] = None, user_id: Optional[int] = None) -> Optional[queue.Queue]:
        """
        Download a file or torrent.

        Args:
            anime_id: Anime ID
            url: URL to download from
            hash_value: Torrent hash for existing torrent
            user_id: User ID for tagging

        Returns:
            Queue for download status updates
        """
        if not url and not hash_value:
            self.log("DOWNLOAD_MANAGER", "[ERROR] - No URL or hash provided")
            return None

        self._clear_deleted_status_for_redownload(hash_value)

        task = DownloadTask(anime_id, url, hash_value, user_id)
        self._download_queue.put(task)

        self.log("DOWNLOAD_MANAGER", f"Queued download for anime {anime_id}")
        return task.status_queue

    def redownload(self, anime_id: int) -> int:
        """
        Redownload all torrents for an anime.

        Args:
            anime_id: Anime ID

        Returns:
            Number of torrents queued for redownload
        """
        self.log("DOWNLOAD_MANAGER", f"Redownload requested for anime {anime_id}")
        return 0

    def cancel_download(self, anime_id: int) -> bool:
        """
        Cancel download for an anime.

        Args:
            anime_id: Anime ID

        Returns:
            True if download was cancelled, False otherwise
        """
        with self._lock:
            task = self._active_downloads.pop(anime_id, None)
        if task is not None:
            task.cancel()
            self.log("DOWNLOAD_MANAGER", f"Cancelled download for anime {anime_id}")
            return True

        self.log("DOWNLOAD_MANAGER", f"No active download found for anime {anime_id}")
        return False

    def get_download_status(self, anime_id: int) -> Optional[Dict[str, Any]]:
        """
        Get download status for an anime.

        Args:
            anime_id: Anime ID

        Returns:
            Status dictionary or None
        """
        self._refresh_active_task_status()
        with self._lock:
            task = self._active_downloads.get(anime_id)
            if task:
                return task.get_status()

        return None

    def get_active_downloads(self) -> List[Dict[str, Any]]:
        """
        Get list of all active downloads.

        Returns:
            List of download status dictionaries
        """
        self._refresh_active_task_status()
        with self._lock:
            return [task.get_status() for task in self._active_downloads.values()]

    # ------------------------------------------------------------------
    # Unified torrent overview (downloading / seeding / completed)
    # ------------------------------------------------------------------

    # Lowercase state tokens used by libtorrent and qBittorrent that we
    # bucket into a single normalised category. Anything not listed
    # here falls back to ``"other"`` so unknown states still surface in
    # the UI instead of being silently dropped.
    _ACTIVE_STATES = frozenset({
        "downloading",
        "downloading_metadata",
        "metadl",
        "queueddl",
        "stalleddl",
        "forceddl",
        "checkingdl",
        "checking",
        "checking_files",
        "checking_resume",
        "checking_resume_data",
        "allocating",
        "queued",
        "queued_for_checking",
    })
    _SEEDING_STATES = frozenset({
        "seeding",
        "uploading",
        "stalledup",
        "queuedup",
        "forcedup",
        "checkingup",
    })
    _COMPLETED_STATES = frozenset({
        "finished",
        "pausedup",
        "complete",
        "completed",
    })
    _ERROR_STATES = frozenset({
        "error",
        "missingfiles",
    })

    @classmethod
    def _normalise_category(cls, state: Optional[str], progress: Optional[float]) -> str:
        """Bucket a torrent ``state`` into one of the overview categories.

        Falls back to inspecting ``progress`` for adapters that don't
        emit a state string (or emit something we haven't seen yet):
        a 100% torrent is treated as ``"completed"``, anything less is
        ``"active"``.
        """
        token = (state or "").strip().lower().replace(" ", "_")
        if token in cls._ACTIVE_STATES:
            return "active"
        if token in cls._SEEDING_STATES:
            return "seeding"
        if token in cls._COMPLETED_STATES:
            return "completed"
        if token in cls._ERROR_STATES:
            return "error"
        if isinstance(progress, (int, float)):
            if progress >= 0.999:
                return "completed"
            if progress > 0:
                return "active"
        if token:
            return "other"
        return "other"

    def get_torrents_overview(self) -> Dict[str, List[Dict[str, Any]]]:
        """Return every torrent the torrent client knows about, bucketed.

        The result is shaped as::

            {
                "active":    [<entry>, ...],
                "seeding":   [<entry>, ...],
                "completed": [<entry>, ...],
                "error":     [<entry>, ...],
                "other":     [<entry>, ...],
            }

        Each ``entry`` is a homogeneous dict mirroring the legacy
        ``get_active_downloads()`` shape (``hash``, ``name``,
        ``progress``, ``state``, ``dl_speed``, ``eta``, ``size``,
        ``downloaded``, ``anime_id``, ``path``) plus an ``up_speed``
        field that the previous shape ignored. Entries are correlated
        back to anime via the persisted torrent index, so a torrent
        that was added in a previous session is still labelled
        correctly without needing an in-memory :class:`DownloadTask`.
        Torrents that have no matching anime row are still returned so
        the user can see them and decide whether to clean them up.
        """
        empty: Dict[str, List[Dict[str, Any]]] = {
            "active": [],
            "seeding": [],
            "completed": [],
            "error": [],
            "other": [],
        }
        tm = self._torrent_manager
        if tm is None:
            return empty

        ensure = getattr(tm, "ensure_restored", None)
        if callable(ensure):
            try:
                ensure()
            except Exception as exc:
                self.log(
                    "DOWNLOAD_MANAGER",
                    f"LibTorrent restore wait failed: {exc}",
                )

        try:
            rows = tm.list() or []
        except Exception as exc:
            self.log("DOWNLOAD_MANAGER", f"Failed to list torrents: {exc}")
            return empty

        # Capture the in-memory task map under the lock so we can
        # cross-reference live torrents with the anime they were
        # started for in this session without holding the lock during
        # the (potentially slow) DB roundtrip below.
        with self._lock:
            task_by_hash: Dict[str, "DownloadTask"] = {
                str(t.hash_value).lower(): t
                for t in self._active_downloads.values()
                if t.hash_value
            }

        hashes: List[str] = []
        normalised_rows: List[Dict[str, Any]] = []
        for entry in rows:
            if entry is None:
                continue
            h = self._extract_torrent_field(entry, "hash")
            if not h:
                continue
            h_lower = str(h).strip().lower()
            normalised_rows.append({"_raw": entry, "_hash": h_lower})
            hashes.append(h_lower)

        anime_map: Dict[str, int] = {}
        title_map: Dict[int, str] = {}
        db_manager = self._database_manager
        if db_manager is not None and hashes:
            try:
                anime_map = db_manager.get_anime_ids_by_hashes(hashes) or {}
            except Exception as exc:
                self.log(
                    "DOWNLOAD_MANAGER",
                    f"Could not resolve anime ids for overview: {exc}",
                )
                anime_map = {}
            if anime_map:
                try:
                    title_map = db_manager.get_anime_titles(
                        list({aid for aid in anime_map.values()})
                    ) or {}
                except Exception as exc:
                    self.log(
                        "DOWNLOAD_MANAGER",
                        f"Could not resolve anime titles for overview: {exc}",
                    )
                    title_map = {}

        out = {key: [] for key in empty}
        for entry in normalised_rows:
            data = entry["_raw"]
            h_lower = entry["_hash"]
            size = self._extract_torrent_field(data, "size")
            downloaded = self._extract_torrent_field(data, "downloaded")
            progress = self._extract_torrent_field(data, "progress")
            if progress is None and size and downloaded is not None:
                try:
                    size_f = float(size)
                    if size_f > 0:
                        progress = float(downloaded) / size_f
                except (TypeError, ValueError):
                    progress = None
            if isinstance(progress, (int, float)):
                progress = max(0.0, min(1.0, float(progress)))

            state_raw = self._extract_torrent_field(data, "state")
            category = self._normalise_category(state_raw, progress)

            anime_id = anime_map.get(h_lower)
            task = task_by_hash.get(h_lower)
            if anime_id is None and task is not None:
                anime_id = task.anime_id

            name = self._extract_torrent_field(data, "name")
            if not name and task is not None:
                name = task.name
            if not name and anime_id is not None:
                name = title_map.get(anime_id) or f"Anime #{anime_id}"
            if not name:
                name = h_lower or "Unknown torrent"

            dl_speed = self._extract_torrent_field(data, "dl_speed")
            up_speed = self._extract_torrent_field(data, "up_speed")
            if up_speed is None:
                up_speed = self._extract_torrent_field(data, "upload_rate")
            eta = self._extract_torrent_field(data, "eta")
            path = self._extract_torrent_field(data, "path")

            row: Dict[str, Any] = {
                "hash": h_lower,
                "name": str(name),
                "anime_id": int(anime_id) if anime_id is not None else None,
                "anime_title": title_map.get(int(anime_id)) if anime_id is not None else None,
                "state": str(state_raw).upper() if state_raw else None,
                "category": category,
                "progress": progress,
                "size": int(size) if isinstance(size, (int, float)) and size >= 0 else None,
                "downloaded": int(downloaded) if isinstance(downloaded, (int, float)) and downloaded >= 0 else None,
                "dl_speed": float(dl_speed) if isinstance(dl_speed, (int, float)) and dl_speed >= 0 else None,
                "up_speed": float(up_speed) if isinstance(up_speed, (int, float)) and up_speed >= 0 else None,
                "eta": int(eta) if isinstance(eta, (int, float)) and eta >= 0 else None,
                "path": str(path) if path else None,
            }
            self._maybe_mark_torrent_complete(h_lower, state_raw, progress)
            out[category].append(row)

        # Also surface tasks that are queued/preparing but haven't been
        # registered with the torrent client yet (the torrent_manager
        # ``list()`` call would skip them otherwise). They show up as
        # "active" so the user gets immediate feedback right after
        # clicking Download.
        seen_hashes = {row["hash"] for bucket in out.values() for row in bucket if row.get("hash")}
        with self._lock:
            for task in self._active_downloads.values():
                h_lower = (
                    str(task.hash_value).strip().lower()
                    if task.hash_value
                    else None
                )
                if h_lower and h_lower in seen_hashes:
                    continue
                status = task.get_status()
                category = self._normalise_category(status.get("state"), status.get("progress"))
                out[category].append(
                    {
                        "hash": h_lower,
                        "name": status.get("name") or (
                            f"Anime #{status['anime_id']}"
                            if status.get("anime_id")
                            else "Pending download"
                        ),
                        "anime_id": status.get("anime_id"),
                        "anime_title": None,
                        "state": status.get("state"),
                        "category": category,
                        "progress": status.get("progress"),
                        "size": status.get("size"),
                        "downloaded": status.get("downloaded"),
                        "dl_speed": status.get("dl_speed"),
                        "up_speed": None,
                        "eta": status.get("eta"),
                        "path": status.get("path"),
                    }
                )

        return out

    def _refresh_active_task_status(self) -> None:
        """Pull live progress / state from the torrent manager into each task.

        :class:`DownloadTask` only captures what we know at scheduling time
        (URL, hash, name). Without a periodic poll, the ``progress`` /
        ``downloaded`` / ``dl_speed`` fields stay frozen at their initial
        value and the UI progress bar never moves even though the torrent
        client is happily downloading in the background.

        This helper is invoked from every status getter so the polling
        cost is paid only when somebody is actually watching. We throttle
        the underlying ``torrent_manager.list()`` call to at most one
        invocation per :attr:`_STATUS_REFRESH_INTERVAL_S` to keep
        bursty pollers (web UI + Tk + API clients in parallel) from
        flogging the torrent client.
        """
        tm = self._torrent_manager
        if tm is None:
            return

        now = time.time()
        if now - self._last_status_refresh < self._STATUS_REFRESH_INTERVAL_S:
            return

        with self._lock:
            hashes = [t.hash_value for t in self._active_downloads.values() if t.hash_value]

        if not hashes:
            self._last_status_refresh = now
            return

        try:
            results = tm.list(hashes=hashes)
        except TypeError:
            # Some adapters predate the ``hashes`` keyword; fall back to a
            # broader query and filter on our side.
            try:
                results = tm.list()
            except Exception as exc:
                self.log("DOWNLOAD_MANAGER", f"Failed to refresh torrent status: {exc}")
                self._last_status_refresh = now
                return
        except Exception as exc:
            self.log("DOWNLOAD_MANAGER", f"Failed to refresh torrent status: {exc}")
            self._last_status_refresh = now
            return

        self._last_status_refresh = now

        if not results:
            return

        by_hash: Dict[str, Any] = {}
        for entry in results:
            if entry is None:
                continue
            h = self._extract_torrent_field(entry, "hash")
            if h:
                by_hash[str(h).lower()] = entry

        if not by_hash:
            return

        with self._lock:
            for task in self._active_downloads.values():
                if not task.hash_value:
                    continue
                data = by_hash.get(str(task.hash_value).lower())
                if data is None:
                    continue
                self._apply_torrent_status_to_task(task, data)

    @staticmethod
    def _extract_torrent_field(obj: Any, name: str, default: Any = None) -> Any:
        """Read ``name`` from a torrent-manager list result.

        Adapters return heterogeneous shapes: LibTorrent emits plain
        :class:`dict` rows, while qBittorrent emits
        :class:`adapters.persistence.models.Torrent` (which subclasses
        ``dict`` but also gates ``__setattr__`` on ``data_keys``). Routing
        all reads through ``dict.get`` works for both and side-steps the
        Item class's attribute filtering.
        """
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    def _apply_torrent_status_to_task(self, task: 'DownloadTask', data: Any) -> None:
        """Copy live torrent fields onto a :class:`DownloadTask`.

        Missing values keep the task's last-known value (so a transient
        empty response from the torrent client doesn't blank the UI).
        ``progress`` is derived from ``downloaded / size`` when the
        adapter doesn't supply it directly (qBittorrent's ``Torrent``
        shim only exposes raw byte counts).
        """
        size = self._extract_torrent_field(data, "size")
        downloaded = self._extract_torrent_field(data, "downloaded")
        progress = self._extract_torrent_field(data, "progress")

        if progress is None and size is not None and downloaded is not None:
            try:
                size_f = float(size)
                if size_f > 0:
                    progress = float(downloaded) / size_f
            except (TypeError, ValueError):
                progress = None

        name = self._extract_torrent_field(data, "name")
        state = self._extract_torrent_field(data, "state")
        path = self._extract_torrent_field(data, "path")
        dl_speed = self._extract_torrent_field(data, "dl_speed")
        eta = self._extract_torrent_field(data, "eta")

        if name:
            task.name = str(name)
        if isinstance(size, (int, float)) and size > 0:
            task.size = int(size)
        if isinstance(downloaded, (int, float)) and downloaded >= 0:
            task.downloaded = int(downloaded)
        if isinstance(progress, (int, float)):
            task.progress = max(0.0, min(1.0, float(progress)))
        if state:
            task.state = str(state).upper()
        if path:
            task.path = str(path)
        if isinstance(dl_speed, (int, float)) and dl_speed >= 0:
            task.dl_speed = float(dl_speed)
        if isinstance(eta, (int, float)) and eta >= 0:
            task.eta = int(eta)
        self._maybe_mark_torrent_complete(
            str(task.hash_value).lower() if task.hash_value else None,
            state,
            task.progress,
        )

    def _clear_deleted_status_for_redownload(self, hash_value: Optional[str]) -> None:
        """Allow a manual re-download to proceed after a DELETED torrent."""
        if not hash_value:
            return
        db_manager = self._database_manager
        if db_manager is None:
            return
        getter = getattr(db_manager, "get_torrent_status", None)
        updater = getattr(db_manager, "update_torrent_status", None)
        if not callable(getter) or not callable(updater):
            return
        try:
            if str(getter(hash_value) or "").lower() == "deleted":
                updater(hash_value, None)
        except Exception as exc:
            self.log(
                "DOWNLOAD_MANAGER",
                f"Could not clear deleted status for {hash_value}: {exc}",
            )

    def _maybe_mark_torrent_complete(
        self,
        hash_value: Optional[str],
        state: Any,
        progress: Optional[float],
    ) -> None:
        """Persist ``complete`` when the torrent client reports a finished download."""
        if not hash_value:
            return
        if not self._is_live_complete(state, progress):
            return
        db_manager = self._database_manager
        if db_manager is None:
            return
        updater = getattr(db_manager, "update_torrent_status", None)
        getter = getattr(db_manager, "get_torrent_status", None)
        if not callable(updater) or not callable(getter):
            return
        try:
            current = str(getter(hash_value) or "").lower()
            if current in ("complete", "deleted"):
                return
            updater(hash_value, "complete")
        except Exception as exc:
            self.log(
                "DOWNLOAD_MANAGER",
                f"Could not mark torrent complete for {hash_value}: {exc}",
            )

    @classmethod
    def _is_live_complete(cls, state: Any, progress: Optional[float]) -> bool:
        token = str(state or "").strip().lower().replace(" ", "_")
        if token in cls._COMPLETED_STATES or token in cls._SEEDING_STATES:
            return True
        return isinstance(progress, (int, float)) and float(progress) >= 0.999

    def _remove_torrent_from_client(
        self, hash_value: str, *, delete_files: bool = False
    ) -> None:
        tm = self._torrent_manager
        if tm is None or not hash_value:
            return
        deleter = getattr(tm, "delete", None)
        if not callable(deleter):
            return
        try:
            deleter(hash_value, delete_files=delete_files)
        except TypeError:
            try:
                deleter(hash_value)
            except Exception as exc:
                self.log(
                    "DOWNLOAD_MANAGER",
                    f"Failed to remove torrent {hash_value}: {exc}",
                )
        except Exception as exc:
            self.log(
                "DOWNLOAD_MANAGER",
                f"Failed to remove torrent {hash_value}: {exc}",
            )

    def _lookup_live_torrent(self, hash_value: str) -> Optional[Dict[str, Any]]:
        tm = self._torrent_manager
        if tm is None or not hash_value:
            return None
        try:
            rows = tm.list(hashes=[hash_value])
        except TypeError:
            try:
                rows = [
                    row
                    for row in (tm.list() or [])
                    if str(self._extract_torrent_field(row, "hash") or "").lower()
                    == str(hash_value).lower()
                ]
            except Exception:
                return None
        except Exception:
            return None
        if not rows:
            return None
        row = rows[0]
        return {
            "state": self._extract_torrent_field(row, "state"),
            "progress": self._extract_torrent_field(row, "progress"),
            "path": self._extract_torrent_field(row, "path"),
        }

    def reconcile_deleted_torrents(
        self,
        folder_resolver: Callable[[int], Optional[str]],
    ) -> int:
        """Mark completed torrents with missing files as deleted and stop restore."""
        from application.services.torrent_file_presence import (
            paths_have_video_files,
            should_mark_deleted,
        )

        db_manager = self._database_manager
        if db_manager is None:
            return 0
        lister = getattr(db_manager, "list_torrents_for_reconcile", None)
        updater = getattr(db_manager, "update_torrent_status", None)
        if not callable(lister) or not callable(updater):
            return 0

        marked = 0
        for row in lister() or []:
            if not isinstance(row, dict):
                continue
            hash_val = str(row.get("hash") or "").strip()
            if not hash_val:
                continue
            status = row.get("status")
            if str(status or "").lower() == "deleted":
                self._remove_torrent_from_client(hash_val, delete_files=False)
                continue

            anime_id = row.get("anime_id")
            anime_folder: Optional[str] = None
            if anime_id is not None:
                try:
                    anime_folder = folder_resolver(int(anime_id))
                except Exception:
                    anime_folder = None

            save_path = row.get("save_path")
            live = self._lookup_live_torrent(hash_val)
            if live and self._is_live_complete(live.get("state"), live.get("progress")):
                updater(hash_val, "complete")
                status = "complete"
                if live.get("path") and not save_path:
                    save_path = str(live.get("path"))

            if should_mark_deleted(
                status=status,
                save_path=save_path,
                anime_folder=anime_folder,
            ):
                updater(hash_val, "deleted")
                self._remove_torrent_from_client(hash_val, delete_files=False)
                marked += 1

        if marked:
            self.log(
                "DOWNLOAD_MANAGER",
                f"Marked {marked} torrent(s) as deleted (missing files)",
            )
        return marked

    def _process_download_queue(self) -> None:
        """Drain the download queue until :meth:`close` is invoked."""
        while not self._stopping.is_set():
            try:
                task = self._download_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            executor = self._executor
            if task is None or executor is None:
                continue
            try:
                executor.submit(self._execute_download, task)
            except Exception as exc:
                self.log("DOWNLOAD_MANAGER", f"Error scheduling download: {exc}")

    def _execute_download(self, task: 'DownloadTask') -> None:
        """
        Execute a download task.

        Args:
            task: Download task to execute
        """
        with self._lock:
            self._active_downloads[task.anime_id] = task

        # The task stays in ``_active_downloads`` for as long as the user
        # should still see it in the UI. We only evict on failure / exception
        # so the panel reflects an actually-running torrent after a successful
        # hand-off; cancellation removes it via :meth:`cancel_download`.
        keep_visible = False
        task.state = "QUEUED"
        try:
            task.status_queue.put(True)  # Download started

            torrent = self._prepare_torrent(task)
            if not torrent:
                task.status_queue.put(False)
                return

            task.name = getattr(torrent, "name", None) or task.name
            # Both magnet-parsed torrents and hash-only restarts populate
            # ``torrent.hash``; cache it on the task so progress polling can
            # correlate this DownloadTask with the live torrent later.
            if not task.hash_value:
                torrent_hash = getattr(torrent, "hash", None)
                if torrent_hash:
                    task.hash_value = str(torrent_hash)
            if task.size is None:
                size_hint = getattr(torrent, "size", None)
                if isinstance(size_hint, (int, float)) and size_hint > 0:
                    task.size = int(size_hint)

            folder_path = self._get_anime_folder(task.anime_id)
            self._save_torrent(task.anime_id, torrent, save_path=folder_path)

            if task.user_id:
                self._set_user_tag(task.anime_id, task.user_id)

            success = self._start_download(task.anime_id, torrent)
            task.status_queue.put(success)

            if success:
                # Use the canonical libtorrent/qBittorrent label so the next
                # refresh tick can overwrite this with the live state without
                # the UI briefly flipping between two unrelated tokens.
                task.state = "DOWNLOADING"
                task.progress = task.progress if task.progress is not None else 0.0
                keep_visible = True
                self.log("DOWNLOAD_MANAGER", f"Successfully started download for anime {task.anime_id}")
            else:
                self.log("DOWNLOAD_MANAGER", f"Failed to start download for anime {task.anime_id}")

        except Exception as e:
            self.log("DOWNLOAD_MANAGER", f"Download execution failed for anime {task.anime_id}: {e}")
            task.status_queue.put(False)
        finally:
            if not keep_visible:
                with self._lock:
                    self._active_downloads.pop(task.anime_id, None)

    def _prepare_torrent(self, task: 'DownloadTask') -> Optional[Torrent]:
        """
        Prepare torrent for download.

        Args:
            task: Download task

        Returns:
            Torrent object or None
        """
        try:
            if task.url:
                if isinstance(task.url, Magnet):
                    task.url = task.url.get()

                if self._is_magnet_link(task.url):
                    return Torrent.from_magnet(task.url)
                if not self._is_url_allowed(task.url):
                    self.log("DOWNLOAD_MANAGER", "Blocked unsafe download URL")
                    return None
                import requests
                req = requests.get(
                    task.url,
                    allow_redirects=False,
                    timeout=15,
                    stream=True,
                )
                try:
                    if req.status_code != 200:
                        return None
                    # Cap torrent file size to defend against abusive sources.
                    max_bytes = 10 * 1024 * 1024
                    if req.headers.get("Content-Length") and int(
                        req.headers["Content-Length"]
                    ) > max_bytes:
                        self.log(
                            "DOWNLOAD_MANAGER",
                            f"Torrent content too large: {req.headers['Content-Length']}",
                        )
                        return None
                    content = req.raw.read(max_bytes + 1, decode_content=True)
                    if len(content) > max_bytes:
                        self.log("DOWNLOAD_MANAGER", "Torrent payload exceeds cap")
                        return None
                    return Torrent.from_torrent(content)
                finally:
                    req.close()

            elif task.hash_value:
                db_manager = self._database_manager
                if db_manager is not None:
                    data = db_manager.get_torrent_data(task.hash_value)
                    if data:
                        return Torrent(hash=task.hash_value, name=data[0], trackers=data[1])

        except Exception as e:
            self.log("DOWNLOAD_MANAGER", f"Error preparing torrent: {e}")

        return None

    def _save_torrent(
        self,
        anime_id: int,
        torrent: Torrent,
        *,
        save_path: Optional[str] = None,
    ) -> None:
        """Persist torrent metadata through the injected DatabaseManager."""
        db_manager = self._database_manager
        if db_manager is None:
            return
        try:
            db_manager.save_torrent(anime_id, torrent, save_path=save_path)
        except Exception as exc:
            self.log("DOWNLOAD_MANAGER", f"Error saving torrent: {exc}")

    def _set_user_tag(self, anime_id: int, user_id: int) -> None:
        """Promote library tag to ``WATCHING`` when a download is tied to a user."""
        self.log("DOWNLOAD_MANAGER", f"Watching-tag hook for anime {anime_id}, user {user_id}")
        cb = self._watching_tag_callback
        if cb is None or not user_id:
            return
        try:
            cb(anime_id, int(user_id))
        except Exception as exc:  # noqa: BLE001
            self.log(
                "DOWNLOAD_MANAGER",
                f"Watching-tag callback failed for anime {anime_id}: {exc}",
            )
    def _start_download(self, anime_id: int, torrent: Torrent) -> bool:
        """
        Start the actual download.

        Args:
            anime_id: Anime ID
            torrent: Torrent object

        Returns:
            True if download started successfully
        """
        try:
            if not self._torrent_manager or not hasattr(torrent, "to_magnet"):
                return False

            folder_path = self._get_anime_folder(anime_id)
            if not folder_path:
                return False

            torrents = self._torrent_manager.add([torrent.to_magnet()], path=folder_path)

            if torrents:
                self._move_torrents_to_folder(torrents, folder_path)

            return bool(torrents)

        except Exception as e:
            self.log("DOWNLOAD_MANAGER", f"Error starting download: {e}")
            return False

    def _get_anime_folder(self, anime_id: int) -> Optional[str]:
        """Resolve the on-disk folder where ``anime_id`` should be stored.

        Order of preference:

        1. ``<file_manager.dataPath>/Animes/<Sanitized Title> - <id>`` when
           the file manager exposes a configured ``dataPath`` and the
           database manager can resolve the anime title.
        2. ``<file_manager.dataPath>/Animes/anime_<id>`` when only the
           ``dataPath`` is known.
        3. ``./anime_<id>`` as the last-ditch fallback (matches the
           historical placeholder used by unit tests and the legacy code
           paths that pre-date file-manager wiring).

        The chosen folder is created on demand so the torrent client can
        immediately write into it. Previously this method hardcoded
        ``./anime_<id>``, which meant every download landed in the
        process CWD (typically the repo root) instead of the user's
        configured anime library, so downloaded files looked "missing"
        even though they had been written to disk.
        """
        fm = self._file_manager
        data_path: str = ""
        if fm is not None:
            settings = getattr(fm, "settings", None)
            if isinstance(settings, dict):
                data_path = str(settings.get("dataPath") or "").strip()

        if not data_path:
            return f"./anime_{anime_id}"

        animes_root = os.path.join(data_path, "Animes")
        title = self._lookup_anime_title(anime_id)
        folder_name = self._format_folder_name(title, anime_id)
        folder = os.path.join(animes_root, folder_name)

        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            self.log(
                "DOWNLOAD_MANAGER",
                f"Could not create anime folder {folder!r}: {exc}",
            )
            return f"./anime_{anime_id}"
        return folder

    @staticmethod
    def _format_folder_name(title: Optional[str], anime_id: int) -> str:
        """Sanitize ``title`` into a filesystem-safe folder name.

        Mirrors the historical ``Getters.getFolderFormat`` behavior: keep
        alphanumerics + spaces, treat hyphens as spaces, then append the
        anime id so two entries with similar titles never collide.
        """
        if not title:
            return f"anime_{anime_id}"
        cleaned_chars: list[str] = []
        for ch in title:
            if ch.isalnum() or ch == " ":
                cleaned_chars.append(ch)
            elif ch == "-":
                cleaned_chars.append(" ")
        cleaned = "".join(cleaned_chars).strip()
        if not cleaned:
            return f"anime_{anime_id}"
        cleaned = " ".join(cleaned.split())
        return f"{cleaned} - {anime_id}"

    def _lookup_anime_title(self, anime_id: int) -> Optional[str]:
        """Best-effort lookup of an anime's title via the DatabaseManager.

        Returns ``None`` (and never raises) when the DB manager isn't
        wired in, the row doesn't exist, or the query fails -- the
        caller falls back to a generic folder name.
        """
        dm = self._database_manager
        if dm is None:
            return None
        try:
            db = getattr(dm, "get_database", lambda: None)()
        except Exception:
            db = None
        if db is None:
            return None
        try:
            row = db.get(anime_id, table="anime")
        except Exception as exc:
            self.log(
                "DOWNLOAD_MANAGER",
                f"Anime title lookup failed for {anime_id}: {exc}",
            )
            return None
        if not row:
            return None
        if isinstance(row, dict):
            title = row.get("title")
        else:
            title = getattr(row, "title", None)
            if title is None and hasattr(row, "__getitem__"):
                try:
                    title = row["title"]
                except (KeyError, IndexError, TypeError):
                    title = None
        if title in (None, ""):
            return None
        return str(title)

    def _move_torrents_to_folder(self, torrents, folder_path: str) -> None:
        """
        Move torrents to the specified folder.

        Args:
            torrents: Torrent objects
            folder_path: Target folder path
        """
        try:
            if hasattr(torrents, "__iter__"):
                torrent_hashes = []
                for t in torrents:
                    h = None
                    if isinstance(t, dict):
                        h = t.get("hash")
                    elif hasattr(t, "hash"):
                        h = getattr(t, "hash", None)
                    if h:
                        torrent_hashes.append(h)

                if torrent_hashes and self._torrent_manager:
                    self._torrent_manager.move(path=folder_path, hashes=torrent_hashes)
                db_manager = self._database_manager
                if db_manager is not None:
                    for h in torrent_hashes:
                        try:
                            db_manager.update_torrent_save_path(str(h), folder_path)
                        except Exception as exc:
                            self.log(
                                "DOWNLOAD_MANAGER",
                                f"Could not persist save_path for {h}: {exc}",
                            )
        except Exception as e:
            self.log("DOWNLOAD_MANAGER", f"Error moving torrents: {e}")

    def _is_magnet_link(self, url: str) -> bool:
        """
        Check if URL is a magnet link.

        Args:
            url: URL to check

        Returns:
            True if magnet link
        """
        return url.startswith("magnet:?")

    def _is_url_allowed(self, url: str) -> bool:
        """Allow only safe, expected outbound URLs (delegates to shared.security)."""
        safe, reason = validate_url(url)
        if not safe:
            self.log("DOWNLOAD_MANAGER", f"URL rejected: {reason}")
        return safe


class DownloadTask:
    """
    Represents a download task.
    """

    def __init__(self, anime_id: int, url: Optional[str] = None,
                 hash_value: Optional[str] = None, user_id: Optional[int] = None):
        self.anime_id = anime_id
        self.url = url
        self.hash_value = hash_value
        self.user_id = user_id
        self.status_queue = queue.Queue()
        self.cancelled = False
        self.start_time = time.time()
        # UI-facing fields populated by DownloadManager as the task
        # progresses. ``progress`` is a 0..1 float; ``size`` / ``downloaded``
        # are bytes; ``dl_speed`` is bytes/sec; ``eta`` is seconds remaining.
        # All start as ``None`` so the UI knows the value isn't available yet
        # (vs. a misleading 0 that would render an empty progress bar).
        self.state: Optional[str] = None
        self.name: Optional[str] = None
        self.progress: Optional[float] = None
        self.size: Optional[int] = None
        self.downloaded: Optional[int] = None
        self.dl_speed: Optional[float] = None
        self.eta: Optional[int] = None
        self.path: Optional[str] = None

    def cancel(self) -> None:
        """Cancel the download task."""
        self.cancelled = True
        self.state = "CANCELLED"

    def get_status(self) -> Dict[str, Any]:
        """
        Get task status.

        Returns:
            Status dictionary
        """
        return {
            "anime_id": self.anime_id,
            "url": self.url,
            "hash": self.hash_value,
            "user_id": self.user_id,
            "cancelled": self.cancelled,
            "elapsed_time": time.time() - self.start_time,
            "state": self.state,
            "name": self.name,
            "progress": self.progress,
            "size": self.size,
            "downloaded": self.downloaded,
            "dl_speed": self.dl_speed,
            "eta": self.eta,
            "path": self.path,
        }
