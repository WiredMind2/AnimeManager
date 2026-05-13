"""Anime details and actions dialog (dark themed)."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from datetime import datetime, timezone
from tkinter import messagebox, ttk
from typing import Any, Callable, Iterable

from clients.tk.presenters import AnimeBrowserPresenter
from clients.tk.theme import apply_dark_theme, load_theme, resolve_font


_WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def _format_date(value: Any) -> str | None:
    """Format a stored date (Unix timestamp or ISO string) as ``DD MMM YYYY``."""
    if value is None or value == "":
        return None
    try:
        ts = int(value)
    except (TypeError, ValueError):
        text = str(value).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text).strftime("%d %b %Y")
        except ValueError:
            return text
    try:
        return datetime.fromtimestamp(ts, timezone.utc).strftime("%d %b %Y")
    except (OverflowError, OSError, ValueError):
        return None


def _format_aired(date_from: Any, date_to: Any) -> str:
    """Combine ``date_from``/``date_to`` into a human-readable range."""
    start = _format_date(date_from)
    end = _format_date(date_to)
    if start and end and start != end:
        return f"{start} \u2192 {end}"
    if start and end:
        return start
    if start:
        return f"{start} \u2192 ?"
    if end:
        return f"? \u2192 {end}"
    return "Unknown"


def _format_duration(value: Any) -> str:
    """Render a per-episode duration (minutes) as ``X min`` / ``Xh Ym``."""
    if value is None or value == "":
        return "Unknown"
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return str(value)
    if minutes <= 0:
        return "Unknown"
    if minutes < 60:
        return f"{minutes} min"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m" if mins else f"{hours}h"


def _format_broadcast(value: Any) -> str | None:
    """Render a ``weekday-hour-minute`` broadcast slot in plain English."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    parts = text.split("-")
    if len(parts) != 3:
        return text
    try:
        weekday, hour, minute = (int(p) for p in parts)
    except ValueError:
        return text
    if not 0 <= weekday < 7:
        return text
    return f"{_WEEKDAY_NAMES[weekday]} {hour:02d}:{minute:02d}"


def _join_list(values: Any, limit: int | None = None) -> str | None:
    """Render a list-like metadata field as a comma-separated string."""
    if values is None:
        return None
    if isinstance(values, str):
        text = values.strip()
        return text or None
    if not isinstance(values, Iterable):
        return str(values)
    items = [str(item).strip() for item in values if str(item).strip()]
    if not items:
        return None
    if limit is not None and len(items) > limit:
        extra = len(items) - limit
        return ", ".join(items[:limit]) + f", +{extra} more"
    return ", ".join(items)


class AnimeDetailsDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        presenter: AnimeBrowserPresenter,
        anime: dict[str, Any],
        *,
        user_id: int,
        on_refresh: Callable[[], None],
        open_torrent_dialog: Callable[[dict[str, Any]], None],
        open_search_terms_dialog: Callable[[dict[str, Any]], None],
        open_relations_dialog: Callable[[dict[str, Any]], None],
    ) -> None:
        super().__init__(master)
        self.title(f"Details - {anime.get('title', 'Anime')}")
        self.geometry("960x620")
        apply_dark_theme(self)
        self._theme = load_theme()
        self._presenter = presenter
        self._anime = anime
        self._user_id = user_id
        self._on_refresh = on_refresh
        self._open_torrent_dialog = open_torrent_dialog
        self._open_search_terms_dialog = open_search_terms_dialog
        self._open_relations_dialog = open_relations_dialog

        self._status = tk.StringVar(value="Ready")
        self._seen_file = tk.StringVar(value=anime.get("last_seen") or "manual")
        self._tag = tk.StringVar(value=anime.get("tag") or "NONE")
        self._liked = tk.BooleanVar(value=bool(anime.get("liked")))

        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self, style="AnimeManager.TFrame")
        top.pack(fill=tk.X, padx=14, pady=14)

        title = self._anime.get("title", "")
        ttk.Label(
            top,
            text=title,
            style="AnimeManager.Header.TLabel",
            font=resolve_font(16, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(
            top,
            text=f"ID: {self._anime.get('id')}",
            style="AnimeManager.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            top,
            text=(
                f"Status: {self._anime.get('status') or 'Unknown'}    "
                f"Episodes: {self._anime.get('episodes') or '?'}    "
                f"Rating: {self._anime.get('rating') or 'N/A'}"
            ),
            style="AnimeManager.TLabel",
        ).pack(anchor=tk.W, pady=(2, 8))

        row = ttk.Frame(top, style="AnimeManager.TFrame")
        row.pack(fill=tk.X)
        ttk.Label(row, text="Tag", style="AnimeManager.TLabel").pack(side=tk.LEFT)
        ttk.Combobox(
            row,
            textvariable=self._tag,
            values=("NONE", "WATCHLIST", "WATCHING", "SEEN"),
            state="readonly",
            width=14,
            style="AnimeManager.TCombobox",
        ).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Checkbutton(
            row,
            text="Liked",
            variable=self._liked,
            style="AnimeManager.TCheckbutton",
        ).pack(side=tk.LEFT)
        ttk.Button(
            row,
            text="Save Tag/Like",
            command=self._save_state,
            style="AnimeManager.TButton",
        ).pack(side=tk.LEFT, padx=(12, 0))

        seen = ttk.Frame(top, style="AnimeManager.TFrame")
        seen.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(seen, text="Seen file", style="AnimeManager.TLabel").pack(side=tk.LEFT)
        ttk.Entry(
            seen,
            textvariable=self._seen_file,
            style="AnimeManager.TEntry",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(
            seen,
            text="Mark Seen",
            command=self._mark_seen,
            style="AnimeManager.TButton",
        ).pack(side=tk.LEFT)

        actions = ttk.Frame(top, style="AnimeManager.TFrame")
        actions.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(
            actions,
            text="Torrent Search / Download",
            command=lambda: self._open_torrent_dialog(self._anime),
            style="AnimeManager.TButton",
        ).pack(side=tk.LEFT)
        ttk.Button(
            actions,
            text="Search Terms",
            command=lambda: self._open_search_terms_dialog(self._anime),
            style="AnimeManager.TButton",
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            actions,
            text="Relations",
            command=lambda: self._open_relations_dialog(self._anime),
            style="AnimeManager.TButton",
        ).pack(side=tk.LEFT)

        self._build_metadata(top)

        body = ttk.Frame(self, style="AnimeManager.TFrame")
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))
        synopsis = tk.Text(
            body,
            wrap=tk.WORD,
            height=18,
            bg=self._theme.color("Gray2"),
            fg=self._theme.color("White"),
            insertbackground=self._theme.color("White"),
            bd=0,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self._theme.color("Gray4"),
            font=resolve_font(12),
            padx=10,
            pady=8,
        )
        synopsis.insert("1.0", self._anime.get("synopsis") or "No synopsis.")
        synopsis.configure(state=tk.DISABLED)
        synopsis.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            self,
            textvariable=self._status,
            anchor=tk.W,
            style="AnimeManager.Status.TLabel",
        ).pack(fill=tk.X, padx=14, pady=(0, 12))

    def _build_metadata(self, parent: ttk.Frame) -> None:
        """Render a two-column grid of additional anime metadata."""
        anime = self._anime

        rows: list[tuple[str, str | None, str | None]] = [
            ("Aired", _format_aired(anime.get("date_from"), anime.get("date_to")), None),
            ("Duration", _format_duration(anime.get("duration")), None),
            ("Broadcast", _format_broadcast(anime.get("broadcast")), None),
            ("Genres", _join_list(anime.get("genres")), None),
            ("Synonyms", _join_list(anime.get("title_synonyms"), limit=4), None),
            ("Last seen", anime.get("last_seen") or None, None),
        ]

        trailer = anime.get("trailer")
        if isinstance(trailer, str) and trailer.strip():
            rows.append(("Trailer", trailer.strip(), trailer.strip()))

        rows = [row for row in rows if row[1]]
        if not rows:
            return

        meta = ttk.Frame(parent, style="AnimeManager.TFrame")
        meta.pack(fill=tk.X, pady=(10, 0))
        meta.columnconfigure(1, weight=1)
        meta.columnconfigure(3, weight=1)

        label_font = resolve_font(11, "bold")
        value_font = resolve_font(11)
        muted = self._theme.color("Gray")
        accent = self._theme.color("Blue")
        fg = self._theme.color("White")

        for index, (label, value, link) in enumerate(rows):
            row, col = divmod(index, 2)
            base_col = col * 2
            tk.Label(
                meta,
                text=f"{label}:",
                font=label_font,
                bg=self._theme.color("Gray3"),
                fg=muted,
                anchor="w",
            ).grid(row=row, column=base_col, sticky="w", padx=(0, 6), pady=2)

            value_widget = tk.Label(
                meta,
                text=value,
                font=value_font,
                bg=self._theme.color("Gray3"),
                fg=accent if link else fg,
                anchor="w",
                justify=tk.LEFT,
                wraplength=380,
                cursor="hand2" if link else "",
            )
            value_widget.grid(
                row=row,
                column=base_col + 1,
                sticky="ew",
                padx=(0, 18),
                pady=2,
            )
            if link:
                value_widget.bind(
                    "<Button-1>",
                    lambda _event, url=link: self._open_link(url),
                )

    def _open_link(self, url: str) -> None:
        """Open a trailer / external URL in the user's default browser."""
        try:
            webbrowser.open(url, new=2)
        except Exception as exc:  # pragma: no cover - defensive UI guard
            self._status.set(f"Failed to open link: {exc}")

    def _save_state(self) -> None:
        anime_id = int(self._anime["id"])
        tag = self._tag.get().strip() or "NONE"
        liked = self._liked.get()
        self._status.set("Saving...")
        self._presenter.set_tag(
            anime_id,
            tag,
            self._user_id,
            on_done=lambda: self._presenter.set_like(
                anime_id,
                self._user_id,
                liked,
                on_done=self._saved,
                on_error=self._error,
            ),
            on_error=self._error,
        )

    def _mark_seen(self) -> None:
        anime_id = int(self._anime["id"])
        file_name = self._seen_file.get().strip() or "manual"
        self._status.set("Updating seen state...")
        self._presenter.mark_seen(
            anime_id,
            file_name,
            self._user_id,
            on_done=self._saved,
            on_error=self._error,
        )

    def _saved(self) -> None:
        self._status.set("Saved")
        self._on_refresh()

    def _error(self, exc: Exception) -> None:
        self._status.set(f"Error: {exc}")
        messagebox.showerror("AnimeManager", str(exc), parent=self)
