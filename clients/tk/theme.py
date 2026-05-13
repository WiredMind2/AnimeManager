"""Theme + palette for the Tk client (legacy-parity look).

The legacy UI used a dark, borderless aesthetic configured from
``settings.json`` under the ``UI`` block (palette, tag-colors, menu
options). To match the original appearance exactly we read the same
palette here; the values fall back to the documented defaults when the
file isn't reachable.

The module exposes:

* ``COLORS`` -- hex palette (Gray2/Gray3/Gray4/White/Red/Green/Orange/Blue).
* ``MENU_OPTIONS`` -- ordered application-menu entries with action keys.
* ``FILTER_OPTIONS`` -- ordered filter entries with backend filter codes.
* ``TAG_COLORS`` -- mapping of tag → palette key.
* ``WINDOW`` -- main window geometry (title, width, height).
* ``ASSETS_DIR`` -- path to the bundled ``icons/`` folder.
* ``FONT_FAMILY`` / ``FONT_FAMILY_BOLD`` -- preferred fonts (with fallbacks).
* :func:`font`, :func:`apply_dark_theme`, :func:`apply_dark_window`,
  :func:`configure_ttk_styles` -- runtime helpers.

This module is intentionally tiny and side-effect free at import time so
that headless test environments can import it without requiring a Tk
display.
"""

from __future__ import annotations

import json
import os
import tkinter as tk
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any


_DEFAULT_PALETTE: dict[str, str] = {
    "Blue": "#56D8EF",
    "Gray": "#676760",
    "Gray2": "#181915",
    "Gray3": "#282923",
    "Gray4": "#373734",
    "Green": "#98E22B",
    "Orange": "#E79622",
    "Red": "#F92472",
    "White": "#F0F0FF",
}

_DEFAULT_TAG_COLORS: dict[str, str] = {
    "NONE": "White",
    "SEEN": "Green",
    "WATCHING": "Orange",
    "WATCHLIST": "Blue",
}

# Legacy menu options. Each entry maps a label to a palette color key
# and an opaque action key consumed by the browser view.
_DEFAULT_MENU_OPTIONS: list[dict[str, str]] = [
    {"label": "Liked characters", "color": "Green", "action": "characters"},
    {"label": "Disk manager", "color": "Orange", "action": "disks"},
    {"label": "Log panel", "color": "Blue", "action": "logs"},
    {"label": "Clear logs", "color": "Green", "action": "clear_logs"},
    {"label": "Clear cache", "color": "Blue", "action": "clear_cache"},
    {"label": "Settings", "color": "Gray", "action": "settings"},
    {"label": "Reload", "color": "Orange", "action": "reload"},
    {"label": "Exit", "color": "Red", "action": "exit"},
]

# Filter options exactly as in settings.json. Each entry has a label, a
# palette color key and the backend filter name.
_DEFAULT_FILTER_OPTIONS: list[dict[str, str]] = [
    {"label": "Liked", "color": "Red", "filter": "LIKED"},
    {"label": "Seen", "color": "Green", "filter": "SEEN"},
    {"label": "Watching", "color": "Orange", "filter": "WATCHING"},
    {"label": "Watchlist", "color": "Blue", "filter": "WATCHLIST"},
    {"label": "Finished", "color": "Green", "filter": "FINISHED"},
    {"label": "Airing", "color": "Orange", "filter": "AIRING"},
    {"label": "Upcoming", "color": "Blue", "filter": "UPCOMING"},
    {"label": "Rated", "color": "Red", "filter": "RATED"},
    {"label": "By season", "color": "Blue", "filter": "SEASON"},
    {"label": "Random", "color": "Green", "filter": "RANDOM"},
    {"label": "No tags", "color": "White", "filter": "NONE"},
    {"label": "No filter", "color": "Gray", "filter": "DEFAULT"},
]

_DEFAULT_WINDOW: dict[str, Any] = {
    "title": "Anime Manager - Browser",
    "width": 920,
    "height": 600,
    "anime_per_row": 4,
    "anime_per_page": 50,
}

# Preferred font family; falls back transparently if missing.
FONT_FAMILY = "Source Code Pro Medium"
FONT_FAMILY_FALLBACK = "Consolas"


@dataclass(frozen=True)
class FilterOption:
    label: str
    color: str
    filter: str


@dataclass(frozen=True)
class MenuOption:
    label: str
    color: str
    action: str


