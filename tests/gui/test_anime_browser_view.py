"""End-to-end render test of the dark-themed AnimeBrowserView."""

from __future__ import annotations

import tkinter as tk

import pytest

from clients.tk.presenters.anime_browser import AnimeBrowserPresenter
from clients.tk.views import AnimeBrowserView


class _InlineRunner:
    def submit(self, func, *args, on_success=None, on_error=None, **kwargs):
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            if on_error:
                on_error(exc)
            return
        if on_success:
            on_success(result)


class _FakeSDK:
    def __init__(self):
        self.calls: dict[str, int] = {}
        self.list_payload = {
            "items": [
                {"id": 1, "title": "Cowboy Bebop", "tag": "SEEN", "liked": True},
                {"id": 2, "title": "Trigun", "tag": "WATCHING"},
                {"id": 3, "title": "Berserk", "tag": "NONE"},
            ],
            "has_next": False,
        }

    def get_anime_list(self, **kwargs):
        self.calls["get_anime_list"] = self.calls.get("get_anime_list", 0) + 1
        return self.list_payload

    def search_anime(self, query: str, limit: int = 50):
        self.calls["search_anime"] = self.calls.get("search_anime", 0) + 1
        return [{"id": 99, "title": f"{query} result"}]

    def get_anime(self, anime_id: int):
        return {"id": anime_id, "title": "Loaded"}


def test_browser_view_renders_initial_list(tk_root):
    presenter = AnimeBrowserPresenter(
        sdk=_FakeSDK(),
        runner=_InlineRunner(),
        status_cb=lambda _msg: None,
    )
    view = AnimeBrowserView(tk_root, presenter, borderless=False)
    view.pack()
    tk_root.update_idletasks()
    # ``after_idle`` schedules the initial load; flush queued tasks
    tk_root.update()
    assert len(view._grid._cards) == 3
    titles = [card.label.cget("text") for card in view._grid._cards]
    assert any("Cowboy Bebop" in t for t in titles)
    # Liked entry should carry the heart suffix
    assert any("\u2764" in t for t in titles)
    view.destroy()


def test_search_callback_renders_results(tk_root):
    presenter = AnimeBrowserPresenter(
        sdk=_FakeSDK(),
        runner=_InlineRunner(),
        status_cb=lambda _msg: None,
    )
    view = AnimeBrowserView(tk_root, presenter, borderless=False)
    view.pack()
    tk_root.update_idletasks()
    tk_root.update()
    view._search_text.set("naruto")
    view.search()
    tk_root.update_idletasks()
    assert len(view._grid._cards) == 1
    assert "naruto" in view._grid._cards[0].label.cget("text").lower()
    view.destroy()


def test_filter_command_triggers_reload(tk_root):
    sdk = _FakeSDK()
    presenter = AnimeBrowserPresenter(
        sdk=sdk,
        runner=_InlineRunner(),
        status_cb=lambda _msg: None,
    )
    view = AnimeBrowserView(tk_root, presenter, borderless=False)
    view.pack()
    tk_root.update_idletasks()
    tk_root.update()
    initial_calls = sdk.calls.get("get_anime_list", 0)
    view._filter_command_for("WATCHING")()
    tk_root.update_idletasks()
    assert sdk.calls["get_anime_list"] >= initial_calls + 1
    assert view._current_filter == "WATCHING"
    assert "Watching" in view._filter_label_var.get()
    view.destroy()
