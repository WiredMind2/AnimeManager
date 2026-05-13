"""Reusable Tk widgets for the AnimeManager client."""

from .anime_grid import CARD_HEIGHT, CARD_WIDTH, AnimeGrid
from .anime_table import AnimeTable
from .icon_loader import (
    asset_path,
    blank_image,
    card_placeholder,
    fetch_poster_to_disk,
    load_from_disk,
    load_gif_frames,
    load_image,
)
from .icon_menu import IconMenuButton, make_icon_button
from .loading_canvas import LoadingCanvas
from .placeholder_entry import EntryWithPlaceholder
from .scrollable_frame import ScrollableFrame
from .status_bar import StatusBar


__all__ = [
    "AnimeGrid",
    "AnimeTable",
    "CARD_HEIGHT",
    "CARD_WIDTH",
    "EntryWithPlaceholder",
    "IconMenuButton",
    "LoadingCanvas",
    "ScrollableFrame",
    "StatusBar",
    "asset_path",
    "blank_image",
    "card_placeholder",
    "fetch_poster_to_disk",
    "load_from_disk",
    "load_gif_frames",
    "load_image",
    "make_icon_button",
]