@dataclass(frozen=True)
class Theme:
    """Resolved palette + legacy menu metadata."""

    colors: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_PALETTE))
    tag_colors: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_TAG_COLORS))
    menu_options: list[MenuOption] = field(default_factory=list)
    filter_options: list[FilterOption] = field(default_factory=list)
    window: dict[str, Any] = field(default_factory=lambda: dict(_DEFAULT_WINDOW))

    def color(self, name: str, fallback: str = "#FFFFFF") -> str:
        return self.colors.get(name, fallback)

    def tag_color(self, tag: str | None) -> str:
        key = self.tag_colors.get((tag or "NONE").upper(), "White")
        return self.color(key)


def _repo_root() -> Path:
    """Return the repository root (package root) regardless of CWD."""
    return Path(__file__).resolve().parent.parent.parent


def _read_settings() -> dict[str, Any]:
    """Best-effort load of ``settings.json`` from the repo root.

    Returns an empty dict on any failure so the defaults take over.
    """
    candidates: list[Path] = []
    env_path = os.environ.get("ANIMEMANAGER_SETTINGS")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(_repo_root() / "settings.json")
    for path in candidates:
        try:
            if path.is_file():
                with path.open("r", encoding="utf-8") as fp:
                    return json.load(fp) or {}
        except (OSError, ValueError):
            continue
    return {}


@lru_cache(maxsize=1)
def load_theme() -> Theme:
    """Resolve the palette/menus from settings, falling back to defaults."""
    settings = _read_settings()
    ui = settings.get("UI", {}) if isinstance(settings, dict) else {}
    windows = settings.get("windows", {}) if isinstance(settings, dict) else {}

    colors = dict(_DEFAULT_PALETTE)
    if isinstance(ui.get("colors"), dict):
        colors.update({k: str(v) for k, v in ui["colors"].items() if isinstance(v, str)})

    tag_colors = dict(_DEFAULT_TAG_COLORS)
    if isinstance(ui.get("tagcolors"), dict):
        tag_colors.update({k: str(v) for k, v in ui["tagcolors"].items() if isinstance(v, str)})

    menu_options = [MenuOption(**entry) for entry in _DEFAULT_MENU_OPTIONS]
    filter_options = [FilterOption(**entry) for entry in _DEFAULT_FILTER_OPTIONS]

    window = dict(_DEFAULT_WINDOW)
    if isinstance(windows, dict):
        window["title"] = str(windows.get("mainWindowTitle", window["title"]))
        try:
            window["width"] = int(windows.get("mainWindowWidth", window["width"]))
            window["height"] = int(windows.get("mainWindowHeight", window["height"]))
        except (TypeError, ValueError):
            pass

    anime_cfg = settings.get("anime", {}) if isinstance(settings, dict) else {}
    if isinstance(anime_cfg, dict):
        try:
            window["anime_per_row"] = int(anime_cfg.get("animePerRow", window["anime_per_row"]))
            window["anime_per_page"] = int(anime_cfg.get("animePerPage", window["anime_per_page"]))
        except (TypeError, ValueError):
            pass

    return Theme(
        colors=colors,
        tag_colors=tag_colors,
        menu_options=menu_options,
        filter_options=filter_options,
        window=window,
    )


def reset_theme_cache() -> None:
    """Clear the cached theme (test helper)."""
    load_theme.cache_clear()


ASSETS_DIR: Path = _repo_root() / "icons"


def resolve_font(size: int = 13, weight: str = "normal") -> tuple[str, int, str]:
    """Return a ``(family, size, weight)`` tuple for a font usable now.

    The legacy UI uses ``Source Code Pro Medium``; we prefer it if
    installed and gracefully fall back to a sane monospace family.
    """
    families = tkfont.families() if _has_default_root() else ()
    family = FONT_FAMILY if FONT_FAMILY in families else FONT_FAMILY_FALLBACK
    return (family, size, weight)


def font(size: int = 13, weight: str = "normal") -> tuple[str, int, str]:
    """Public alias of :func:`resolve_font`."""
    return resolve_font(size=size, weight=weight)


def _has_default_root() -> bool:
    try:
        return tk._default_root is not None  # type: ignore[attr-defined]
    except Exception:
        return False


