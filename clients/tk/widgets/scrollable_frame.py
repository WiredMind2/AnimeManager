"""Scrollable Canvas-backed frame used by the anime grid.

A minimal port of the legacy ``window_frames.ScrollableFrame`` that
keeps the dark palette consistent and is small enough to maintain.

The widget exposes ``inner`` as the target for child widgets and
``set_scrollregion`` to be invoked after large rebuilds.
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

from clients.tk.theme import load_theme


class ScrollableFrame(tk.Frame):
    """A vertically-scrollable container with a dark-themed scrollbar."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        background: Optional[str] = None,
        scrollbar_background: Optional[str] = None,
        scrollbar_width: int = 14,
        **kwargs,
    ) -> None:
        theme = load_theme()
        bg = background or theme.color("Gray2")
        track_bg = scrollbar_background or theme.color("Gray4")
        super().__init__(master, bg=bg, **kwargs)

        self.canvas = tk.Canvas(
            self,
            bg=bg,
            highlightthickness=0,
            bd=0,
        )
        self.scrollbar = tk.Scrollbar(
            self,
            orient=tk.VERTICAL,
            command=self.canvas.yview,
            bg=track_bg,
            troughcolor=bg,
            activebackground=theme.color("Gray"),
            bd=0,
            highlightthickness=0,
            width=scrollbar_width,
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.inner = tk.Frame(self.canvas, bg=bg)
        self._inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor=tk.NW)

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind(sequence, self._on_mousewheel)
            self.inner.bind(sequence, self._on_mousewheel)

    def _on_inner_configure(self, _event: tk.Event) -> None:
        self.set_scrollregion()

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._inner_id, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> str:
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        else:
            # Windows/Mac deliver delta=120 per notch.
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta, "units")
        return "break"

    def set_scrollregion(self) -> None:
        bbox = self.canvas.bbox("all")
        if bbox is not None:
            self.canvas.configure(scrollregion=bbox)

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0)


__all__ = ["ScrollableFrame"]
