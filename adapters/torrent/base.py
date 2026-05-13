import enum

try:
    from adapters.legacy.legacy_classes import Torrent
    from clients.tk.dialogs import LoginDialog
    from shared.telemetry.logger import Logger
except ImportError:  # pragma: no cover - packaged install fallback
    from AnimeManager.adapters.legacy.legacy_classes import Torrent  # type: ignore
    from AnimeManager.clients.tk.dialogs import LoginDialog  # type: ignore
    from AnimeManager.shared.telemetry.logger import Logger  # type: ignore


class BaseTorrentManager(Logger):
    name = ""

    def __init__(self, settings={}, update=False):
        Logger.__init__(self)
        self.settings = settings

        if update:
            self.login_dialog()

        self.initialize()

    @staticmethod
    def error_wrapper(func):
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                print(
                    f"Exception occured on torrent manager ({self.name}): {str(e)}"
                )  # TODO - use logger
                raise TorrentException(*e.args)

        return wrapper

    def initialize(self):
        pass

    def connect(self):
        raise NotImplementedError()

    def login_dialog(self):
        raise NotImplementedError()

    def add(self, hashes):
        raise NotImplementedError()

    def list(self, filter=None):
        raise NotImplementedError()

    def move(self, hashes, paths):
        raise NotImplementedError()

    def delete(self, hashes):
        raise NotImplementedError()


class TorrentListFilter(enum.Enum):
    ALL = "ALL"
    COMPLETED = "COMPLETED"
    DOWNLOADING = "DOWNLOADING"


class TorrentException(Exception):
    pass


if __name__ == "__main__":
    m = "magnet:?xt=urn:btih:dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c&dn=Big+Buck+Bunny&tr=udp%3A%2F%2Fexplodie.org%3A6969&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.empire-js.us%3A1337&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337&tr=wss%3A%2F%2Ftracker.btorrent.xyz&tr=wss%3A%2F%2Ftracker.fastcast.nz&tr=wss%3A%2F%2Ftracker.openwebtorrent.com&ws=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2F&xs=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2Fbig-buck-bunny.torrent"
    t = Torrent.from_magnet(m)
    m2 = t.to_magnet()
    pass
