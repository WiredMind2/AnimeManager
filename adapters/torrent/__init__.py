"""Torrent client adapters.

This package is the **canonical** home of the torrent client managers
(qBittorrent, Transmission, optional LibTorrent). The legacy
``torrent_managers`` package is a thin compatibility shim that
re-exports from here.
"""

from __future__ import annotations

import os

from .base import Torrent, TorrentException, TorrentListFilter
from .qbittorrent import qBittorrent
from .transmission import Transmission

try:
    from .libtorrent import LIBTORRENT_AVAILABLE, LibTorrent
except Exception:  # pragma: no cover - optional binary missing
    LibTorrent = None
    LIBTORRENT_AVAILABLE = False

try:
    from .libtorrent_remote import LibTorrentRemote
except Exception:  # pragma: no cover - optional dependency missing
    LibTorrentRemote = None  # type: ignore[assignment,misc]

managers: dict[str, type] = {}
for _m in [qBittorrent, Transmission]:
    managers[_m.name] = _m


def _libtorrent_manager_class() -> type | None:
    if os.getenv("LIBTORRENT_DAEMON_URL", "").strip() and LibTorrentRemote is not None:
        return LibTorrentRemote
    if (
        LibTorrent is not None
        and getattr(LibTorrent, "name", None)
        and LIBTORRENT_AVAILABLE
    ):
        return LibTorrent
    return None


_lt_manager = _libtorrent_manager_class()
if _lt_manager is not None:
    managers[_lt_manager.name] = _lt_manager

__all__ = [
    "Torrent",
    "TorrentException",
    "TorrentListFilter",
    "qBittorrent",
    "Transmission",
    "LibTorrent",
    "LibTorrentRemote",
    "LIBTORRENT_AVAILABLE",
    "managers",
]
