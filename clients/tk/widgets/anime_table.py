"""Treeview wrapper for the anime browser grid."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable


class AnimeTable(ttk.Frame):
    COLUMNS = ("id", "title", "status", "episodes", "rating", "tag", "liked")

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_activate: Callable[[int], None],
        on_secondary: Callable[[int], None],
    ) -> None:
        super().__init__(master)
        self._on_activate = on_activate
        self._on_secondary = on_secondary
        self._by_item: dict[str, dict[str, Any]] = {}

        self.tree = ttk.Treeview(self, columns=self.COLUMNS, show="headings", height=22)
        widths = {
            "id": 60,
            "title": 400,
            "status": 120,
            "episodes": 80,
            "rating": 120,
            "tag": 120,
            "liked": 70,
        }
        for col in self.COLUMNS:
            self.tree.heading(col, text=col.upper())
            self.tree.column(col, width=widths[col], anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self._double_click)
        self.tree.bind("<Button-3>", self._right_click)

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.tree.delete(*self.tree.get_children())
        self._by_item.clear()
        for row in rows:
            iid = self.tree.insert(
                "",
                tk.END,
                values=(
                    row.get("id"),
                    row.get("title"),
                    row.get("status") or "",
                    row.get("episodes") or "",
                    row.get("rating") or "",
                    row.get("tag") or "NONE",
                    "Yes" if row.get("liked") else "No",
                ),
            )
            self._by_item[iid] = row

    def selected_anime_id(self) -> int | None:
        selection = self.tree.selection()
        if not selection:
            return None
        row = self._by_item.get(selection[0])
        if not row:
            return None
        anime_id = row.get("id")
        try:
            return int(anime_id)
        except Exception:
            return None

    def _double_click(self, _event: tk.Event[tk.Misc]) -> None:
        anime_id = self.selected_anime_id()
        if anime_id is not None:
            self._on_activate(anime_id)

    def _right_click(self, event: tk.Event[tk.Misc]) -> None:
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        self.tree.selection_set(row_id)
        anime = self._by_item.get(row_id)
        if anime is None:
            return
        anime_id = anime.get("id")
        try:
            self._on_secondary(int(anime_id))
        except Exception:
            return
