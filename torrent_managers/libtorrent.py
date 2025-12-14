import os
import tempfile
import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Provide symbols for type checkers/static analysis when libtorrent is present
    import libtorrent as lt  # type: ignore

try:
    import libtorrent as lt

    LIBTORRENT_AVAILABLE = True
except ImportError:
    # Avoid printing during import-time; use module-level flag instead.
    lt = None
    LIBTORRENT_AVAILABLE = False

# Let static analyzers treat `lt` as a dynamic object with any attributes when installed.
lt: Any

try:
    from ..dialog_components import LoginDialog
    from .base import BaseTorrentManager, TorrentException, TorrentListFilter
except ImportError:
    from torrent_managers.base import (
        BaseTorrentManager,
        TorrentListFilter,
        TorrentException,
    )
    from dialog_components import LoginDialog

import json


class LibTorrent(BaseTorrentManager):
    name = "LibTorrent"

    def __init__(self, *args, **kwargs):
        if not LIBTORRENT_AVAILABLE:
            raise TorrentException(
                "LibTorrent is not available. Please install a compatible python-libtorrent build for your Python version and platform."
            )
        self.session = None
        self.handles = {}  # Maps hash to torrent_handle
        self._running = False
        self._thread = None
        # Provide a sensible default download_path before calling BaseTorrentManager.__init__
        # BaseTorrentManager.__init__ may call login_dialog() when update=True, and
        # login_dialog expects `self.download_path` to exist.
        try:
            self.download_path = os.path.join(
                tempfile.gettempdir(), "libtorrent_downloads"
            )
        except Exception:
            # Fallback to empty string if tempfile or os behave unexpectedly
            self.download_path = ""
        super().__init__(*args, **kwargs)

    def initialize(self):
        if lt is None:
            raise ImportError(
                "libtorrent library is not available. Please install python-libtorrent."
            )
        # Prefer explicit manager setting first, then a dataPath provided by the app
        # `Getters.getTorrentManager()` should inject the appropriate value into
        # self.settings (either 'download_path' or 'dataPath'). If neither is
        # present, fall back to a temp dir.
        default_download = os.path.join(tempfile.gettempdir(), "libtorrent_downloads")

        # Accept both 'download_path' (explicit) or 'dataPath' (app file manager root)
        download = (
            self.settings.get("download_path")
            if isinstance(self.settings, dict)
            else None
        )
        data_path = (
            self.settings.get("dataPath") if isinstance(self.settings, dict) else None
        )

        if download:
            self.download_path = download
        elif data_path:
            # Use Downloads subfolder inside the application's dataPath
            try:
                self.download_path = os.path.join(data_path, "Downloads")
            except Exception:
                self.download_path = default_download
        else:
            self.download_path = default_download

        self.listen_port = (
            self.settings.get("listen_port", 6881)
            if isinstance(self.settings, dict)
            else 6881
        )

        # Ensure download directory exists
        try:
            os.makedirs(self.download_path, exist_ok=True)
        except Exception:
            # If we couldn't create the dir, fall back to temp
            self.download_path = default_download

        if not self.download_path:
            return self.login_dialog()

        self.connect()

    def connect(self, thread=True):
        if thread is True:
            # Use a different thread to avoid blocking
            threading.Thread(target=self.connect, args=(False,)).start()
            return

        try:
            # Create libtorrent session
            self.session = lt.session()

            # Configure session settings
            settings = {
                "listen_interfaces": f"0.0.0.0:{self.listen_port}",
                "enable_dht": True,
                "enable_lsd": True,  # Local Service Discovery
                "enable_upnp": True,
                "enable_natpmp": True,
            }

            self.session.apply_settings(settings)

            # Start DHT
            self.session.add_dht_router("router.bittorrent.com", 6881)
            self.session.add_dht_router("router.utorrent.com", 6881)
            self.session.add_dht_router("dht.transmissionbt.com", 6881)

            self._running = True
            self._thread = threading.Thread(target=self._session_thread, daemon=True)
            self._thread.start()

        except Exception as e:
            print(f"Couldn't connect to LibTorrent: {str(e)}")  # TODO - use logger
            raise TorrentException(f"Failed to initialize LibTorrent session: {str(e)}")

    def _session_thread(self):
        """Background thread to handle session alerts and updates"""
        while self._running and self.session:
            try:
                alerts = self.session.pop_alerts()
                for alert in alerts:
                    if isinstance(alert, lt.torrent_added_alert):
                        h = alert.handle
                        info_hash = str(h.info_hash())
                        self.handles[info_hash] = h
                    elif isinstance(alert, lt.torrent_removed_alert):
                        info_hash = str(alert.info_hash)
                        if info_hash in self.handles:
                            del self.handles[info_hash]
                    elif isinstance(alert, lt.torrent_error_alert):
                        print(f"Torrent error: {alert.message}")  # TODO - use logger

                time.sleep(0.1)  # Small delay to prevent busy waiting
            except Exception as e:
                print(f"Error in session thread: {str(e)}")  # TODO - use logger
                break

    def login_dialog(self, failed=False):
        fields = {
            "download_path": self.settings.get("download_path", self.download_path)
        }
        fields_name = {"download_path": "download_path"}

        validator = lambda r: (
            1 if r.get("download_path", "") != "" else "No download path provided"
        )

        title = "Configure LibTorrent"
        if failed:
            title = "An error occurred, please try again\n" + title

        dialog = LoginDialog(fields=fields, title=title, validator=validator)
        data = dialog.results

        if data is None:
            # Dialog was cancelled or closed; raise to indicate configuration aborted
            raise TorrentException("LibTorrent configuration cancelled by user")

        settings = {}
        for field, name in fields_name.items():
            settings[field] = data.get(name, "")

        self.settings = settings
        try:
            from ..general_utils import persist_manager_settings
        except Exception:
            from general_utils import persist_manager_settings

        try:
            persist_manager_settings("torrent_managers", self.name, self.settings)
        except Exception:
            pass

        self.initialize()

    @staticmethod
    def wait_connection(func):
        def wrapper(self, *args, **kwargs):
            if self.session is None or not self._running:
                raise TorrentException("LibTorrent session not available")

            return BaseTorrentManager.error_wrapper(func)(self, *args, **kwargs)

        return wrapper

    @wait_connection
    def add(self, hashes, path=None, **kwargs):
        """Add torrents from magnet links or torrent files.

        Backwards-compatible: accepts a single string or iterable of magnets/files.
        Also accepts an optional `path` argument (positional or kw) to override
        the manager's configured download path.
        """
        # Accept both a single string or an iterable of strings
        if isinstance(hashes, str):
            items = [hashes]
        else:
            items = list(hashes or [])

        # Determine save path: explicit argument > manager setting > default
        save_path = (
            path or self.settings.get("download_path", None)
            if isinstance(self.settings, dict)
            else None
        )
        if not save_path:
            save_path = self.download_path

        for item in items:
            try:
                if isinstance(item, str) and item.startswith("magnet:"):
                    if self.session is None:
                        raise TorrentException("LibTorrent session is not initialized")
                    params = {"url": item, "save_path": save_path}
                    self.session.add_torrent(params)
                else:
                    if isinstance(item, str) and os.path.exists(item):
                        info = lt.torrent_info(item)
                        params = {"ti": info, "save_path": save_path}
                        if self.session is None:
                            raise TorrentException(
                                "LibTorrent session is not initialized"
                            )
                        self.session.add_torrent(params)
                    else:
                        raise TorrentException(
                            f"Torrent file not found or invalid magnet: {item}"
                        )
            except Exception as e:
                raise TorrentException(f"Failed to add torrent {item}: {str(e)}")

    @wait_connection
    def list(self, filter=None, hashes=None):
        """List torrents with optional filtering"""
        torrents = []

        for info_hash, handle in self.handles.items():
            if hashes is not None and len(hashes) > 0 and info_hash not in hashes:
                continue

            try:
                status = handle.status()

                # Apply filter
                if filter == TorrentListFilter.COMPLETED and not status.is_seeding:
                    continue
                elif filter == TorrentListFilter.DOWNLOADING and status.is_seeding:
                    continue
                # TorrentListFilter.ALL includes everything

                torrent_data = self._convert_handle_to_torrent_data(handle, status)
                torrents.append(torrent_data)

            except Exception as e:
                print(
                    f"Error getting status for torrent {info_hash}: {str(e)}"
                )  # TODO - use logger
                continue

        return torrents

    @wait_connection
    def move(self, hashes, paths):
        """Move torrents to a new location.

        Matches BaseTorrentManager.move(hashes, paths) signature. `paths` may be a single
        path string or a mapping; here we treat `paths` as the destination path.
        """
        # Allow either hashes as string or iterable
        if isinstance(hashes, str):
            hashes = [hashes]

        dest = paths if isinstance(paths, str) else (paths or "")

        for hash_str in hashes:
            if hash_str in self.handles:
                try:
                    handle = self.handles[hash_str]
                    handle.move_storage(dest)
                except Exception as e:
                    raise TorrentException(
                        f"Failed to move torrent {hash_str}: {str(e)}"
                    )

    @wait_connection
    def delete(self, hashes):
        """Delete torrents and their files"""
        if isinstance(hashes, str):
            hashes = [hashes]

        for hash_str in hashes:
            if hash_str in self.handles:
                try:
                    handle = self.handles[hash_str]
                    if self.session is None or lt is None:
                        raise TorrentException(
                            "LibTorrent session or library not available"
                        )
                    self.session.remove_torrent(handle, lt.options_t.delete_files)
                except Exception as e:
                    raise TorrentException(
                        f"Failed to delete torrent {hash_str}: {str(e)}"
                    )

    def _convert_handle_to_torrent_data(self, handle, status):
        """Convert libtorrent handle and status to the application's torrent data format"""
        try:
            info_hash = str(handle.info_hash())

            # Get torrent info if available
            if handle.has_metadata():
                torrent_info = handle.get_torrent_info()
                name = torrent_info.name()
                total_size = torrent_info.total_size()
            else:
                name = status.name or info_hash
                total_size = status.total_wanted

            # Get trackers
            trackers = []
            for tracker in handle.trackers():
                trackers.append(tracker["url"])

            # Calculate progress
            progress = status.progress
            downloaded = (
                int(total_size * progress) if total_size > 0 else status.total_download
            )

            torrent_data = {
                "hash": info_hash,
                "name": name,
                "trackers": trackers,
                "seeds": status.num_seeds,
                "leech": status.num_peers - status.num_seeds,
                "size": total_size,
                "path": status.save_path,
                "downloaded": downloaded,
                "link": None,  # We don't store the original magnet/file link
                "progress": progress,
                "state": self._get_torrent_state(status),
            }

            return torrent_data

        except Exception as e:
            print(f"Error converting torrent data: {str(e)}")  # TODO - use logger
            return None

    def _get_torrent_state(self, status):
        """Get human-readable torrent state"""
        state_map = {
            lt.torrent_status.queued_for_checking: "queued",
            lt.torrent_status.checking_files: "checking",
            lt.torrent_status.downloading_metadata: "downloading_metadata",
            lt.torrent_status.downloading: "downloading",
            lt.torrent_status.finished: "finished",
            lt.torrent_status.seeding: "seeding",
            lt.torrent_status.allocating: "allocating",
            lt.torrent_status.checking_resume_data: "checking_resume",
        }
        return state_map.get(status.state, "unknown")

    def close(self):
        """Clean shutdown of the LibTorrent session"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

        if self.session:
            try:
                self.session.pause()
                # Save resume data for all torrents
                for handle in self.handles.values():
                    if handle.is_valid():
                        handle.save_resume_data()

                # Wait a bit for resume data to be saved
                time.sleep(1)

            except Exception as e:
                print(f"Error during session cleanup: {str(e)}")  # TODO - use logger
            finally:
                self.session = None
                self.handles.clear()

    def __del__(self):
        """Destructor to ensure clean shutdown"""
        self.close()


if __name__ == "__main__":
    # Test the LibTorrent manager
    settings = {
        "download_path": os.path.join(tempfile.gettempdir(), "test_libtorrent"),
        "listen_port": 6881,
    }

    manager = LibTorrent(settings)

    # Test with Big Buck Bunny magnet (legal, open-source movie)
    test_magnet = "magnet:?xt=urn:btih:dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c&dn=Big+Buck+Bunny&tr=udp%3A%2F%2Fexplodie.org%3A6969&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.empire-js.us%3A1337&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337"

    try:
        print("Adding test magnet...")
        manager.add(test_magnet)

        print("Waiting for metadata...")
        time.sleep(5)

        print("Listing torrents...")
        torrents = manager.list()
        for torrent in torrents:
            print(
                f"Name: {torrent['name']}, Size: {torrent['size']}, State: {torrent.get('state', 'unknown')}"
            )

    except Exception as e:
        print(f"Test failed: {str(e)}")
    finally:
        manager.close()
