"""Torrent search and download dialog (dark themed)."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from clients.tk.presenters import AnimeBrowserPresenter
from clients.tk.theme import apply_dark_theme


class TorrentDownloadDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        presenter: AnimeBrowserPresenter,
        anime: dict[str, Any],
    ) -> None:
        super().__init__(master)
        self.title(f"Torrents - {anime.get('title', 'Anime')}")
        self.geometry("1100x550")
        apply_dark_theme(self)
        self._presenter = presenter
        self._anime = anime
        self._rows: list[dict[str, Any]] = []

        self._term = tk.StringVar(value=anime.get("title") or "")
        self._profile = tk.StringVar(value="interactive")
        self._status = tk.StringVar(value="Ready")
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self, style="AnimeManager.TFrame")
        top.pack(fill=tk.X, padx=12, pady=12)

        ttk.Label(top, text="Terms (comma separated)", style="AnimeManager.TLabel").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self._term, style="AnimeManager.TEntry").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=8
        )
        ttk.Combobox(
            top,
            textvariable=self._profile,
            values=("interactive", "strict"),
            width=14,
            state="readonly",
            style="AnimeManager.TCombobox",
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(top, text="Search", command=self._search, style="AnimeManager.TButton").pack(side=tk.LEFT)
        ttk.Button(top, text="Refresh Progress", command=self._progress, style="AnimeManager.TButton").pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(top, text="Cancel Download", command=self._cancel, style="AnimeManager.TButton").pack(side=tk.LEFT)

        self._tree = ttk.Treeview(
            self,
            columns=("name", "seeds", "leech", "size", "engine", "hash"),
            show="headings",
            height=18,
            style="AnimeManager.Treeview",
        )
        for col, width in (
            ("name", 560),
            ("seeds", 70),
            ("leech", 70),
            ("size", 90),
            ("engine", 190),
            ("hash", 110),
        ):
            self._tree.heading(col, text=col.upper())
            self._tree.column(col, width=width, anchor=tk.W)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        self._tree.bind("<Double-1>", lambda _e: self._start_selected())

        bottom = ttk.Frame(self, style="AnimeManager.TFrame")
        bottom.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Button(
            bottom,
            text="Start Selected Download",
            command=self._start_selected,
            style="AnimeManager.TButton",
        ).pack(side=tk.LEFT)
        ttk.Label(
            bottom,
            textvariable=self._status,
            style="AnimeManager.Status.TLabel",
        ).pack(side=tk.LEFT, padx=12)

    def _search(self) -> None:
        terms = [part.strip() for part in self._term.get().split(",") if part.strip()]
        if not terms:
            messagebox.showwarning("AnimeManager", "Please provide at least one search term.", parent=self)
            return
        self._status.set("Searching torrents...")
        self._presenter.search_torrents(
            terms=terms,
            profile=self._profile.get(),
            limit=250,
            on_result=self._show_rows,
            on_error=self._error,
        )

    def _show_rows(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._tree.delete(*self._tree.get_children())
        for idx, row in enumerate(rows):
            self._tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    row.get("name"),
                    row.get("seeds"),
                    row.get("leech"),
                    row.get("size"),
                    row.get("engine_url"),
                    row.get("infohash") or "",
                ),
            )
        self._status.set(f"Found {len(rows)} torrents")

    def _start_selected(self) -> None:
        selected = self._tree.selection()
        if not selected:
            messagebox.showwarning("AnimeManager", "Select a torrent row first.", parent=self)
            return
        row = self._rows[int(selected[0])]
        self._status.set("Starting selected download...")
        self._presenter.start_download(
            anime_id=int(self._anime["id"]),
            url=row.get("link"),
            hash_value=row.get("infohash"),
            on_result=lambda started: self._status.set("Started" if started else "Not started"),
            on_error=self._error,
        )

    def _progress(self) -> None:
        self._status.set("Loading progress...")
        self._presenter.get_download_progress(
            int(self._anime["id"]),
            on_result=lambda payload: self._status.set(f"Progress: {payload}"),
            on_error=self._error,
        )

    def _cancel(self) -> None:
        self._presenter.cancel_download(
            int(self._anime["id"]),
            on_result=lambda cancelled: self._status.set(
                "Cancelled" if cancelled else "No active download"
            ),
            on_error=self._error,
        )

    def _error(self, exc: Exception) -> None:
        self._status.set(f"Error: {exc}")
        messagebox.showerror("AnimeManager", str(exc), parent=self)
