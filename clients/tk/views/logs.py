"""Log viewer window (dark themed)."""

from __future__ import annotations

import tkinter as tk

from clients.tk.theme import apply_dark_theme, load_theme, resolve_font


class LogsDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("Logs")
        self.geometry("960x420")
        apply_dark_theme(self)
        theme = load_theme()
        self._text = tk.Text(
            self,
            wrap=tk.NONE,
            bg=theme.color("Gray2"),
            fg=theme.color("White"),
            insertbackground=theme.color("White"),
            bd=0,
            highlightthickness=1,
            highlightbackground=theme.color("Gray4"),
            font=resolve_font(11),
            padx=10,
            pady=8,
        )
        self._text.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        self.append("Tk log panel initialized.")

    def append(self, text: str) -> None:
        self._text.insert(tk.END, text + "\n")
        self._text.see(tk.END)

    def clear(self) -> None:
        self._text.delete("1.0", tk.END)
