import glob
import os
import stat
import tempfile
import threading
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

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
    from .base import BaseTorrentManager, TorrentException, TorrentListFilter
except ImportError:  # pragma: no cover - legacy relative import
    from base import BaseTorrentManager, TorrentException, TorrentListFilter  # type: ignore

try:
    from clients.tk.dialogs import LoginDialog
except ImportError:  # pragma: no cover - headless / Docker HTTP mode
    class LoginDialog:  # type: ignore[no-redef]
        """Stub when Tk is unavailable."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("LoginDialog requires the Tk desktop client")

_RESUME_DIR_NAME = ".libtorrent_resume"
_RESUME_SUFFIX = ".resume"
# Fastresume produced by write_resume_data_buf is typically multi-kB; older
# builds mistakenly stored a tiny bencoded dict (~50 bytes) which cannot reload.
_MIN_RESUME_FILE_BYTES = 200
_PERIODIC_SAVE_INTERVAL_S = 300.0
_SHUTDOWN_SAVE_TIMEOUT_S = 5.0
_SESSION_READY_TIMEOUT_S = 30.0
# Wait for DownloadAdapter to wire DB callbacks before restore (avoids race).
_RESTORE_WIRE_TIMEOUT_S = 5.0
# Cap concurrent piece checks to reduce HDD thrash at boot.
_DEFAULT_ACTIVE_CHECKING = 1
# Global peer connections limit (libtorrent session connections_limit).
_DEFAULT_MAX_CONNECTIONS = 200
_MIN_MAX_CONNECTIONS = 1
_MAX_MAX_CONNECTIONS = 65535


class LibTorrent(BaseTorrentManager):
    name = "LibTorrent"

    def __init__(self, *args, **kwargs):
        if not LIBTORRENT_AVAILABLE:
            raise TorrentException(
                "LibTorrent is not available. Please install a compatible python-libtorrent build for your Python version and platform."
            )
        self.session = None
        self.handles: Dict[str, Any] = {}
        self._running = False
        self._thread = None
        self._session_ready = threading.Event()
        self._shutting_down = False
        self._pending_resume_saves = 0
        self._resume_lock = threading.Lock()
        self._resume_file_locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._last_periodic_save = 0.0
        self._last_handle_save: Dict[str, float] = {}
        self._restore_callback: Optional[Callable[[], List[Dict[str, Any]]]] = None
        self._torrent_status_callback: Optional[Callable[[str], Optional[str]]] = None
        self._restored = False
        self._restore_lock = threading.Lock()
        try:
            self.download_path = os.path.join(
                tempfile.gettempdir(), "libtorrent_downloads"
            )
        except Exception:
            self.download_path = ""
        super().__init__(*args, **kwargs)

    def set_restore_callback(
        self, callback: Optional[Callable[[], List[Dict[str, Any]]]]
    ) -> None:
        """Optional DB rows for magnet+save_path fallback after fast-resume load."""
        self._restore_callback = callback
        # If connect already restored without the callback, pick up missing magnets.
        if self._restored and self.session is not None:
            self._restore_from_database_fallback()

    def set_torrent_status_callback(
        self, callback: Optional[Callable[[str], Optional[str]]]
    ) -> None:
        """Optional lookup of persisted torrent status by hash."""
        self._torrent_status_callback = callback

    def _torrent_status(self, info_hash: str) -> Optional[str]:
        callback = self._torrent_status_callback
        if callback is None:
            return None
        try:
            return callback(info_hash)
        except Exception:
            return None

    def ensure_restored(self) -> None:
        """Block until the background connect thread finished session restore."""
        if not self._session_ready.wait(timeout=_SESSION_READY_TIMEOUT_S):
            raise TorrentException("LibTorrent session restore timed out")

    def purge_deleted_torrents(self) -> int:
        """Drop resume files and live handles for torrents marked deleted in the DB."""
        purged = 0
        resume_dir = self._resume_dir()
        for path in sorted(glob.glob(os.path.join(resume_dir, f"*{_RESUME_SUFFIX}"))):
            try:
                basename = os.path.basename(path)
                if not basename.endswith(_RESUME_SUFFIX):
                    continue
                info_hash = self._normalise_hash(
                    basename[: -len(_RESUME_SUFFIX)]
                )
                if self._torrent_status(info_hash) != "deleted":
                    continue
                try:
                    os.remove(path)
                except OSError:
                    pass
                purged += 1
            except Exception:
                continue

        if self.session is not None and lt is not None:
            for key in list(self.handles.keys()):
                if self._torrent_status(key) != "deleted":
                    continue
                try:
                    self.delete(key, delete_files=False)
                    purged += 1
                except Exception:
                    continue
        return purged

    @staticmethod
    def _normalise_hash(info_hash: Any) -> str:
        if isinstance(info_hash, (bytes, bytearray)):
            return bytes(info_hash).hex()
        return str(info_hash).strip().lower()

    def _resolve_data_path(self) -> str:
        if isinstance(self.settings, dict):
            dp = self.settings.get("dataPath")
            if dp:
                return str(dp).strip()
        if self.download_path:
            base = os.path.dirname(os.path.normpath(self.download_path))
            if base and os.path.basename(self.download_path).lower() == "downloads":
                return base
            return self.download_path
        return tempfile.gettempdir()

    def _resume_dir(self) -> str:
        path = os.path.join(self._resolve_data_path(), _RESUME_DIR_NAME)
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
        return path

    def _resume_file_path(self, info_hash: str) -> str:
        return os.path.join(
            self._resume_dir(), f"{self._normalise_hash(info_hash)}{_RESUME_SUFFIX}"
        )

    @staticmethod
    def _is_retryable_write_error(exc: BaseException) -> bool:
        if isinstance(exc, PermissionError):
            return True
        if isinstance(exc, OSError):
            winerror = getattr(exc, "winerror", None)
            if winerror in (5, 32):
                return True
            if exc.errno in (13,):
                return True
        return False

    @staticmethod
    def _clear_writable(path: str) -> None:
        try:
            if os.path.exists(path):
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass

    def _commit_atomic_write(self, tmp: str, path: str) -> None:
        self._clear_writable(path)
        last_exc: Optional[BaseException] = None
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                return
            except OSError as exc:
                last_exc = exc
                if not self._is_retryable_write_error(exc):
                    break
                if attempt < 4:
                    time.sleep(0.05 * (attempt + 1))
        try:
            self._clear_writable(path)
            if os.path.exists(path):
                os.remove(path)
            os.rename(tmp, path)
            return
        except OSError as exc:
            last_exc = exc
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        if last_exc is not None:
            raise last_exc

    def _atomic_write_bytes(self, path: str, data: bytes) -> None:
        dirpath = os.path.dirname(path)
        basename = os.path.basename(path)
        os.makedirs(dirpath, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dirpath, prefix=f"{basename}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            self._commit_atomic_write(tmp, path)
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            raise

    def initialize(self):
        if lt is None:
            raise ImportError(
                "libtorrent library is not available. Please install python-libtorrent."
            )
        default_download = os.path.join(tempfile.gettempdir(), "libtorrent_downloads")

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
            try:
                self.download_path = os.path.join(data_path, "Downloads")
            except Exception:
                self.download_path = default_download
        else:
            self.download_path = default_download

        # Keep dataPath on the manager settings so resume files always
        # land under the library root even after settings are persisted.
        if isinstance(self.settings, dict) and data_path:
            self.settings["dataPath"] = data_path

        self.listen_port = (
            self.settings.get("listen_port", 6881)
            if isinstance(self.settings, dict)
            else 6881
        )
        self.max_connections = self._resolve_max_connections()

        try:
            os.makedirs(self.download_path, exist_ok=True)
        except Exception:
            self.download_path = default_download

        if not self.download_path:
            return self.login_dialog()

        self._session_ready.clear()
        self.connect()

    def _resolve_max_connections(self) -> int:
        raw = _DEFAULT_MAX_CONNECTIONS
        if isinstance(self.settings, dict):
            raw = self.settings.get("max_connections", _DEFAULT_MAX_CONNECTIONS)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return _DEFAULT_MAX_CONNECTIONS
        return max(_MIN_MAX_CONNECTIONS, min(_MAX_MAX_CONNECTIONS, value))

    def connect(self, thread=True):
        if thread is True:
            threading.Thread(target=self.connect, args=(False,), daemon=True).start()
            return

        try:
            self.session = lt.session()
            active_checking = _DEFAULT_ACTIVE_CHECKING
            if isinstance(self.settings, dict):
                raw = self.settings.get("active_checking", _DEFAULT_ACTIVE_CHECKING)
                try:
                    active_checking = max(1, int(raw))
                except (TypeError, ValueError):
                    active_checking = _DEFAULT_ACTIVE_CHECKING
            max_connections = getattr(
                self, "max_connections", None
            )
            if max_connections is None:
                max_connections = self._resolve_max_connections()
                self.max_connections = max_connections
            # DHT/UPnP stay off until torrents are restored (less boot contention).
            settings = {
                "listen_interfaces": f"0.0.0.0:{self.listen_port}",
                "enable_dht": False,
                "enable_lsd": False,
                "enable_upnp": False,
                "enable_natpmp": False,
                "active_checking": active_checking,
                "connections_limit": max_connections,
            }
            self.session.apply_settings(settings)
            try:
                self.session.apply_settings(
                    {
                        "alert_mask": lt.alert.category_t.all_categories,
                    }
                )
            except Exception:
                pass

            self._running = True
            self._thread = threading.Thread(target=self._session_thread, daemon=True)
            self._thread.start()

            self._wait_for_restore_callbacks()
            self._run_session_restore()
            self._session_ready.set()
        except Exception as e:
            self._session_ready.set()
            print(f"Couldn't connect to LibTorrent: {str(e)}")  # TODO - use logger
            raise TorrentException(f"Failed to initialize LibTorrent session: {str(e)}")

    def _wait_for_restore_callbacks(self) -> None:
        """Block briefly so DownloadAdapter can wire DB restore/status callbacks."""
        deadline = time.monotonic() + _RESTORE_WIRE_TIMEOUT_S
        while time.monotonic() < deadline:
            if (
                self._restore_callback is not None
                and self._torrent_status_callback is not None
            ):
                return
            time.sleep(0.05)

    def _run_session_restore(self) -> None:
        """Load resume files + DB fallback once, then enable discovery."""
        with self._restore_lock:
            if self._restored:
                return
            self._restore_from_resume_files()
            self._restore_from_database_fallback()
            self._enable_network_services()
            self._restored = True

    def _enable_network_services(self) -> None:
        """Turn on DHT/LSD/UPnP after torrents are in the session."""
        if self.session is None:
            return
        try:
            self.session.apply_settings(
                {
                    "enable_dht": True,
                    "enable_lsd": True,
                    "enable_upnp": True,
                    "enable_natpmp": True,
                }
            )
        except Exception:
            pass
        try:
            self.session.add_dht_router("router.bittorrent.com", 6881)
            self.session.add_dht_router("router.utorrent.com", 6881)
            self.session.add_dht_router("dht.transmissionbt.com", 6881)
        except Exception:
            pass

    def _seed_mode_flag(self) -> Optional[Any]:
        if lt is None:
            return None
        flags = getattr(lt, "torrent_flags", None)
        if flags is None:
            return None
        return getattr(flags, "seed_mode", None)

    def _apply_seed_mode(self, params: Any) -> Any:
        """OR seed_mode into add_torrent params (dict or add_torrent_params)."""
        seed = self._seed_mode_flag()
        if seed is None or params is None:
            return params
        if isinstance(params, dict):
            existing = params.get("flags")
            if existing is None and lt is not None:
                default = getattr(
                    getattr(lt, "torrent_flags", None), "default_flags", None
                )
                if default is not None:
                    params["flags"] = default | seed
                else:
                    params["flags"] = seed
            else:
                try:
                    params["flags"] = existing | seed
                except Exception:
                    params["flags"] = seed
            return params
        try:
            params.flags |= seed
        except Exception:
            pass
        return params

    def _apply_seed_mode_if_complete(self, params: Any, info_hash: str) -> Any:
        if self._torrent_status(info_hash) != "complete":
            return params
        return self._apply_seed_mode(params)

    def _restore_from_resume_files(self) -> None:
        if self.session is None or lt is None:
            return
        resume_dir = self._resume_dir()
        for path in sorted(glob.glob(os.path.join(resume_dir, f"*{_RESUME_SUFFIX}"))):
            try:
                basename = os.path.basename(path)
                if not basename.endswith(_RESUME_SUFFIX):
                    continue
                info_hash = self._normalise_hash(
                    basename[: -len(_RESUME_SUFFIX)]
                )
                if self._torrent_status(info_hash) == "deleted":
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    continue
                with open(path, "rb") as fh:
                    data = fh.read()
                if not data or len(data) < _MIN_RESUME_FILE_BYTES:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    continue
                params = lt.read_resume_data(data)
                params = self._apply_seed_mode_if_complete(params, info_hash)
                handle = self.session.add_torrent(params)
                info_hash = self._normalise_hash(handle.info_hash())
                if info_hash in self.handles:
                    continue
                self.handles[info_hash] = handle
            except Exception as exc:
                print(f"Failed to restore torrent from {path}: {exc}")  # TODO - logger

    def _restore_from_database_fallback(self) -> None:
        callback = self._restore_callback
        if callback is None or self.session is None:
            return
        try:
            rows = callback() or []
        except Exception as exc:
            print(f"Torrent DB restore callback failed: {exc}")  # TODO - logger
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw_hash = row.get("hash")
            if not raw_hash:
                continue
            info_hash = self._normalise_hash(raw_hash)
            if info_hash in self.handles:
                continue
            if self._torrent_status(info_hash) == "deleted":
                continue
            save_path = row.get("save_path")
            if not save_path or not os.path.isdir(str(save_path)):
                continue
            magnet = self._magnet_from_restore_row(row)
            if not magnet:
                continue
            try:
                params: Any = {"url": magnet, "save_path": str(save_path)}
                params = self._apply_seed_mode_if_complete(params, info_hash)
                handle = self.session.add_torrent(params)
                self.handles[info_hash] = handle
            except Exception as exc:
                print(
                    f"Failed DB fallback restore for {info_hash}: {exc}"
                )  # TODO - logger

    @staticmethod
    def _magnet_from_restore_row(row: Dict[str, Any]) -> Optional[str]:
        try:
            from adapters.persistence.models import Torrent
        except ImportError:
            from AnimeManager.adapters.persistence.models import Torrent  # type: ignore

        raw_hash = row.get("hash")
        if not raw_hash:
            return None
        name = row.get("name")
        trackers = row.get("trackers")
        if isinstance(trackers, str):
            import json as _json

            try:
                trackers = _json.loads(trackers)
            except Exception:
                trackers = []
        if not isinstance(trackers, (list, tuple)):
            trackers = []
        try:
            torrent = Torrent(hash=str(raw_hash), name=name, trackers=list(trackers))
            return torrent.to_magnet()
        except Exception:
            return f"magnet:?xt=urn:btih:{raw_hash}"

    def _process_alert(self, alert: Any) -> None:
        if lt is None:
            return
        save_alert = getattr(lt, "save_resume_data_alert", None)
        failed_alert = getattr(lt, "save_resume_data_failed_alert", None)
        state_alert = getattr(lt, "state_update_alert", None)

        if save_alert is not None and isinstance(alert, save_alert):
            self._write_resume_alert(alert)
            return
        if failed_alert is not None and isinstance(alert, failed_alert):
            msg = getattr(alert, "message", None) or getattr(alert, "error", "")
            print(f"Resume save failed: {msg}")  # TODO - logger
            with self._resume_lock:
                if self._pending_resume_saves > 0:
                    self._pending_resume_saves -= 1
            return
        if isinstance(alert, lt.torrent_added_alert):
            h = alert.handle
            info_hash = self._normalise_hash(h.info_hash())
            self.handles[info_hash] = h
            return
        if isinstance(alert, lt.torrent_removed_alert):
            info_hash = self._normalise_hash(alert.info_hash)
            self.handles.pop(info_hash, None)
            return
        if isinstance(alert, lt.torrent_error_alert):
            print(f"Torrent error: {alert.message}")  # TODO - use logger
            return
        if state_alert is not None and isinstance(alert, state_alert):
            try:
                status = alert.status
                state = getattr(status, "state", None)
                finished = getattr(lt.torrent_status, "finished", None)
                seeding = getattr(lt.torrent_status, "seeding", None)
                if state in (finished, seeding):
                    handle = alert.handle
                    if handle.is_valid():
                        handle.save_resume_data()
            except Exception:
                pass

    def _serialize_resume_alert(self, alert: Any) -> Optional[bytes]:
        """Encode a save_resume_data_alert to on-disk fastresume bytes."""
        if lt is None:
            return None
        params = getattr(alert, "params", None)
        if params is not None:
            try:
                writer = getattr(lt, "write_resume_data_buf", None)
                if callable(writer):
                    return bytes(writer(params))
            except Exception:
                pass
            try:
                writer = getattr(lt, "write_resume_data", None)
                if callable(writer):
                    entry = writer(params)
                    return bytes(lt.bencode(entry))
            except Exception:
                pass
        legacy = getattr(alert, "resume_data", None)
        if isinstance(legacy, (bytes, bytearray)):
            return bytes(legacy)
        if isinstance(legacy, dict):
            try:
                return bytes(lt.bencode(legacy))
            except Exception:
                return None
        return None

    def _write_resume_alert(self, alert: Any) -> None:
        resume_bytes = self._serialize_resume_alert(alert)
        if not resume_bytes:
            with self._resume_lock:
                if self._pending_resume_saves > 0:
                    self._pending_resume_saves -= 1
            return
        try:
            handle = alert.handle
            info_hash = self._normalise_hash(handle.info_hash())
        except Exception:
            info_hash = ""
        if info_hash:
            path = self._resume_file_path(info_hash)
            try:
                with self._resume_file_locks[info_hash]:
                    self._atomic_write_bytes(path, resume_bytes)
            except Exception as exc:
                print(f"Failed to write resume file {path}: {exc}")  # TODO - logger
        with self._resume_lock:
            if self._pending_resume_saves > 0:
                self._pending_resume_saves -= 1

    def _maybe_periodic_save(self) -> None:
        now = time.time()
        if now - self._last_periodic_save < _PERIODIC_SAVE_INTERVAL_S:
            return
        self._last_periodic_save = now
        for info_hash, handle in list(self.handles.items()):
            if not handle.is_valid():
                continue
            last = self._last_handle_save.get(info_hash, 0.0)
            if now - last < _PERIODIC_SAVE_INTERVAL_S:
                continue
            try:
                handle.save_resume_data()
                self._last_handle_save[info_hash] = now
                with self._resume_lock:
                    self._pending_resume_saves += 1
            except Exception:
                pass

    def _session_thread(self):
        """Background thread to handle session alerts and updates."""
        while self._running and self.session:
            try:
                alerts = self.session.pop_alerts()
                for alert in alerts:
                    self._process_alert(alert)
                self._maybe_periodic_save()
                time.sleep(0.1)
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
            raise TorrentException("LibTorrent configuration cancelled by user")

        settings = {}
        for field, name in fields_name.items():
            settings[field] = data.get(name, "")

        self.settings = settings
        try:
            from shared.utils.general import persist_manager_settings
        except Exception:  # pragma: no cover - packaged install fallback
            from AnimeManager.shared.utils.general import persist_manager_settings  # type: ignore

        try:
            persist_manager_settings("torrent_managers", self.name, self.settings)
        except Exception:
            pass

        self.initialize()

    @staticmethod
    def wait_connection(func):
        def wrapper(self, *args, **kwargs):
            if not self._session_ready.wait(timeout=_SESSION_READY_TIMEOUT_S):
                raise TorrentException("LibTorrent session not ready")
            if self.session is None or not self._running:
                raise TorrentException("LibTorrent session not available")
            return BaseTorrentManager.error_wrapper(func)(self, *args, **kwargs)

        return wrapper

    @wait_connection
    def add(self, hashes, path=None, **kwargs):
        if isinstance(hashes, str):
            items = [hashes]
        else:
            items = list(hashes or [])

        save_path = (
            path or self.settings.get("download_path", None)
            if isinstance(self.settings, dict)
            else None
        )
        if not save_path:
            save_path = self.download_path

        if save_path:
            try:
                os.makedirs(save_path, exist_ok=True)
            except OSError:
                save_path = self.download_path
                try:
                    os.makedirs(save_path, exist_ok=True)
                except OSError:
                    pass

        added: list[dict[str, Any]] = []
        for item in items:
            try:
                if self.session is None:
                    raise TorrentException("LibTorrent session is not initialized")

                if isinstance(item, str) and item.startswith("magnet:"):
                    params = {"url": item, "save_path": save_path}
                    handle = self.session.add_torrent(params)
                elif isinstance(item, str) and os.path.exists(item):
                    info = lt.torrent_info(item)
                    params = {"ti": info, "save_path": save_path}
                    handle = self.session.add_torrent(params)
                else:
                    raise TorrentException(
                        f"Torrent file not found or invalid magnet: {item}"
                    )

                info_hash = self._normalise_hash(handle.info_hash())
                self.handles[info_hash] = handle

                name: Optional[str] = None
                try:
                    status = handle.status()
                    name = getattr(status, "name", None) or None
                except Exception:
                    name = None
                if not name and isinstance(item, str) and item.startswith("magnet:"):
                    from urllib.parse import parse_qs

                    try:
                        qs = parse_qs(item[len("magnet:?") :])
                        name = (qs.get("dn") or [None])[0]
                    except Exception:
                        name = None

                try:
                    handle.save_resume_data()
                    with self._resume_lock:
                        self._pending_resume_saves += 1
                except Exception:
                    pass

                added.append(
                    {
                        "hash": info_hash,
                        "name": name,
                        "save_path": save_path,
                    }
                )
            except TorrentException:
                raise
            except Exception as e:
                raise TorrentException(f"Failed to add torrent {item}: {str(e)}")

        return added

    @wait_connection
    def list(self, filter=None, hashes=None):
        torrents = []
        hash_filter = None
        if hashes is not None and len(hashes) > 0:
            hash_filter = {self._normalise_hash(h) for h in hashes if h}

        for info_hash, handle in self.handles.items():
            if hash_filter is not None and info_hash not in hash_filter:
                continue

            try:
                status = handle.status()
                if filter == TorrentListFilter.COMPLETED and not status.is_seeding:
                    continue
                elif filter == TorrentListFilter.DOWNLOADING and status.is_seeding:
                    continue

                torrent_data = self._convert_handle_to_torrent_data(handle, status)
                if torrent_data:
                    torrents.append(torrent_data)
            except Exception as e:
                print(
                    f"Error getting status for torrent {info_hash}: {str(e)}"
                )  # TODO - use logger
                continue

        return torrents

    @wait_connection
    def move(self, hashes=None, paths=None, *, path=None, **kwargs):
        if isinstance(hashes, str):
            hashes = [hashes]
        if not hashes:
            return

        dest = path if path is not None else paths
        if isinstance(dest, (list, tuple)):
            dest = dest[0] if dest else ""
        dest = dest or ""

        if dest:
            try:
                os.makedirs(dest, exist_ok=True)
            except OSError:
                pass

        for hash_str in hashes:
            key = self._normalise_hash(hash_str)
            if key in self.handles:
                try:
                    handle = self.handles[key]
                    handle.move_storage(dest)
                    try:
                        handle.save_resume_data()
                        with self._resume_lock:
                            self._pending_resume_saves += 1
                    except Exception:
                        pass
                except Exception as e:
                    raise TorrentException(f"Failed to move torrent {hash_str}: {str(e)}")

    @wait_connection
    def delete(self, hashes, delete_files=True):
        if isinstance(hashes, str):
            hashes = [hashes]

        for hash_str in hashes:
            key = self._normalise_hash(hash_str)
            if key in self.handles:
                try:
                    handle = self.handles[key]
                    if self.session is None or lt is None:
                        raise TorrentException(
                            "LibTorrent session or library not available"
                        )
                    options = (
                        lt.options_t.delete_files if delete_files else 0
                    )
                    self.session.remove_torrent(handle, options)
                    self.handles.pop(key, None)
                except Exception as e:
                    raise TorrentException(f"Failed to delete torrent {hash_str}: {str(e)}")
            resume_path = self._resume_file_path(key)
            try:
                if os.path.isfile(resume_path):
                    os.remove(resume_path)
            except OSError:
                pass

    @wait_connection
    def list_files(self, hash_value):
        if self.session is None or lt is None:
            return []
        key = self._normalise_hash(hash_value)
        handle = self.handles.get(key)
        if handle is None or not handle.has_metadata():
            return []
        try:
            status = handle.status()
            save_path = str(status.save_path or "").strip()
            torrent_info = handle.get_torrent_info()
            file_storage = torrent_info.files()
            out: list[str] = []
            for index in range(file_storage.num_files()):
                rel = file_storage.file_path(index)
                if save_path:
                    out.append(os.path.join(save_path, rel))
                else:
                    out.append(rel)
            return out
        except Exception:
            return []

    def _convert_handle_to_torrent_data(self, handle, status):
        try:
            info_hash = self._normalise_hash(handle.info_hash())

            if handle.has_metadata():
                torrent_info = handle.get_torrent_info()
                name = torrent_info.name()
                total_size = torrent_info.total_size()
            else:
                name = status.name or info_hash
                total_size = status.total_wanted

            trackers = []
            for tracker in handle.trackers():
                trackers.append(tracker["url"])

            progress = status.progress
            downloaded = (
                int(total_size * progress) if total_size > 0 else status.total_download
            )

            dl_speed = int(getattr(status, "download_rate", 0) or 0)
            remaining = (
                total_size - downloaded if total_size and downloaded is not None else 0
            )
            eta: Optional[int]
            if dl_speed > 0 and remaining > 0:
                eta = int(remaining / dl_speed)
            else:
                eta = None

            torrent_data = {
                "hash": info_hash,
                "name": name,
                "trackers": trackers,
                "seeds": status.num_seeds,
                "leech": status.num_peers - status.num_seeds,
                "size": total_size,
                "path": status.save_path,
                "downloaded": downloaded,
                "link": None,
                "progress": progress,
                "state": self._get_torrent_state(status),
                "dl_speed": dl_speed,
                "eta": eta,
            }

            return torrent_data

        except Exception as e:
            print(f"Error converting torrent data: {str(e)}")  # TODO - use logger
            return None

    def _get_torrent_state(self, status):
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

    def _drain_resume_saves(self) -> None:
        if self.session is None:
            return
        with self._resume_lock:
            pending = self._pending_resume_saves
        if pending <= 0:
            for handle in list(self.handles.values()):
                if handle.is_valid():
                    try:
                        handle.save_resume_data()
                        with self._resume_lock:
                            self._pending_resume_saves += 1
                    except Exception:
                        pass
        deadline = time.time() + _SHUTDOWN_SAVE_TIMEOUT_S
        while time.time() < deadline:
            with self._resume_lock:
                pending = self._pending_resume_saves
            if pending <= 0:
                break
            try:
                for alert in self.session.pop_alerts():
                    self._process_alert(alert)
            except Exception:
                break
            time.sleep(0.05)

    def close(self):
        """Clean shutdown: flush fast-resume files then tear down the session."""
        self._shutting_down = True
        if self.session:
            try:
                with self._resume_lock:
                    for handle in list(self.handles.values()):
                        if handle.is_valid():
                            try:
                                handle.save_resume_data()
                                self._pending_resume_saves += 1
                            except Exception:
                                pass
            except Exception:
                pass

        # Stop the alert thread before draining so it does not steal alerts.
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

        if self.session:
            try:
                self._drain_resume_saves()
            except Exception as e:
                print(f"Error saving resume data: {e}")  # TODO - use logger

        if self.session:
            try:
                self.session.pause()
            except Exception as e:
                print(f"Error during session cleanup: {str(e)}")  # TODO - use logger
            finally:
                self.session = None
                self.handles.clear()

        self._session_ready.clear()
        self._shutting_down = False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


if __name__ == "__main__":
    settings = {
        "download_path": os.path.join(tempfile.gettempdir(), "test_libtorrent"),
        "listen_port": 6881,
    }

    manager = LibTorrent(settings)

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
