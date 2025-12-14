import threading

import qbittorrentapi

try:
    from .base import (BaseTorrentManager, Torrent, TorrentException,
                       TorrentListFilter)
except ImportError:
    from base import (BaseTorrentManager, Torrent, TorrentException,
                      TorrentListFilter)

try:
    # LoginDialog and persist helper live in utils
    from ..dialog_components import LoginDialog
    from ..general_utils import persist_manager_settings
except Exception:
    try:
        from dialog_components import LoginDialog
        from general_utils import persist_manager_settings
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
            threading.Thread(target=self.connect, args=(False,)).start()
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

        # Persist these settings to global settings.json
        try:
            from ..general_utils import persist_manager_settings
        except Exception:
            try:
                from general_utils import persist_manager_settings
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
    def add(self, hashes):
        # Backwards-compatible: accept a single string or iterable of magnets
        if isinstance(hashes, str):
            items = [hashes]
        else:
            items = list(hashes or [])

        # Ensure client is present for static analysis (decorator may not be visible to analyzer)
        if self.qb is None:
            raise TorrentException("Couldn't connect to qBittorrent")

        # qbittorrent API accepts comma-separated or list of urls
        self.qb.torrents_add(urls=items)

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
    def move(self, hashes, paths):
        # Align signature with BaseTorrentManager.move(self, hashes, paths)
        if not hashes:
            return

        if isinstance(paths, (list, tuple)):
            # Prefer the first path if multiple provided
            path = paths[0] if len(paths) > 0 else None
        else:
            path = paths

        if path is None:
            raise TorrentException("No destination path provided")

        if self.qb is None:
            raise TorrentException("Couldn't connect to qBittorrent")

        self.qb.torrents_set_location(location=path, torrent_hashes=hashes)

    @wait_connection
    def delete(self, hashes):
        if self.qb is None:
            raise TorrentException("Couldn't connect to qBittorrent")

        self.qb.torrents_delete(delete_files=True, torrent_hashes=hashes)

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

        return t


if __name__ == "__main__":
    args = {"url": "localhost:8081", "login": "admin", "password": "123456789"}
    qb = qBittorrent(args)
    torrents = qb.list()
    t = qb.list(hashes=[torrents[0].hash])
    pass
