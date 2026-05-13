"""Search-bar Entry with built-in placeholder text.

Direct successor of the legacy ``menu_components.EntryWithPlaceholder``.
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional


class EntryWithPlaceholder(tk.Entry):
    """A regular Entry that shows greyed-out placeholder text when empty."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        placeholder: str = "",
        placeholder_color: str = "#676760",
        textvariable: Optional[tk.StringVar] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, textvariable=textvariable, **kwargs)
        self._placeholder = placeholder
        self._placeholder_color = placeholder_color
        self._default_fg = str(self["fg"]) or "#F0F0FF"
        self._textvariable = textvariable
        self._showing_placeholder = False
        self._suppress_trace = False
        if self._textvariable is not None:
            try:
                self._textvariable.trace_add("write", self._on_variable_write)
            except (AttributeError, tk.TclError):
                pass
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Key>", self._on_user_input, add="+")
        self._show_placeholder_if_empty()

    def _show_placeholder_if_empty(self) -> None:
        current = self._current_text()
        if not current:
            self._render_placeholder()

    def _current_text(self) -> str:
        if self._textvariable is not None:
            return self._textvariable.get()
        return super().get()

    def _render_placeholder(self) -> None:
        self._suppress_trace = True
        try:
            self.delete(0, tk.END)
            super().insert(0, self._placeholder)
            self.configure(fg=self._placeholder_color)
            self._showing_placeholder = True
        finally:
            self._suppress_trace = False

    def _clear_placeholder(self) -> None:
        if self._showing_placeholder:
            self._suppress_trace = True
            try:
                self.delete(0, tk.END)
                self.configure(fg=self._default_fg)
                self._showing_placeholder = False
            finally:
                self._suppress_trace = False

    def _on_variable_write(self, *_args) -> None:
        """Detect external textvariable changes so ``get()`` stays honest."""
        if self._suppress_trace or self._textvariable is None:
            return
        current = self._textvariable.get()
        if self._showing_placeholder:
            if current and current != self._placeholder:
                self._showing_placeholder = False
                try:
                    self.configure(fg=self._default_fg)
                except tk.TclError:
                    pass
        elif not current:
            try:
                if self.focus_get() is not self:
                    self._render_placeholder()
            except (tk.TclError, KeyError):
                self._render_placeholder()

    def _on_focus_in(self, _event: tk.Event) -> None:
        self._clear_placeholder()

    def _on_focus_out(self, _event: tk.Event) -> None:
        if not self._current_text():
            self._render_placeholder()

    def _on_user_input(self, _event: tk.Event) -> None:
        if self._showing_placeholder:
            self._clear_placeholder()

    def get(self) -> str:  # type: ignore[override]
        if self._showing_placeholder:
            return ""
        return super().get()

    def is_placeholder_visible(self) -> bool:
        return self._showing_placeholder


__all__ = ["EntryWithPlaceholder"]
