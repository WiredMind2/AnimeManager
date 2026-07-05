import threading

import qbittorrentapi

try:
    from .base import (BaseTorrentManager, Torrent, TorrentException,
                       TorrentListFilter)
except ImportError:
    from base import (BaseTorrentManager, Torrent, TorrentException,
                      TorrentListFilter)

try:
    from clients.tk.dialogs import LoginDialog
    from shared.utils.general import persist_manager_settings
except Exception:  # pragma: no cover - optional collaborators
    try:
        from AnimeManager.clients.tk.dialogs import LoginDialog  # type: ignore
        from AnimeManager.shared.utils.general import persist_manager_settings  # type: ignore
    except Exception:
        LoginDialog = None
        persist_manager_settings = None


class qBittorrent(BaseTorrentManager):
    name = "qBittorrent"

    def __init__(self, *args, **kwargs):
        self.qb = None
        super().__init__(*args, **kwargs)

    def initialize(self):
        self.url = self.settings.get("url", "")
        if self.url == "":
            return self.login_dialog()

        self.login = self.settings.get("user", "")
        self.password = self.settings.get("password", "")

        self.timeout = self.settings.get("timeout", 2)  # TODO
        self.login_event = threading.Event()
        self.connect()

    def connect(self, thread=True):
        if thread is True:
            # Use a different thread to avoid blocking
            threading.Thread(target=self.connect, args=(False,), daemon=True).start()
            return

        try:
            if self.qb is not None:
                try:
                    self.qb.auth_log_out()
                except Exception:
                    pass

            self.qb = qbittorrentapi.Client(self.url, REQUESTS_ARGS={"timeout": 0.5})
            # Attempt login; some qbittorrentapi versions accept 'timeout' arg, others may not
            try:
                self.qb.auth_log_in(self.login, self.password, timeout=0.5)
            except TypeError:
                self.qb.auth_log_in(self.login, self.password)

        except Exception as e:
            # Handle common connection/login failures gracefully
            try:
                from qbittorrentapi import LoginFailed
            except Exception:
                LoginFailed = None

            msg = str(e)
            if LoginFailed is not None and isinstance(e, LoginFailed):
                self.qb = None
                self.login_event = None
                print("Couldn't connect to qBittorrent client!")
                return None
            if msg.startswith("Failed to connect to qBittorrent"):
                self.qb = None
                self.login_event = None
                print("Couldn't connect to qBittorrent client!")
                return None

            # Fallback: ask user to re-enter credentials
            return self.login_dialog(failed=True)

        # Post-login checks
        try:
            if not getattr(self.qb, "is_logged_in", True):
                # Probably invalid credentials
                return self.login_dialog(failed=True)
            else:
                args = self.settings.get("qb_settings", None)
                if args:
                    try:
                        self.qb.app_set_preferences(args)
                    except Exception:
                        pass

                if self.login_event is not None:
                    try:
                        self.login_event.set()
                    except Exception:
                        pass
        except Exception:
            pass

    def login_dialog(self, failed=False):
        fields = {}
        fields_name = {"url": "url", "user": "login", "password": "password"}
        for field, name in fields_name.items():
            fields[name] = self.settings.get(field, None)
        validator = lambda r: 1 if r.get("url", "") != "" else "No URL provided"

        title = "Login to qBittorrent UI"
        if failed:
            title = "An error occured, please try again\n" + title

        # Guard in case the UI helper isn't available in this environment
        if LoginDialog is None:
            raise TorrentException("Login dialog not available")

        dialog = LoginDialog(fields=fields, title=title, validator=validator)
        data = dialog.results

        settings = {}
        if data is not None:
            for field, name in fields_name.items():
                settings[field] = data.get(name, "")
        else:
            # Dialog was cancelled or returned no data, use default values
            for field, name in fields_name.items():
                settings[field] = ""

        self.settings = settings

        try:
            from shared.utils.general import persist_manager_settings
        except Exception:
            try:
                from AnimeManager.shared.utils.general import persist_manager_settings  # type: ignore
            except Exception:
                persist_manager_settings = None

        try:
            if persist_manager_settings is not None:
                persist_manager_settings("torrent_managers", self.name, self.settings)
        except Exception:
            pass

        # Continue initialization after persisting settings
        self.initialize()

    @staticmethod
    def wait_connection(func):
        def wrapper(self, *args, **kwargs):
            if self.qb is None or not (self.login_event and self.login_event.is_set()):
                # Not connected yet
                if self.login_event is None:
                    # Error while connecting
                    raise TorrentException("Couldn't connect to qBittorrent")

                connected = False
                try:
                    connected = self.login_event.wait(self.timeout)
                except Exception:
                    connected = False

                if not connected or self.qb is None:
                    # Couldn't connect
                    raise TorrentException("Couldn't connect to qBittorrent")

            return self.error_wrapper(func)(self, *args, **kwargs)

        return wrapper

    @wait_connection
    def add(self, hashes, path=None, **kwargs):
        """Add one or more magnets / .torrent URLs to qBittorrent.

        Accepts an optional ``path`` keyword (used by the application
        :class:`DownloadManager`) which is forwarded to qBittorrent as
        ``save_path``. Returns a list of :class:`Torrent` objects parsed
        from the input magnets so callers can chain ``move()`` /
        bookkeeping calls without re-querying the qBittorrent API.
        Previously this returned ``None``, which the DownloadManager
        interpreted as failure and the torrent silently vanished from
        the UI even though qBittorrent had accepted it.
        """
        if isinstance(hashes, str):
            items = [hashes]
        else:
            items = list(hashes or [])

        if self.qb is None:
            raise TorrentException("Couldn't connect to qBittorrent")

        add_kwargs: dict = {"urls": items}
        if path:
            add_kwargs["save_path"] = path

        self.qb.torrents_add(**add_kwargs)

        added: list[Torrent] = []
        for item in items:
            t = None
            try:
                if isinstance(item, str) and item.startswith("magnet:"):
                    parsed = Torrent.from_magnet(item)
                    if parsed:
                        t = parsed
            except Exception:
                t = None
            if t is None:
                t = Torrent(hash=None, name=None)
            try:
                t.path = path
            except Exception:
                pass
            added.append(t)
        return added

    @wait_connection
    def list(self, filter=None, hashes=None):
        if filter is not None:
            if filter == TorrentListFilter.ALL:
                filter = "all"
            elif filter == TorrentListFilter.COMPLETED:
                filter = "completed"
            elif filter == TorrentListFilter.DOWNLOADING:
                filter = "downloading"
            else:
                filter = None

        # Normalize empty hashes to None
        if not hashes:
            hashes = None

        if self.qb is None:
            raise TorrentException("Couldn't connect to qBittorrent")

        torrents = self.qb.torrents_info(status_filter=filter, torrent_hashes=hashes)

        # qbittorrentapi returns an object with .data being iterable of torrent objects
        data = list(map(self.convert, getattr(torrents, "data", torrents)))
        return data

    @wait_connection
    def move(self, hashes=None, paths=None, *, path=None, **kwargs):
        """Relocate already-added torrents.

        Accepts both the legacy ``paths`` positional argument and the
        ``path`` keyword used by :class:`DownloadManager`.
        """
        if not hashes:
            return

        dest = path if path is not None else paths
        if isinstance(dest, (list, tuple)):
            dest = dest[0] if dest else None
        if dest is None:
            raise TorrentException("No destination path provided")

        if self.qb is None:
            raise TorrentException("Couldn't connect to qBittorrent")

        self.qb.torrents_set_location(location=dest, torrent_hashes=hashes)

    @wait_connection
    def delete(self, hashes, delete_files=True):
        if self.qb is None:
            raise TorrentException("Couldn't connect to qBittorrent")

        self.qb.torrents_delete(delete_files=delete_files, torrent_hashes=hashes)

    def convert(self, data):
        # Convert qbittorrentapi torrent representation to our Torrent
        if hasattr(data, "magnet_uri") and getattr(data, "magnet_uri"):
            t = Torrent.from_magnet(data.magnet_uri)
            if t is False:
                # Magnet parsing failed, fall back to constructing Torrent
                t = Torrent(
                    hash=getattr(data, "hash", None), name=getattr(data, "name", None)
                )
        else:
            t = Torrent(
                hash=getattr(data, "hash", None), name=getattr(data, "name", None)
            )

        # Populate common attributes if available
        try:
            t.size = getattr(data, "size", None)
        except Exception:
            t.size = None

        try:
            t.downloaded = getattr(data, "completed", None)
        except Exception:
            t.downloaded = None

        try:
            t.path = getattr(data, "save_path", None)
        except Exception:
            t.path = None

        # ``Torrent.__setattr__`` only honours keys in ``data_keys`` (it
        # swallows everything else with a log warning). The Item class is
        # a ``dict`` subclass though, so we can stash live status fields
        # via item access -- :meth:`DownloadManager._extract_torrent_field`
        # reads them back through ``dict.get``. This lets the progress
        # bar reflect live state without expanding the canonical
        # ``Torrent.data_keys`` schema (which would ripple into save
        # formats and migrations).
        progress = getattr(data, "progress", None)
        if isinstance(progress, (int, float)):
            t["progress"] = float(progress)

        state = getattr(data, "state", None)
        if state:
            t["state"] = str(state).upper()

        for src, dst in (("dlspeed", "dl_speed"), ("eta", "eta")):
            value = getattr(data, src, None)
            if isinstance(value, (int, float)) and value >= 0:
                t[dst] = value

        return t


if __name__ == "__main__":
    args = {"url": "localhost:8081", "login": "admin", "password": "123456789"}
    qb = qBittorrent(args)
    torrents = qb.list()
    t = qb.list(hashes=[torrents[0].hash])
    pass
