"""
DownloadManager component for handling file and torrent downloads.
Implements progress tracking, error handling, and download coordination.
"""

import threading
import queue
import time
from typing import Optional, Any, Dict, List, Callable
from concurrent.futures import ThreadPoolExecutor

from ..core import BaseComponent
from classes import Torrent, Magnet


class DownloadManager(BaseComponent):
    """
    Manages file and torrent downloads with progress tracking and error handling.
    Coordinates between torrent managers and file managers.
    """

    def __init__(self):
        super().__init__("DownloadManager")
        self._torrent_manager = None
        self._file_manager = None
        self._active_downloads: Dict[int, DownloadTask] = {}
        self._download_queue = queue.Queue()
        self._executor = None
        self._max_concurrent_downloads = 3
        self._lock = threading.RLock()

    def _initialize(self) -> None:
        """Initialize the download manager."""
        self.log("DOWNLOAD_MANAGER", "Initializing Download Manager")
        self._executor = ThreadPoolExecutor(max_workers=self._max_concurrent_downloads)

        # Subscribe to download-related events
        self.subscribe_event("download.start", self._handle_start_download)
        self.subscribe_event("download.cancel", self._handle_cancel_download)

    def _start(self) -> None:
        """Start the download manager."""
        self.log("DOWNLOAD_MANAGER", "Starting Download Manager")

        # Start download processing thread
        threading.Thread(
            target=self._process_download_queue,
            daemon=True,
            name="DownloadProcessor"
        ).start()

    def _stop(self) -> None:
        """Stop the download manager."""
        with self._lock:
            # Cancel all active downloads
            for task in self._active_downloads.values():
                task.cancel()

            self._active_downloads.clear()

        if self._executor:
            self._executor.shutdown(wait=True)

        self.log("DOWNLOAD_MANAGER", "Download Manager stopped")

    def set_torrent_manager(self, torrent_manager) -> None:
        """
        Set the torrent manager instance.

        Args:
            torrent_manager: Torrent manager instance
        """
        self._torrent_manager = torrent_manager

    def set_file_manager(self, file_manager) -> None:
        """
        Set the file manager instance.

        Args:
            file_manager: File manager instance
        """
        self._file_manager = file_manager

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

        # Create download task
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
        # This would need access to database to get existing torrents
        # For now, return 0 as placeholder
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
            task = self._active_downloads.get(anime_id)
            if task:
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
        with self._lock:
            return [task.get_status() for task in self._active_downloads.values()]

    def _process_download_queue(self) -> None:
        """Process the download queue."""
        while not self.is_stopped:
            try:
                task = self._download_queue.get(timeout=1.0)
                if task:
                    self._executor.submit(self._execute_download, task)
            except queue.Empty:
                continue
            except Exception as e:
                self.log("DOWNLOAD_MANAGER", f"Error processing download queue: {e}")

    def _execute_download(self, task: 'DownloadTask') -> None:
        """
        Execute a download task.

        Args:
            task: Download task to execute
        """
        with self._lock:
            self._active_downloads[task.anime_id] = task

        try:
            task.status_queue.put(True)  # Download started

            torrent = self._prepare_torrent(task)
            if not torrent:
                task.status_queue.put(False)
                return

            # Save torrent to database
            self._save_torrent(task.anime_id, torrent)

            # Set user tag if provided
            if task.user_id:
                self._set_user_tag(task.anime_id, task.user_id)

            # Start download
            success = self._start_download(task.anime_id, torrent)
            task.status_queue.put(success)

            if success:
                self.log("DOWNLOAD_MANAGER", f"Successfully started download for anime {task.anime_id}")
            else:
                self.log("DOWNLOAD_MANAGER", f"Failed to start download for anime {task.anime_id}")

        except Exception as e:
            self.log("DOWNLOAD_MANAGER", f"Download execution failed for anime {task.anime_id}: {e}")
            task.status_queue.put(False)
        finally:
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
                else:
                    # Download torrent file
                    import requests
                    if requests:
                        req = requests.get(task.url, allow_redirects=True)
                        if req.status_code == 200:
                            return Torrent.from_torrent(req.content)

            elif task.hash_value:
                # Get torrent data from database
                db_manager = self.get_dependency("DatabaseManager")
                if db_manager:
                    data = db_manager.get_torrent_data(task.hash_value)
                    if data:
                        return Torrent(hash=task.hash_value, name=data[0], trackers=data[1])

        except Exception as e:
            self.log("DOWNLOAD_MANAGER", f"Error preparing torrent: {e}")

        return None

    def _save_torrent(self, anime_id: int, torrent: Torrent) -> None:
        """
        Save torrent to database.

        Args:
            anime_id: Anime ID
            torrent: Torrent object
        """
        try:
            db_manager = self.get_dependency("DatabaseManager")
            if db_manager:
                db_manager.save_torrent(anime_id, torrent)
        except Exception as e:
            self.log("DOWNLOAD_MANAGER", f"Error saving torrent: {e}")

    def _set_user_tag(self, anime_id: int, user_id: int) -> None:
        """
        Set user tag to WATCHING.

        Args:
            anime_id: Anime ID
            user_id: User ID
        """
        # This would need database access
        # For now, just log
        self.log("DOWNLOAD_MANAGER", f"Setting tag for anime {anime_id}, user {user_id}")

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

            # Get anime folder
            folder_path = self._get_anime_folder(anime_id)
            if not folder_path:
                return False

            # Start download
            torrents = self._torrent_manager.add([torrent.to_magnet()], path=folder_path)

            if torrents:
                # Move torrents to anime folder if needed
                self._move_torrents_to_folder(torrents, folder_path)

            return bool(torrents)

        except Exception as e:
            self.log("DOWNLOAD_MANAGER", f"Error starting download: {e}")
            return False

    def _get_anime_folder(self, anime_id: int) -> Optional[str]:
        """
        Get the folder path for an anime.

        Args:
            anime_id: Anime ID

        Returns:
            Folder path or None
        """
        # This would use the file manager
        # For now, return a placeholder
        return f"./anime_{anime_id}"

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
                    if hasattr(t, "hash"):
                        torrent_hashes.append(t.hash)

                if torrent_hashes and self._torrent_manager:
                    self._torrent_manager.move(path=folder_path, hashes=torrent_hashes)
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

    def _handle_start_download(self, event_type: str, data: Any) -> None:
        """Handle download start event."""
        if isinstance(data, dict):
            self.download_file(**data)

    def _handle_cancel_download(self, event_type: str, data: Any) -> None:
        """Handle download cancel event."""
        if isinstance(data, int):
            self.cancel_download(data)


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

    def cancel(self) -> None:
        """Cancel the download task."""
        self.cancelled = True

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
        }