"""Anime poster grid (legacy main-window centerpiece).

Each anime row in the legacy UI was rendered as a 225×310 poster card
plus a colored title label below it (color keyed off the user tag).
This module recreates that exact layout, with asynchronous poster
fetching via a background callable supplied by the caller (typically
the presenter's :class:`TkAsyncRunner`).

The widget is intentionally agnostic of the backend SDK; it only knows
about ``rows`` (list of dicts) and two callbacks for left/right clicks.
"""

from __future__ import annotations

import os
import tempfile
import tkinter as tk
from pathlib import Path
from typing import Any, Callable, Optional

from clients.tk.theme import load_theme, resolve_font

from .icon_loader import card_placeholder, fetch_poster_to_disk, load_from_disk
from .scrollable_frame import ScrollableFrame


CARD_WIDTH = 225
CARD_HEIGHT = 310
TITLE_HEIGHT = 60
ROW_PADX = 6
ROW_PADY = 6
LIKE_SUFFIX = "  \u2764"  # legacy heart suffix when "liked"


def _cache_root() -> Path:
    return Path(tempfile.gettempdir()) / "AnimeManager" / "posters"


class _Card:
    """A single anime card (image canvas + colored title label)."""

    __slots__ = (
        "anime",
        "canvas",
        "label",
        "_grid_image",
    )

    def __init__(
        self,
        *,
        parent: tk.Widget,
        anime: dict[str, Any],
        on_left: Callable[[dict[str, Any]], None],
        on_right: Callable[[dict[str, Any]], None],
    ) -> None:
        theme = load_theme()
        self.anime = anime
        self.canvas = tk.Canvas(
            parent,
            width=CARD_WIDTH,
            height=CARD_HEIGHT,
            bg=theme.color("Gray3"),
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.label = tk.Label(
            parent,
            text=self._compose_title(anime),
            bg=theme.color("Gray2"),
            fg=theme.tag_color(anime.get("tag")),
            font=resolve_font(13),
            wraplength=CARD_WIDTH - 10,
            justify=tk.CENTER,
            bd=0,
            cursor="hand2",
        )
        self._grid_image = card_placeholder(CARD_WIDTH, CARD_HEIGHT)
        self.canvas.create_image(
            CARD_WIDTH // 2,
            CARD_HEIGHT // 2,
            image=self._grid_image,
            anchor=tk.CENTER,
            tags=("poster",),
        )

        bind_seq = lambda widget: (
            widget.bind("<Button-1>", lambda _e: on_left(anime)),
            widget.bind("<Button-3>", lambda _e: on_right(anime)),
        )
        bind_seq(self.canvas)
        bind_seq(self.label)

    def _compose_title(self, anime: dict[str, Any]) -> str:
        title = (anime.get("title") or "Unknown title").strip()
        if anime.get("liked"):
            title += LIKE_SUFFIX
        return title

    def grid(self, row: int, column: int) -> None:
        self.canvas.grid(row=row, column=column, padx=ROW_PADX, pady=(ROW_PADY, 0), sticky=tk.N)
        self.label.grid(row=row + 1, column=column, padx=ROW_PADX, pady=(2, ROW_PADY), sticky=tk.N)

    def destroy(self) -> None:
        try:
            self.canvas.destroy()
        except tk.TclError:
            pass
        try:
            self.label.destroy()
        except tk.TclError:
            pass

    def set_image(self, image: tk.PhotoImage) -> None:
        self._grid_image = image
        try:
            self.canvas.itemconfigure("poster", image=image)
        except tk.TclError:
            pass


class AnimeGrid(ScrollableFrame):
    """Scrollable grid of poster cards. Replaces the placeholder Treeview."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_left_click: Callable[[dict[str, Any]], None],
        on_right_click: Callable[[dict[str, Any]], None],
        run_async: Optional[Callable[[Callable[[], Any], Callable[[Any], None], Callable[[Exception], None]], None]] = None,
        columns: int = 4,
    ) -> None:
        super().__init__(master)
        self._on_left = on_left_click
        self._on_right = on_right_click
        self._run_async = run_async
        self._columns = max(1, columns)
        self._cards: list[_Card] = []
        self._cache_dir = _cache_root()

        for col in range(self._columns):
            self.inner.grid_columnconfigure(col, weight=1, uniform="cards")

        self._empty_label = tk.Label(
            self.inner,
            text="",
            bg=self.inner["bg"],
            fg=load_theme().color("Gray"),
            font=resolve_font(16, "bold"),
        )

    def show_message(self, message: str) -> None:
        """Replace the grid contents with a centered status message."""
        self.clear()
        self._empty_label.configure(text=message)
        self._empty_label.grid(
            row=0,
            column=0,
            columnspan=self._columns,
            padx=20,
            pady=40,
            sticky=tk.NSEW,
        )
        self.set_scrollregion()

    def clear(self) -> None:
        try:
            self._empty_label.grid_forget()
        except tk.TclError:
            pass
        for card in self._cards:
            card.destroy()
        self._cards = []

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.clear()
        if not rows:
            self.show_message("No results")
            return
        for index, anime in enumerate(rows):
            row = (index // self._columns) * 2
            column = index % self._columns
            card = _Card(
                parent=self.inner,
                anime=anime,
                on_left=self._on_left,
                on_right=self._on_right,
            )
            card.grid(row=row, column=column)
            self._cards.append(card)
            picture_url = anime.get("picture")
            if picture_url and self._run_async is not None:
                self._schedule_poster_fetch(card, anime, picture_url)
        self.scroll_to_top()
        self.set_scrollregion()

    def _poster_path(self, anime: dict[str, Any]) -> Path:
        anime_id = anime.get("id") or "anon"
        return self._cache_dir / f"{anime_id}.jpg"

    def _schedule_poster_fetch(
        self,
        card: _Card,
        anime: dict[str, Any],
        url: str,
    ) -> None:
        if self._run_async is None:
            return
        dest = self._poster_path(anime)

        def worker() -> Optional[Path]:
            fetched = fetch_poster_to_disk(url, dest)
            return fetched

        def on_done(path: Optional[Path]) -> None:
            if path is None:
                return
            image = load_from_disk(path, (CARD_WIDTH, CARD_HEIGHT))
            if image is None:
                return
            try:
                if card.canvas.winfo_exists():
                    card.set_image(image)
            except tk.TclError:
                pass

        def on_error(_exc: Exception) -> None:
            return

        self._run_async(worker, on_done, on_error)


__all__ = ["AnimeGrid", "CARD_HEIGHT", "CARD_WIDTH"]
