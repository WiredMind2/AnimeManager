"""Torrent client adapters.

This package is the **canonical** home of the torrent client managers
(qBittorrent, Transmission, optional LibTorrent). The legacy
``torrent_managers`` package is a thin compatibility shim that
re-exports from here.
"""

from __future__ import annotations

from .base import Torrent, TorrentException, TorrentListFilter
from .qbittorrent import qBittorrent
from .transmission import Transmission

try:
    from .libtorrent import LIBTORRENT_AVAILABLE, LibTorrent
except Exception:  # pragma: no cover - optional binary missing
    LibTorrent = None
    LIBTORRENT_AVAILABLE = False

managers: dict[str, type] = {}
for _m in [qBittorrent, Transmission]:
    managers[_m.name] = _m

if (
    LibTorrent is not None
    and getattr(LibTorrent, "name", None)
    and LIBTORRENT_AVAILABLE
):
    managers[LibTorrent.name] = LibTorrent

__all__ = [
    "Torrent",
    "TorrentException",
    "TorrentListFilter",
    "qBittorrent",
    "Transmission",
    "LibTorrent",
    "LIBTORRENT_AVAILABLE",
    "managers",
]
