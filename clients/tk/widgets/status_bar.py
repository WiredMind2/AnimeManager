"""Status bar widget (legacy parity)."""

from __future__ import annotations

import tkinter as tk

from clients.tk.theme import load_theme, resolve_font


class StatusBar(tk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        theme = load_theme()
        super().__init__(master, bg=theme.color("Gray2"), bd=0)
        self._value = tk.StringVar(value="Ready")
        self._label = tk.Label(
            self,
            textvariable=self._value,
            anchor=tk.W,
            bg=theme.color("Gray2"),
            fg=theme.color("Gray"),
            font=resolve_font(11),
            padx=10,
            pady=4,
        )
        self._label.pack(fill=tk.X)

    def set(self, value: str) -> None:
        self._value.set(value)

    def get(self) -> str:
        return self._value.get()
