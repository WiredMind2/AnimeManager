"""Icon-button + popup menu helpers used in the header bar.

The legacy code used ``tk.OptionMenu`` configured to look like an icon
button (no indicator, image instead of text). We instead use a plain
``tk.Button`` with an attached ``tk.Menu`` because ``OptionMenu`` is
unreasonably hard to style consistently across platforms.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Iterable, Optional, Tuple

from clients.tk.theme import load_theme, resolve_font

from .icon_loader import load_image


def make_icon_button(
    master: tk.Misc,
    *,
    icon_name: str,
    icon_size: tuple[int, int],
    command: Optional[Callable[[], None]] = None,
    fallback_text: str = "",
    padx: int = 8,
    pady: int = 4,
) -> tk.Button:
    """Return a dark-themed icon button. Falls back to text if asset missing."""
    theme = load_theme()
    image = load_image(icon_name, icon_size, optional=True)
    button = tk.Button(
        master,
        image=image if image is not None else "",
        text=fallback_text if image is None else "",
        bd=0,
        bg=theme.color("Gray2"),
        activebackground=theme.color("Gray4"),
        fg=theme.color("White"),
        relief="flat",
        highlightthickness=0,
        command=command if command is not None else (lambda: None),
        padx=padx,
        pady=pady,
        cursor="hand2",
    )
    if image is not None:
        # Keep a reference so Tk doesn't garbage collect the PhotoImage.
        button.image = image  # type: ignore[attr-defined]
    return button


class IconMenuButton(tk.Frame):
    """An icon button that opens a dark-themed popup menu when clicked."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        icon_name: str,
        icon_size: tuple[int, int],
        entries: Iterable[Tuple[str, str, Callable[[], None]]],
        fallback_text: str = "",
    ) -> None:
        theme = load_theme()
        super().__init__(master, bg=theme.color("Gray2"))
        self._menu = tk.Menu(
            self,
            tearoff=False,
            bd=0,
            bg=theme.color("Gray2"),
            fg=theme.color("White"),
            activebackground=theme.color("Gray4"),
            activeforeground=theme.color("White"),
            font=resolve_font(13),
            relief="flat",
        )
        for label, color_key, command in entries:
            self._menu.add_command(
                label=label,
                command=command,
                foreground=theme.color(color_key, theme.color("White")),
            )
        self._button = make_icon_button(
            self,
            icon_name=icon_name,
            icon_size=icon_size,
            command=self._show_menu,
            fallback_text=fallback_text,
        )
        self._button.pack()

    def _show_menu(self) -> None:
        x = self._button.winfo_rootx()
        y = self._button.winfo_rooty() + self._button.winfo_height()
        try:
            self._menu.tk_popup(x, y)
        finally:
            self._menu.grab_release()

    def update_entries(
        self,
        entries: Iterable[Tuple[str, str, Callable[[], None]]],
    ) -> None:
        """Replace the menu entries (used when reloading filters)."""
        theme = load_theme()
        self._menu.delete(0, tk.END)
        for label, color_key, command in entries:
            self._menu.add_command(
                label=label,
                command=command,
                foreground=theme.color(color_key, theme.color("White")),
            )


__all__ = ["IconMenuButton", "make_icon_button"]
