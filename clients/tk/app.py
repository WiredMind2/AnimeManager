"""Tk app shell that wires presenter + browser view onto a dark window.

The legacy app used a hidden root + borderless ``Toplevel`` so that the
main window itself was custom-painted dark. This module restores that
shape:

* The hidden ``Tk`` root only holds the taskbar icon (Windows) and the
  ``Esc`` global shortcut.
* The visible window is a borderless ``Toplevel`` styled with the dark
  palette and movable from the header bar.

All workflows still flow through the :class:`AnimeBrowserPresenter`
which is fed by the shared :class:`ClientSDK`. The UI never imports the
domain or adapter layers directly.
"""

from __future__ import annotations

import os
import platform
import tkinter as tk
from typing import Optional

from clients.sdk import ClientSDK
from clients.tk.presenters import AnimeBrowserPresenter, TkAsyncRunner
from clients.tk.theme import (
    ASSETS_DIR,
    apply_dark_window,
    configure_ttk_styles,
    load_theme,
)
from clients.tk.views import AnimeBrowserView


class AnimeManagerTkClient:
    """Hidden root + borderless dark Toplevel, matching the legacy look."""

    def __init__(self, sdk: ClientSDK, *, borderless: Optional[bool] = None) -> None:
        theme = load_theme()
        self._theme = theme
        self._root = tk.Tk()
        self._root.title(theme.window.get("title", "Anime Manager - Browser"))
        # Hide the root: only the borderless Toplevel is visible to the
        # user. ``withdraw`` keeps the taskbar icon on Windows.
        self._root.withdraw()
        self._configure_app_icon(self._root)
        configure_ttk_styles(self._root)

        # Default to borderless on Windows for legacy parity, normal
        # decorations elsewhere so window managers can position/move
        # the app sanely.
        if borderless is None:
            borderless = platform.system() == "Windows" or os.environ.get("ANIMEMANAGER_BORDERLESS") == "1"

        self._main = tk.Toplevel(self._root)
        self._configure_main_window(self._main, borderless=borderless)

        self._runner = TkAsyncRunner(schedule_ui=self._schedule_ui)
        self._view: Optional[AnimeBrowserView] = None
        self._presenter = AnimeBrowserPresenter(
            sdk=sdk,
            runner=self._runner,
            status_cb=self._set_status,
        )
        self._view = AnimeBrowserView(
            self._main,
            self._presenter,
            on_close=self._on_close,
            borderless=borderless,
        )
        self._view.pack(fill=tk.BOTH, expand=True)

        self._main.protocol("WM_DELETE_WINDOW", self._on_close)
        self._main.bind("<Escape>", lambda _e: self._on_close())
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _schedule_ui(self, callback) -> None:
        try:
            self._root.after(0, callback)
        except tk.TclError:
            # The root may be torn down during shutdown; ignore the callback.
            return

    def _configure_app_icon(self, win: tk.Misc) -> None:
        icon_path = ASSETS_DIR / "app_icon" / "icon.ico"
        if not icon_path.is_file():
            return
        try:
            win.iconbitmap(default=str(icon_path))  # type: ignore[attr-defined]
        except tk.TclError:
            try:
                win.iconbitmap(str(icon_path))  # type: ignore[attr-defined]
            except tk.TclError:
                pass

    def _configure_main_window(self, win: tk.Toplevel, *, borderless: bool) -> None:
        theme = self._theme
        title = str(theme.window.get("title", "Anime Manager - Browser"))
        width = int(theme.window.get("width", 920))
        height = int(theme.window.get("height", 600))
        win.title(title)
        win.geometry(f"{width}x{height}+120+80")
        win.minsize(width, 400)
        apply_dark_window(win)
        self._configure_app_icon(win)
        if borderless:
            try:
                win.overrideredirect(True)
            except tk.TclError:  # pragma: no cover - some WMs reject it
                pass
        win.focus_force()

    def _set_status(self, text: str) -> None:
        if self._view is None:
            return
        self._view.set_status(text)

    def _on_close(self) -> None:
        try:
            self._runner.close()
        finally:
            try:
                self._main.destroy()
            except tk.TclError:
                pass
            try:
                self._root.destroy()
            except tk.TclError:
                pass

    @property
    def root(self) -> tk.Tk:
        return self._root

    @property
    def main(self) -> tk.Toplevel:
        return self._main

    def run(self) -> None:
        # While the Tcl event loop is in native code, Ctrl+C may queue a
        # KeyboardInterrupt that is not observed until Python runs again.
        # A periodic after() callback yields to the interpreter so console
        # Ctrl+C reliably tears down the UI on Windows and other platforms.
        self._schedule_sigint_pump()
        try:
            self._root.mainloop()
        except KeyboardInterrupt:
            self._on_close()
            raise SystemExit(130) from None

    def _schedule_sigint_pump(self) -> None:
        interval_ms = 250

        def pump() -> None:
            try:
                if self._root.winfo_exists():
                    self._root.after(interval_ms, pump)
            except tk.TclError:
                return

        try:
            self._root.after(interval_ms, pump)
        except tk.TclError:
            return


def run() -> None:
    AnimeManagerTkClient(ClientSDK()).run()


__all__ = ["AnimeManagerTkClient", "run"]
