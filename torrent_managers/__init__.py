from .base import Torrent, TorrentException, TorrentListFilter
from .qbittorrent import qBittorrent
from .transmission import Transmission

# Import libtorrent manager only if available to avoid import-time errors on systems
# without a compatible libtorrent binary.
try:
    from .libtorrent import LIBTORRENT_AVAILABLE, LibTorrent
except Exception:
    LibTorrent = None
    LIBTORRENT_AVAILABLE = False

managers = {}
for m in [qBittorrent, Transmission]:
    managers[m.name] = m

if (
    LibTorrent is not None
    and getattr(LibTorrent, "name", None)
    and LIBTORRENT_AVAILABLE
):
    managers[LibTorrent.name] = LibTorrent
