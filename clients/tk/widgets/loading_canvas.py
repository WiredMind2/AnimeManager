"""Animated GIF spinner displayed during long-running operations."""

from __future__ import annotations

import tkinter as tk
from typing import Optional

from clients.tk.theme import load_theme

from .icon_loader import load_gif_frames


class LoadingCanvas(tk.Canvas):
    """A 56×56 canvas that animates the bundled ``loading.gif``."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        width: int = 56,
        height: int = 56,
        interval_ms: int = 60,
        background: Optional[str] = None,
    ) -> None:
        theme = load_theme()
        bg = background or theme.color("Gray2")
        super().__init__(
            master,
            width=width,
            height=height,
            bg=bg,
            highlightthickness=0,
            bd=0,
        )
        self._frames = load_gif_frames("loading.gif")
        self._interval = max(20, int(interval_ms))
        self._index = 0
        self._running = False
        self._tk_after_id: Optional[str] = None
        self._image_id: Optional[int] = None
        self._render_static_first_frame()

    def _render_static_first_frame(self) -> None:
        if not self._frames:
            return
        self._image_id = self.create_image(
            self.winfo_reqwidth() // 2,
            self.winfo_reqheight() // 2,
            image=self._frames[0],
            anchor=tk.CENTER,
        )
        self.itemconfigure(self._image_id, state=tk.HIDDEN)

    def start(self) -> None:
        if self._running or not self._frames:
            return
        self._running = True
        if self._image_id is not None:
            self.itemconfigure(self._image_id, state=tk.NORMAL)
        self._step()

    def stop(self) -> None:
        self._running = False
        if self._tk_after_id is not None:
            try:
                self.after_cancel(self._tk_after_id)
            except tk.TclError:
                pass
            self._tk_after_id = None
        if self._image_id is not None:
            self.itemconfigure(self._image_id, state=tk.HIDDEN)

    def _step(self) -> None:
        if not self._running or not self._frames:
            return
        self._index = (self._index + 1) % len(self._frames)
        if self._image_id is not None:
            self.itemconfigure(self._image_id, image=self._frames[self._index])
        try:
            self._tk_after_id = self.after(self._interval, self._step)
        except tk.TclError:
            self._tk_after_id = None


__all__ = ["LoadingCanvas"]
