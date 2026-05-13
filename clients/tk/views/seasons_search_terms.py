"""Season selector and search-terms management dialogs (dark themed)."""

from __future__ import annotations

import datetime as dt
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

from clients.tk.presenters import AnimeBrowserPresenter
from clients.tk.theme import apply_dark_theme, load_theme, resolve_font


class SearchTermsDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        presenter: AnimeBrowserPresenter,
        anime: dict[str, Any],
    ) -> None:
        super().__init__(master)
        self.title(f"Search Terms - {anime.get('title', '')}")
        self.geometry("620x460")
        apply_dark_theme(self)
        theme = load_theme()
        self._theme = theme
        self._presenter = presenter
        self._anime = anime
        self._status = tk.StringVar(value="Loading search terms...")
        self._term = tk.StringVar()
        self._list = tk.Listbox(
            self,
            bg=theme.color("Gray2"),
            fg=theme.color("White"),
            selectbackground=theme.color("Blue"),
            selectforeground=theme.color("Gray2"),
            highlightthickness=1,
            highlightbackground=theme.color("Gray4"),
            bd=0,
            font=resolve_font(12),
            activestyle="dotbox",
        )
        self._build()
        self.reload()

    def _build(self) -> None:
        top = ttk.Frame(self, style="AnimeManager.TFrame")
        top.pack(fill=tk.X, padx=12, pady=12)
        ttk.Entry(top, textvariable=self._term, style="AnimeManager.TEntry").pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(top, text="Add", command=self._add, style="AnimeManager.TButton").pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            top,
            text="Remove Selected",
            command=self._remove,
            style="AnimeManager.TButton",
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Reload", command=self.reload, style="AnimeManager.TButton").pack(side=tk.LEFT)

        self._list.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        ttk.Label(
            self,
            textvariable=self._status,
            style="AnimeManager.Status.TLabel",
        ).pack(fill=tk.X, padx=12, pady=(0, 12))

    def reload(self) -> None:
        self._presenter.get_search_terms(
            int(self._anime["id"]),
            on_result=self._render,
            on_error=self._error,
        )

    def _render(self, values: list[str]) -> None:
        self._list.delete(0, tk.END)
        for value in values:
            self._list.insert(tk.END, value)
        self._status.set(f"{len(values)} terms")

    def _add(self) -> None:
        term = self._term.get().strip()
        if not term:
            return
        self._presenter.add_search_term(
            int(self._anime["id"]),
            term,
            on_result=lambda _ok: self.reload(),
            on_error=self._error,
        )

    def _remove(self) -> None:
        selected = self._list.curselection()
        if not selected:
            return
        term = self._list.get(selected[0])
        self._presenter.remove_search_term(
            int(self._anime["id"]),
            term,
            on_result=lambda _ok: self.reload(),
            on_error=self._error,
        )

    def _error(self, exc: Exception) -> None:
        self._status.set(f"Error: {exc}")
        messagebox.showerror("AnimeManager", str(exc), parent=self)


class SeasonSelectorDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, on_search: Callable[[str], None]) -> None:
        super().__init__(master)
        self.title("Season Selector")
        self.geometry("440x260")
        apply_dark_theme(self)
        self._on_search = on_search
        self._year = tk.StringVar(value=str(dt.date.today().year))
        self._season = tk.StringVar(value="spring")
        self._build()

    def _build(self) -> None:
        frm = ttk.Frame(self, style="AnimeManager.TFrame")
        frm.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)
        ttk.Label(frm, text="Year", style="AnimeManager.TLabel").grid(
            row=0, column=0, sticky=tk.W, pady=(0, 8)
        )
        ttk.Spinbox(
            frm,
            from_=1980,
            to=dt.date.today().year + 5,
            textvariable=self._year,
        ).grid(row=0, column=1, sticky=tk.EW, pady=(0, 8))
        ttk.Label(frm, text="Season", style="AnimeManager.TLabel").grid(row=1, column=0, sticky=tk.W)
        ttk.Combobox(
            frm,
            textvariable=self._season,
            values=("winter", "spring", "summer", "fall"),
            state="readonly",
            style="AnimeManager.TCombobox",
        ).grid(row=1, column=1, sticky=tk.EW)
        frm.grid_columnconfigure(1, weight=1)

        ttk.Label(
            frm,
            text="Runs a title search with '<season> <year>'.",
            style="AnimeManager.Status.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(12, 12))
        ttk.Button(
            frm,
            text="Search Season",
            command=self._submit,
            style="AnimeManager.TButton",
        ).grid(row=3, column=0, columnspan=2, sticky=tk.EW)

    def _submit(self) -> None:
        query = f"{self._season.get()} {self._year.get()}"
        self._on_search(query)
        self.destroy()