def apply_dark_window(win: tk.Misc) -> None:
    """Apply legacy palette to a single Toplevel/Tk window.

    Sets the background and configures ttk styles in the matching
    theme. Safe to call multiple times.
    """
    theme = load_theme()
    bg = theme.color("Gray3")
    try:
        win.configure(bg=bg)
    except tk.TclError:
        pass
    configure_ttk_styles(win)


def configure_ttk_styles(master: tk.Misc) -> None:
    """Register the ``AnimeManager.*`` ttk styles used by views/dialogs."""
    theme = load_theme()
    bg = theme.color("Gray3")
    fg = theme.color("White")
    accent = theme.color("Gray2")
    muted = theme.color("Gray4")
    blue = theme.color("Blue")

    style = ttk.Style(master)
    # Use ``clam`` so our color overrides take effect on Windows too.
    try:
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except tk.TclError:  # pragma: no cover - depends on Tk runtime
        pass

    base_font = resolve_font(13)
    title_font = resolve_font(13, "bold")

    style.configure("AnimeManager.TFrame", background=bg)
    style.configure("AnimeManager.Card.TFrame", background=accent)
    style.configure(
        "AnimeManager.TLabel",
        background=bg,
        foreground=fg,
        font=base_font,
    )
    style.configure(
        "AnimeManager.Card.TLabel",
        background=accent,
        foreground=fg,
        font=base_font,
    )
    style.configure(
        "AnimeManager.Status.TLabel",
        background=accent,
        foreground=theme.color("Gray"),
        font=resolve_font(11),
    )
    style.configure(
        "AnimeManager.Header.TLabel",
        background=accent,
        foreground=fg,
        font=title_font,
    )
    style.configure(
        "AnimeManager.TButton",
        background=accent,
        foreground=fg,
        bordercolor=muted,
        focusthickness=0,
        focuscolor=blue,
        padding=(8, 4),
        font=base_font,
    )
    style.map(
        "AnimeManager.TButton",
        background=[("active", muted)],
        foreground=[("disabled", theme.color("Gray"))],
    )
    style.configure(
        "AnimeManager.Treeview",
        background=accent,
        fieldbackground=accent,
        foreground=fg,
        bordercolor=muted,
        rowheight=24,
        font=base_font,
    )
    style.configure(
        "AnimeManager.Treeview.Heading",
        background=muted,
        foreground=fg,
        relief="flat",
        font=title_font,
    )
    style.map(
        "AnimeManager.Treeview",
        background=[("selected", blue)],
        foreground=[("selected", accent)],
    )
    style.configure(
        "AnimeManager.TEntry",
        fieldbackground=accent,
        foreground=fg,
        bordercolor=muted,
        insertcolor=fg,
        padding=4,
    )
    style.configure(
        "AnimeManager.TCombobox",
        fieldbackground=accent,
        background=accent,
        foreground=fg,
        bordercolor=muted,
        arrowcolor=fg,
        padding=4,
    )
    style.map(
        "AnimeManager.TCombobox",
        fieldbackground=[("readonly", accent)],
        selectbackground=[("readonly", blue)],
    )
    style.configure(
        "AnimeManager.TCheckbutton",
        background=bg,
        foreground=fg,
        focuscolor=blue,
    )
    style.configure(
        "AnimeManager.Vertical.TScrollbar",
        background=muted,
        troughcolor=accent,
        bordercolor=accent,
        arrowcolor=fg,
    )
    style.configure(
        "AnimeManager.Horizontal.TScrollbar",
        background=muted,
        troughcolor=accent,
        bordercolor=accent,
        arrowcolor=fg,
    )
    style.configure(
        "AnimeManager.TNotebook",
        background=bg,
        bordercolor=muted,
    )
    style.configure(
        "AnimeManager.TNotebook.Tab",
        background=accent,
        foreground=fg,
        padding=(12, 4),
    )
    style.map(
        "AnimeManager.TNotebook.Tab",
        background=[("selected", muted)],
        foreground=[("selected", fg)],
    )


def apply_dark_theme(window: tk.Misc) -> None:
    """Convenience wrapper used by Toplevel dialogs."""
    apply_dark_window(window)


__all__ = [
    "ASSETS_DIR",
    "FONT_FAMILY",
    "FONT_FAMILY_FALLBACK",
    "FilterOption",
    "MenuOption",
    "Theme",
    "apply_dark_theme",
    "apply_dark_window",
    "configure_ttk_styles",
    "font",
    "load_theme",
    "reset_theme_cache",
    "resolve_font",
]
