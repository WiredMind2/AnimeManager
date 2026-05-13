"""Tk views."""

from .anime_browser import AnimeBrowserView
from .anime_details import AnimeDetailsDialog
from .characters_disks import CharactersDisksDialog, RelationsDialog
from .logs import LogsDialog
from .seasons_search_terms import SearchTermsDialog, SeasonSelectorDialog
from .settings import SettingsDialog
from .torrent_download import TorrentDownloadDialog

__all__ = [
    "AnimeBrowserView",
    "AnimeDetailsDialog",
    "CharactersDisksDialog",
    "LogsDialog",
    "RelationsDialog",
    "SearchTermsDialog",
    "SeasonSelectorDialog",
    "SettingsDialog",
    "TorrentDownloadDialog",
]
