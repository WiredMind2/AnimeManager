"""Settings editor dialog (dark themed)."""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from clients.tk.presenters import AnimeBrowserPresenter
from clients.tk.theme import apply_dark_theme, load_theme, resolve_font


class SettingsDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, presenter: AnimeBrowserPresenter) -> None:
        super().__init__(master)
        self.title("Settings")
        self.geometry("980x680")
        apply_dark_theme(self)
        self._theme = load_theme()
        self._presenter = presenter
        self._status = tk.StringVar(value="Loading settings...")
        self._text: tk.Text | None = None
        self._build()
        self._load()

    def _build(self) -> None:
        root = ttk.Frame(self, style="AnimeManager.TFrame")
        root.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        ttk.Label(
            root,
            text="Edit settings JSON (legacy parity)",
            style="AnimeManager.Header.TLabel",
        ).pack(anchor=tk.W, pady=(0, 6))
        text = tk.Text(
            root,
            wrap=tk.NONE,
            bg=self._theme.color("Gray2"),
            fg=self._theme.color("White"),
            insertbackground=self._theme.color("White"),
            bd=0,
            highlightthickness=1,
            highlightbackground=self._theme.color("Gray4"),
            font=resolve_font(11),
            padx=8,
            pady=6,
        )
        text.pack(fill=tk.BOTH, expand=True)
        self._text = text

        btn = ttk.Frame(root, style="AnimeManager.TFrame")
        btn.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btn, text="Reload", command=self._load, style="AnimeManager.TButton").pack(side=tk.LEFT)
        ttk.Button(btn, text="Save", command=self._save, style="AnimeManager.TButton").pack(side=tk.LEFT, padx=6)
        ttk.Label(btn, textvariable=self._status, style="AnimeManager.Status.TLabel").pack(side=tk.LEFT, padx=10)

    def _load(self) -> None:
        self._status.set("Loading...")
        self._presenter.get_settings(on_result=self._show_settings, on_error=self._error)

    def _show_settings(self, settings: dict[str, Any]) -> None:
        if self._text is None:
            return
        self._text.delete("1.0", tk.END)
        self._text.insert("1.0", json.dumps(settings, indent=2, ensure_ascii=False))
        self._status.set("Settings loaded")

    def _save(self) -> None:
        if self._text is None:
            return
        payload = self._text.get("1.0", tk.END).strip()
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            messagebox.showerror("AnimeManager", f"Invalid JSON: {exc}", parent=self)
            return
        self._status.set("Saving...")
        self._presenter.update_settings(parsed, on_result=self._show_settings, on_error=self._error)

    def _error(self, exc: Exception) -> None:
        self._status.set(f"Error: {exc}")
        messagebox.showerror("AnimeManager", str(exc), parent=self)
