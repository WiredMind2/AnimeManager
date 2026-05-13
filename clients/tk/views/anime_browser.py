"""Main anime browser view (legacy-parity dark layout).

The view recreates the legacy header bar (menu icon, search entry with
placeholder, animated loader, filter icon, close button) and the 4-column
scrollable poster grid below it. Workflow methods (search, filter, open
detail/torrent dialogs, etc.) are unchanged — they still go through the
shared :class:`AnimeBrowserPresenter`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Any, Callable, Optional

from clients.tk.presenters import AnimeBrowserPresenter
from clients.tk.theme import load_theme, resolve_font
from clients.tk.widgets import (
    AnimeGrid,
    EntryWithPlaceholder,
    IconMenuButton,
    LoadingCanvas,
    StatusBar,
    make_icon_button,
)

from .anime_details import AnimeDetailsDialog
from .characters_disks import CharactersDisksDialog, RelationsDialog
from .logs import LogsDialog
from .seasons_search_terms import SearchTermsDialog, SeasonSelectorDialog
from .settings import SettingsDialog
from .torrent_download import TorrentDownloadDialog


class AnimeBrowserView(tk.Frame):
    """Top-level browser: dark header + scrollable poster grid + status bar."""

    def __init__(
        self,
        master: tk.Misc,
        presenter: AnimeBrowserPresenter,
        *,
        user_id: int = 0,
        on_close: Optional[Callable[[], None]] = None,
        borderless: bool = False,
    ) -> None:
        theme = load_theme()
        super().__init__(master, bg=theme.color("Gray3"))
        self._theme = theme
        self._presenter = presenter
        self._user_id = user_id
        self._on_close_cb = on_close
        self._borderless = borderless
        self._page = 0
        self._has_next = False
        self._current_filter = "DEFAULT"
        self._last_items: list[dict[str, Any]] = []
        self._logs: Optional[LogsDialog] = None
        self._loading: Optional[LoadingCanvas] = None
        self._move_anchor: tuple[int, int] | None = None

        self._search_text = tk.StringVar()

        self._build_header()
        self._build_body()
        self._build_footer()

        self._status_bar.set("Ready")
        self.after_idle(self.refresh_list)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_header(self) -> None:
        theme = self._theme
        header = tk.Frame(self, bg=theme.color("Gray2"), bd=0, height=60)
        header.pack(fill=tk.X, side=tk.TOP)
        header.grid_propagate(False)
        header.pack_propagate(False)
        for col, weight in enumerate((0, 1, 0, 0, 0)):
            header.grid_columnconfigure(col, weight=weight)
        header.grid_rowconfigure(0, weight=1)

        # Drag-to-move on the borderless window: bind the empty parts of
        # the header (and the search entry) so the user can grab almost
        # anywhere to drag the window.
        if self._borderless:
            header.bind("<ButtonPress-1>", self._start_move)
            header.bind("<B1-Motion>", self._do_move)

        self._menu_button = IconMenuButton(
            header,
            icon_name="menu.png",
            icon_size=(30, 30),
            fallback_text="\u2630",
            entries=[
                (entry.label, entry.color, self._menu_command_for(entry.action))
                for entry in theme.menu_options
            ],
        )
        self._menu_button.grid(row=0, column=0, padx=(14, 6), pady=10)

        entry_frame = tk.Frame(header, bg=theme.color("Gray2"))
        entry_frame.grid(row=0, column=1, sticky=tk.NSEW, pady=10, padx=4)
        self._search_entry = EntryWithPlaceholder(
            entry_frame,
            placeholder="Search...",
            placeholder_color=theme.color("Gray"),
            textvariable=self._search_text,
            bd=0,
            bg=theme.color("Gray2"),
            fg=theme.color("White"),
            insertbackground=theme.color("White"),
            highlightthickness=1,
            highlightbackground=theme.color("Gray4"),
            highlightcolor=theme.color("Blue"),
            font=resolve_font(14),
        )
        self._search_entry.pack(fill=tk.BOTH, expand=True, ipady=6, padx=4)
        self._search_entry.bind("<Return>", lambda _e: self.search())
        if self._borderless:
            self._search_entry.bind("<ButtonPress-3>", self._start_move)
            self._search_entry.bind("<B3-Motion>", self._do_move)

        self._loading = LoadingCanvas(header, background=theme.color("Gray2"))
        self._loading.grid(row=0, column=2, padx=4, pady=6)

        self._filter_button = IconMenuButton(
            header,
            icon_name="filter.png",
            icon_size=(35, 35),
            fallback_text="\u25BD",
            entries=[
                (entry.label, entry.color, self._filter_command_for(entry.filter))
                for entry in theme.filter_options
            ],
        )
        self._filter_button.grid(row=0, column=3, padx=(4, 4), pady=10)

        self._close_button = make_icon_button(
            header,
            icon_name="close.png",
            icon_size=(40, 40),
            fallback_text="\u2715",
            command=self._handle_close,
        )
        self._close_button.grid(row=0, column=4, padx=(4, 14), pady=10)

    def _build_body(self) -> None:
        body = tk.Frame(self, bg=self._theme.color("Gray3"))
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 8))

        self._grid = AnimeGrid(
            body,
            on_left_click=self.open_details,
            on_right_click=self.open_torrent_dialog,
            run_async=self._run_async,
            columns=int(self._theme.window.get("anime_per_row", 4)),
        )
        self._grid.pack(fill=tk.BOTH, expand=True)

    def _build_footer(self) -> None:
        theme = self._theme
        footer = tk.Frame(self, bg=theme.color("Gray2"), bd=0)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        nav = tk.Frame(footer, bg=theme.color("Gray2"))
        nav.pack(fill=tk.X, padx=10, pady=6)

        def nav_btn(text: str, command: Callable[[], None]) -> tk.Button:
            btn = tk.Button(
                nav,
                text=text,
                command=command,
                bd=0,
                bg=theme.color("Gray2"),
                fg=theme.color("White"),
                activebackground=theme.color("Gray4"),
                activeforeground=theme.color("White"),
                font=resolve_font(12, "bold"),
                padx=10,
                pady=4,
                cursor="hand2",
            )
            return btn

        nav_btn("\u25C0 Previous", self.prev_page).pack(side=tk.LEFT)
        nav_btn("Reload", self.refresh_list).pack(side=tk.LEFT, padx=6)
        nav_btn("Next \u25B6", self.next_page).pack(side=tk.LEFT)

        self._page_var = tk.StringVar(value="Page 1")
        tk.Label(
            nav,
            textvariable=self._page_var,
            bg=theme.color("Gray2"),
            fg=theme.color("Gray"),
            font=resolve_font(12),
        ).pack(side=tk.LEFT, padx=14)

        self._filter_label_var = tk.StringVar(value="Filter: No filter")
        tk.Label(
            nav,
            textvariable=self._filter_label_var,
            bg=theme.color("Gray2"),
            fg=theme.color("White"),
            font=resolve_font(12),
        ).pack(side=tk.RIGHT)

        self._status_bar = StatusBar(footer)
        self._status_bar.pack(fill=tk.X)

    # ------------------------------------------------------------------
    # Window move (borderless)
    # ------------------------------------------------------------------

    def _start_move(self, event: tk.Event) -> None:
        self._move_anchor = (event.x_root, event.y_root)

    def _do_move(self, event: tk.Event) -> None:
        if self._move_anchor is None:
            return
        dx = event.x_root - self._move_anchor[0]
        dy = event.y_root - self._move_anchor[1]
        toplevel = self.winfo_toplevel()
        try:
            x = toplevel.winfo_x() + dx
            y = toplevel.winfo_y() + dy
            toplevel.geometry(f"+{x}+{y}")
        except tk.TclError:
            return
        self._move_anchor = (event.x_root, event.y_root)

    # ------------------------------------------------------------------
    # Status / loading helpers
    # ------------------------------------------------------------------

    def set_status(self, text: str) -> None:
        self._status_bar.set(text)

    def _begin_loading(self, status: str) -> None:
        self.set_status(status)
        if self._loading is not None:
            self._loading.start()

    def _end_loading(self) -> None:
        if self._loading is not None:
            self._loading.stop()

    def _run_async(self, worker, on_success, on_error) -> None:
        """Submit a callable on the presenter's runner (used by AnimeGrid)."""
        # Reuse the presenter's runner via a public attribute - falls
        # back to running inline if the presenter has no runner exposed.
        runner = getattr(self._presenter, "_runner", None)
        if runner is None:
            try:
                on_success(worker())
            except Exception as exc:
                on_error(exc)
            return
        runner.submit(worker, on_success=on_success, on_error=on_error)

    # ------------------------------------------------------------------
    # Menu / filter command bindings
    # ------------------------------------------------------------------

    def _menu_command_for(self, action: str) -> Callable[[], None]:
        mapping: dict[str, Callable[[], None]] = {
            "characters": self.open_characters_disks,
            "disks": self.open_characters_disks,
            "logs": self.open_logs,
            "clear_logs": self._clear_logs,
            "clear_cache": self._clear_cache,
            "settings": self.open_settings,
            "reload": self.refresh_list,
            "exit": self._handle_close,
        }
        return mapping.get(action, lambda: None)

    def _filter_command_for(self, filter_name: str) -> Callable[[], None]:
        def run() -> None:
            if filter_name == "SEASON":
                self.open_seasons()
                return
            self._current_filter = filter_name
            label = {entry.filter: entry.label for entry in self._theme.filter_options}.get(
                filter_name, filter_name.title()
            )
            self._filter_label_var.set(f"Filter: {label}")
            self._page = 0
            self._search_text.set("")
            self.refresh_list()
        return run

    # ------------------------------------------------------------------
    # Workflows
    # ------------------------------------------------------------------

    def refresh_list(self) -> None:
        self._page_var.set(f"Page {self._page + 1}")
        self._begin_loading("Loading anime list...")
        self._presenter.load_list(
            filter_name=self._current_filter,
            page=self._page,
            hide_rated=None,
            on_result=self._render_page,
            on_error=self._error,
        )

    def search(self) -> None:
        query = self._search_text.get().strip()
        if len(query) < 3:
            if self._search_entry.is_placeholder_visible() or not query:
                self.refresh_list()
            else:
                self.set_status("Type at least 3 characters to search")
            return
        self._begin_loading(f"Searching '{query}'...")
        self._presenter.search(
            query=query,
            limit=250,
            on_result=self._render_search,
            on_error=self._error,
        )

    def _render_page(self, payload: dict[str, Any]) -> None:
        items = list(payload.get("items", []))
        self._has_next = bool(payload.get("has_next"))
        self._last_items = items
        self._grid.set_rows(items)
        self._end_loading()
        self.set_status(f"Loaded {len(items)} anime entries")

    def _render_search(self, rows: list[dict[str, Any]]) -> None:
        self._has_next = False
        self._last_items = list(rows)
        self._grid.set_rows(rows)
        self._end_loading()
        self.set_status(f"Search returned {len(rows)} entries")

    def next_page(self) -> None:
        if not self._has_next and self._last_items:
            self.set_status("No next page")
            return
        self._page += 1
        self.refresh_list()

    def prev_page(self) -> None:
        if self._page == 0:
            return
        self._page -= 1
        self.refresh_list()

    # ------------------------------------------------------------------
    # Dialog routing
    # ------------------------------------------------------------------

    def _find_row(self, anime_id: int) -> Optional[dict[str, Any]]:
        for row in self._last_items:
            try:
                if int(row.get("id", -1)) == anime_id:
                    return row
            except (TypeError, ValueError):
                continue
        return None

    def open_details(self, anime: dict[str, Any]) -> None:
        anime_id = anime.get("id")
        if anime_id is None:
            return
        cached = self._find_row(int(anime_id))
        target = cached if (cached and cached.get("synopsis")) else None
        if target is None:
            self._begin_loading(f"Loading anime #{anime_id}...")
            self._presenter.get_anime(
                int(anime_id),
                on_result=self._show_details_dialog,
                on_error=self._error,
            )
            return
        self._show_details_dialog(target)

    def _show_details_dialog(self, anime: dict[str, Any]) -> None:
        self._end_loading()
        AnimeDetailsDialog(
            self,
            self._presenter,
            anime,
            user_id=self._user_id,
            on_refresh=self.refresh_list,
            open_torrent_dialog=self.open_torrent_dialog,
            open_search_terms_dialog=self.open_search_terms,
            open_relations_dialog=self.open_relations,
        )

    def open_torrent_dialog(self, anime: dict[str, Any]) -> None:
        TorrentDownloadDialog(self, self._presenter, anime)

    def open_search_terms(self, anime: dict[str, Any]) -> None:
        SearchTermsDialog(self, self._presenter, anime)

    def open_relations(self, anime: dict[str, Any]) -> None:
        RelationsDialog(self, self._presenter, anime)

    def open_settings(self) -> None:
        SettingsDialog(self, self._presenter)

    def open_seasons(self) -> None:
        SeasonSelectorDialog(self, on_search=self._apply_season_query)

    def _apply_season_query(self, query: str) -> None:
        self._search_text.set(query)
        self.search()

    def open_characters_disks(self) -> None:
        CharactersDisksDialog(self)

    def open_logs(self) -> None:
        if self._logs is None or not self._logs.winfo_exists():
            self._logs = LogsDialog(self)
        else:
            self._logs.lift()

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    def _clear_logs(self) -> None:
        if self._logs is not None and self._logs.winfo_exists():
            self._logs.clear()
        self.set_status("Logs cleared")

    def _clear_cache(self) -> None:
        self.set_status("Cache clear requested")

    def _handle_close(self) -> None:
        if self._on_close_cb is not None:
            self._on_close_cb()
            return
        try:
            self.winfo_toplevel().destroy()
        except tk.TclError:
            pass

    def _error(self, exc: Exception) -> None:
        self._end_loading()
        self.set_status(f"Error: {exc}")
        try:
            messagebox.showerror("AnimeManager", str(exc), parent=self)
        except tk.TclError:
            pass
