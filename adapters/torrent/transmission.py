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
    from adapters.legacy.legacy_classes import Torrent
    from clients.tk.dialogs import LoginDialog
except Exception:  # pragma: no cover - packaged install fallback
    from AnimeManager.adapters.legacy.legacy_classes import Torrent  # type: ignore
    from AnimeManager.clients.tk.dialogs import LoginDialog  # type: ignore


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

        try:
            from shared.utils.general import persist_manager_settings
        except Exception:  # pragma: no cover - packaged install fallback
            from AnimeManager.shared.utils.general import persist_manager_settings  # type: ignore

        try:
            persist_manager_settings("torrent_managers", self.name, self.settings)
        except Exception:
            pass

        self.initialize()

    def add(self, hashes, path=None, **kwargs):
        """Add magnets / torrent URLs to Transmission.

        Accepts an optional ``path`` keyword used by
        :class:`DownloadManager`; it's forwarded as Transmission's
        ``download_dir`` so the file lands in the right anime folder
        from the start.
        """
        if isinstance(hashes, str):
            items = [hashes]
        else:
            items = list(hashes or [])

        out = []
        for magnet in items:
            if not getattr(self, "client", None):
                raise TorrentException("Transmission client not initialized")
            try:
                add_kwargs = {"torrent": magnet}
                if path:
                    add_kwargs["download_dir"] = path
                t = self.client.add_torrent(**add_kwargs)
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

    def move(self, hashes=None, paths=None, *, path=None, **kwargs):
        """Relocate already-added torrents.

        Accepts both the legacy ``paths`` positional argument and the
        ``path`` keyword used by :class:`DownloadManager`.
        """
        if not getattr(self, "client", None):
            raise TorrentException("Transmission client not initialized")
        if not hashes:
            return
        ids = hashes if isinstance(hashes, (list, tuple)) else [hashes]
        dst = path if path is not None else paths
        if isinstance(dst, (list, tuple)):
            dst = dst[0] if dst else None
        if dst is None:
            raise TorrentException("No destination path provided")
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
