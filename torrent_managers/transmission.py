import string
from urllib.parse import urlparse

from transmission_rpc import Client
from transmission_rpc import torrent as transmission_torrent

# Use explicit imports to avoid wildcard behavior and make static analysis happier
try:
    from .base import BaseTorrentManager, TorrentException, TorrentListFilter
except ImportError:
    from base import BaseTorrentManager, TorrentException, TorrentListFilter

try:
    # LoginDialog and Torrent are pulled in by other modules; import explicitly
    from ..classes import Torrent
    from ..dialog_components import LoginDialog
except Exception:
    from classes import Torrent
    from dialog_components import LoginDialog


class Transmission(BaseTorrentManager):
    name = "Transmission"

    def initialize(self):
        url = self.settings.get("url", "")
        if url == "":
            return self.login_dialog()

        parsed = urlparse(url)
        self.url = parsed.path
        self.port = parsed.port or 9091  # Default value

        self.login = self.settings.get("user", "") or None
        self.password = self.settings.get("password", "") or None

        self.connect()

    def connect(self):
        try:

            self.client = Client(
                host=self.url,
                port=self.port,
                username=self.login,
                password=self.password,
                timeout=2,
            )

        except Exception:
            # If connection fails, prompt for credentials / configuration
            self.login_dialog()
        else:
            # Guard usage for static analysis and runtime safety
            if getattr(self, "client", None):
                try:
                    self.client.set_session(incomplete_dir_enabled=False)
                except Exception:
                    # Best-effort: ignore session-setting failures
                    pass
                self.log(
                    "NETWORK", "Successfully connected to Transmission torrent client!"
                )

    def login_dialog(self):
        fields = {}
        fields_name = {"url": "url", "user": "login", "password": "password"}
        for field, name in fields_name.items():
            fields[name] = self.settings.get(field, None)
        validator = lambda r: 1 if r.get("url", "") != "" else "No URL provided"

        dialog = LoginDialog(
            fields=fields, title="Login to Transmission Web UI", validator=validator
        )
        data = dialog.results

        if data is None:
            # Dialog cancelled
            raise ConnectionAbortedError()

        settings = {}
        for field, name in fields_name.items():
            settings[field] = data.get(name, "")

        self.settings = settings

        # Persist these settings to global settings.json
        try:
            from ..general_utils import persist_manager_settings
        except Exception:
            from general_utils import persist_manager_settings

        try:
            persist_manager_settings("torrent_managers", self.name, self.settings)
        except Exception:
            pass

        self.initialize()

    def add(self, hashes):
        # Accept single string or iterable of magnet links/torrent paths
        if isinstance(hashes, str):
            items = [hashes]
        else:
            items = list(hashes or [])

        out = []
        for magnet in items:
            # Defensive check in case the client wasn't initialized
            if not getattr(self, "client", None):
                raise TorrentException("Transmission client not initialized")
            try:
                t = self.client.add_torrent(torrent=magnet)
            except Exception as e:
                raise TorrentException(f"Failed to add torrent: {str(e)}")
            out.append(self.convert(t))
        return out

    def list(self, filter=None, hashes=None):
        if filter is not None:
            if filter == TorrentListFilter.ALL:
                filter = None
            elif filter == TorrentListFilter.COMPLETED:
                filter = lambda t: t.seeding or t.seed_pending
            elif filter == TorrentListFilter.DOWNLOADING:
                filter = lambda t: t.downloading or t.download_pending
            else:
                filter = None

        if hashes is None:
            hashes = []
        invalid_hash = lambda h: len(h) != 40 or (
            set(h) - set(string.ascii_letters + string.digits)
        )

        if not getattr(self, "client", None):
            raise TorrentException("Transmission client not initialized")
        torrents = self.client.get_torrents([h for h in hashes if not invalid_hash(h)])

        data = []
        for torrent in torrents:
            if filter is None or filter(torrent):
                data.append(self.convert(torrent))

        return data

    def move(self, hashes, paths):
        # move(hashes, paths) signature per BaseTorrentManager
        # Ensure client exists before attempting RPC calls
        if not getattr(self, "client", None):
            raise TorrentException("Transmission client not initialized")
        # accept single id or list of ids; transmission_rpc accepts ids param
        ids = hashes if isinstance(hashes, (list, tuple)) else [hashes]
        dst = paths[0] if isinstance(paths, (list, tuple)) and paths else paths
        # transmission_rpc expects either a single id or a single string id; if multiple
        # ids were provided, call for each to ensure type-safety
        if len(ids) == 1:
            self.client.move_torrent_data(ids=ids[0], location=str(dst))
        else:
            for _id in ids:
                self.client.move_torrent_data(ids=_id, location=str(dst))

    def delete(self, hashes):
        if not getattr(self, "client", None):
            raise TorrentException("Transmission client not initialized")
        ids = hashes if isinstance(hashes, (list, tuple)) else [hashes]
        for h in ids:
            self.client.remove_torrent(h, delete_data=True)

    def convert(self, data):
        t = Torrent(
            hash=data.hashString,  # this one better be there
            name=data.get("name", None),
            trackers=data.get("trackers", []),
            size=data.get("total_size", 0),
            downloaded=int(data.get("percent_done", 0) * data.get("total_size", 0)),
            path=data.get("download_dir", ""),
        )
        return t


if __name__ == "__main__":
    # Simple smoke test (local/dev) - not used in production
    args = {
        "url": "william-server.local",
        "user": "admin",
        "password": "123456789",
        "dataPath": "/home/william/Documents/Anime Manager",
    }
    client = Transmission(args)
    torrents = client.list()
    # Example add: client.add([magnet_string])
    # Note: avoid passing network operations without a real transmission instance
    pass
