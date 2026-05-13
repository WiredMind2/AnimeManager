"""Secondary windows parity: relations/characters/disks (dark themed)."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from clients.tk.presenters import AnimeBrowserPresenter
from clients.tk.theme import apply_dark_theme


class RelationsDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        presenter: AnimeBrowserPresenter,
        anime: dict[str, Any],
    ) -> None:
        super().__init__(master)
        self.title(f"Relations - {anime.get('title', '')}")
        self.geometry("780x420")
        apply_dark_theme(self)
        self._presenter = presenter
        self._anime = anime
        self._status = tk.StringVar(value="Loading relations...")
        self._tree = ttk.Treeview(
            self,
            columns=("name", "rel_id", "type"),
            show="headings",
            style="AnimeManager.Treeview",
        )
        self._build()
        self._load()

    def _build(self) -> None:
        self._tree.heading("name", text="RELATION")
        self._tree.heading("rel_id", text="RELATED ID")
        self._tree.heading("type", text="TYPE")
        self._tree.column("name", width=260)
        self._tree.column("rel_id", width=110)
        self._tree.column("type", width=130)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        ttk.Label(
            self,
            textvariable=self._status,
            style="AnimeManager.Status.TLabel",
        ).pack(fill=tk.X, padx=12, pady=(0, 12))

    def _load(self) -> None:
        self._presenter.get_relations(
            int(self._anime["id"]),
            on_result=self._render,
            on_error=self._error,
        )

    def _render(self, rows: list[dict[str, Any]]) -> None:
        self._tree.delete(*self._tree.get_children())
        for row in rows:
            self._tree.insert(
                "",
                tk.END,
                values=(row.get("name"), row.get("rel_id"), row.get("type")),
            )
        self._status.set(f"{len(rows)} relations")

    def _error(self, exc: Exception) -> None:
        self._status.set(f"Error: {exc}")
        messagebox.showerror("AnimeManager", str(exc), parent=self)


class CharactersDisksDialog(tk.Toplevel):
    """Legacy parity host for windows that are not yet backed by contracts."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("Characters / Disks")
        self.geometry("760x320")
        apply_dark_theme(self)
        ttk.Label(
            self,
            text=(
                "Character and disk-manager flows are exposed as secondary windows.\n"
                "Legacy internals are intentionally hidden from Tk in the rebuilt client."
            ),
            justify=tk.LEFT,
            style="AnimeManager.TLabel",
        ).pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
