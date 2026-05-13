"""Smoke tests for the dark-themed Tk widgets."""

from __future__ import annotations

import tkinter as tk

import pytest

from clients.tk.theme import load_theme
from clients.tk.widgets import (
    AnimeGrid,
    EntryWithPlaceholder,
    IconMenuButton,
    LoadingCanvas,
    ScrollableFrame,
    StatusBar,
    make_icon_button,
)


def test_status_bar_set_get(tk_root):
    bar = StatusBar(tk_root)
    assert bar.get() == "Ready"
    bar.set("Working")
    assert bar.get() == "Working"
    bar.destroy()


def test_entry_with_placeholder_hides_text_when_unfocused(tk_root):
    var = tk.StringVar()
    entry = EntryWithPlaceholder(
        tk_root,
        placeholder="Search...",
        textvariable=var,
        bg="#181915",
        fg="#F0F0FF",
    )
    assert entry.is_placeholder_visible()
    assert entry.get() == ""
    entry.event_generate("<FocusIn>")
    entry.update_idletasks()
    var.set("naruto")
    assert entry.get() == "naruto"
    entry.destroy()


def test_scrollable_frame_inner_is_paintable(tk_root):
    frame = ScrollableFrame(tk_root)
    label = tk.Label(frame.inner, text="hello")
    label.pack()
    frame.update_idletasks()
    frame.set_scrollregion()
    assert label.winfo_exists() == 1
    frame.destroy()


def test_anime_grid_populates_cards(tk_root):
    grid = AnimeGrid(
        tk_root,
        on_left_click=lambda anime: None,
        on_right_click=lambda anime: None,
        columns=3,
    )
    rows = [
        {"id": 1, "title": "Cowboy Bebop", "tag": "SEEN", "liked": True},
        {"id": 2, "title": "Trigun", "tag": "WATCHING"},
        {"id": 3, "title": "Berserk", "tag": "NONE", "liked": False},
        {"id": 4, "title": "Akira", "tag": "WATCHLIST"},
    ]
    grid.set_rows(rows)
    # 4 cards expected (one per row)
    assert len(grid._cards) == 4
    # First card label includes the heart suffix for liked
    assert "\u2764" in grid._cards[0].label.cget("text")
    grid.destroy()


def test_anime_grid_empty_message(tk_root):
    grid = AnimeGrid(
        tk_root,
        on_left_click=lambda anime: None,
        on_right_click=lambda anime: None,
        columns=4,
    )
    grid.pack()
    grid.set_rows([])
    tk_root.update_idletasks()
    assert grid._empty_label.cget("text") == "No results"
    info = grid._empty_label.grid_info()
    assert info, "empty label should be placed on the grid"
    grid.destroy()


def test_icon_menu_button_creates_popup_menu(tk_root):
    invoked = []
    btn = IconMenuButton(
        tk_root,
        icon_name="menu.png",
        icon_size=(30, 30),
        fallback_text="MENU",
        entries=[
            ("Item A", "Green", lambda: invoked.append("A")),
            ("Item B", "Red", lambda: invoked.append("B")),
        ],
    )
    # The internal menu has two commands plus the implicit tearoff line.
    last = btn._menu.index("end")
    assert last is not None and last >= 1
    btn._menu.invoke(0)
    assert invoked == ["A"]
    btn.destroy()


def test_loading_canvas_lifecycle(tk_root):
    canvas = LoadingCanvas(tk_root)
    # Starting + stopping should not raise even when no frames are loaded.
    canvas.start()
    canvas.stop()
    canvas.destroy()


def test_make_icon_button_falls_back_to_text(tk_root):
    btn = make_icon_button(
        tk_root,
        icon_name="__missing__.png",
        icon_size=(24, 24),
        fallback_text="X",
    )
    assert btn.cget("text") == "X"
    btn.destroy()
