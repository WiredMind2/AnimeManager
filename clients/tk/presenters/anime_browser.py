"""Presenter for legacy-parity Tk workflows."""

from __future__ import annotations

from typing import Any, Callable

from clients.sdk import ClientSDK

from .async_runner import TkAsyncRunner


class AnimeBrowserPresenter:
    """Coordinates the Tk views while keeping SDK as the only boundary."""

    def __init__(
        self,
        sdk: ClientSDK,
        runner: TkAsyncRunner,
        *,
        status_cb: Callable[[str], None],
    ) -> None:
        self._sdk = sdk
        self._runner = runner
        self._status_cb = status_cb
        self._page_size = 50

    def load_list(
        self,
        *,
        filter_name: str,
        page: int,
        hide_rated: bool | None,
        on_result: Callable[[dict[str, Any]], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        list_start = max(0, page) * self._page_size
        list_stop = list_start + self._page_size
        self._status_cb("Loading anime list...")
        self._runner.submit(
            self._sdk.get_anime_list,
            filter_name=filter_name,
            list_start=list_start,
            list_stop=list_stop,
            hide_rated=hide_rated,
            on_success=lambda payload: self._finish("List loaded", on_result, payload),
            on_error=lambda exc: self._fail("List load failed", on_error, exc),
        )

    def search(
        self,
        *,
        query: str,
        limit: int,
        on_result: Callable[[dict[str, Any]], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._status_cb("Searching anime...")
        self._runner.submit(
            self._sdk.search_anime,
            query=query,
            limit=limit,
            on_success=lambda payload: self._finish(
                "Search completed",
                on_result,
                payload
                if isinstance(payload, dict)
                else {"items": list(payload or []), "has_next": False},
            ),
            on_error=lambda exc: self._fail("Search failed", on_error, exc),
        )

    def get_anime(
        self,
        anime_id: int,
        *,
        on_result: Callable[[dict[str, Any]], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._status_cb(f"Loading anime #{anime_id}...")
        self._runner.submit(
            self._sdk.get_anime,
            anime_id,
            on_success=lambda anime: self._finish("Anime details ready", on_result, anime),
            on_error=lambda exc: self._fail("Anime details failed", on_error, exc),
        )

    def search_torrents(
        self,
        *,
        terms: list[str],
        profile: str,
        limit: int,
        on_result: Callable[[list[dict[str, Any]]], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._status_cb("Searching torrents...")
        self._runner.submit(
            self._sdk.search_torrents,
            terms=terms,
            profile=profile,
            limit=limit,
            on_success=lambda rows: self._finish("Torrent search completed", on_result, rows),
            on_error=lambda exc: self._fail("Torrent search failed", on_error, exc),
        )

    def start_download(
        self,
        *,
        anime_id: int,
        url: str | None = None,
        hash_value: str | None = None,
        on_result: Callable[[bool], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._status_cb("Starting download...")
        self._runner.submit(
            self._sdk.start_download,
            anime_id,
            url=url,
            hash_value=hash_value,
            on_success=lambda started: self._finish(
                "Download started" if started else "Download not started",
                on_result,
                started,
            ),
            on_error=lambda exc: self._fail("Download failed", on_error, exc),
        )

    def cancel_download(
        self,
        anime_id: int,
        *,
        on_result: Callable[[bool], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._status_cb("Cancelling download...")
        self._runner.submit(
            self._sdk.cancel_download,
            anime_id,
            on_success=lambda cancelled: self._finish(
                "Download cancelled" if cancelled else "No active download",
                on_result,
                cancelled,
            ),
            on_error=lambda exc: self._fail("Cancel failed", on_error, exc),
        )

    def get_download_progress(
        self,
        anime_id: int,
        *,
        on_result: Callable[[dict[str, Any]], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._runner.submit(
            self._sdk.get_download_progress,
            anime_id,
            on_success=on_result,
            on_error=on_error,
        )

    def set_tag(
        self,
        anime_id: int,
        tag: str,
        user_id: int,
        *,
        on_done: Callable[[], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._status_cb(f"Tagging as {tag}...")
        self._runner.submit(
            self._sdk.set_tag,
            anime_id,
            tag,
            user_id,
            on_success=lambda _out: self._finish("Tag updated", lambda _r: on_done(), None),
            on_error=lambda exc: self._fail("Tag update failed", on_error, exc),
        )

    def set_like(
        self,
        anime_id: int,
        user_id: int,
        liked: bool,
        *,
        on_done: Callable[[], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._status_cb("Updating like status...")
        self._runner.submit(
            self._sdk.set_like,
            anime_id,
            user_id=user_id,
            liked=liked,
            on_success=lambda _out: self._finish("Like updated", lambda _r: on_done(), None),
            on_error=lambda exc: self._fail("Like update failed", on_error, exc),
        )

    def mark_seen(
        self,
        anime_id: int,
        file_name: str,
        user_id: int,
        *,
        on_done: Callable[[], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._status_cb("Marking as seen...")
        self._runner.submit(
            self._sdk.mark_seen,
            anime_id,
            file_name,
            user_id,
            on_success=lambda _out: self._finish("Marked as seen", lambda _r: on_done(), None),
            on_error=lambda exc: self._fail("Mark seen failed", on_error, exc),
        )

    def get_search_terms(
        self,
        anime_id: int,
        *,
        on_result: Callable[[list[str]], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._runner.submit(
            self._sdk.get_search_terms,
            anime_id,
            on_success=on_result,
            on_error=on_error,
        )

    def add_search_term(
        self,
        anime_id: int,
        term: str,
        *,
        on_result: Callable[[bool], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._runner.submit(
            self._sdk.add_search_term,
            anime_id,
            term,
            on_success=on_result,
            on_error=on_error,
        )

    def remove_search_term(
        self,
        anime_id: int,
        term: str,
        *,
        on_result: Callable[[bool], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._runner.submit(
            self._sdk.remove_search_term,
            anime_id,
            term,
            on_success=on_result,
            on_error=on_error,
        )

    def get_settings(
        self,
        *,
        on_result: Callable[[dict[str, Any]], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._runner.submit(
            self._sdk.get_settings,
            on_success=on_result,
            on_error=on_error,
        )

    def update_settings(
        self,
        updates: dict[str, Any],
        *,
        on_result: Callable[[dict[str, Any]], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._status_cb("Saving settings...")
        self._runner.submit(
            self._sdk.update_settings,
            updates,
            on_success=lambda payload: self._finish("Settings saved", on_result, payload),
            on_error=lambda exc: self._fail("Settings save failed", on_error, exc),
        )

    def get_relations(
        self,
        anime_id: int,
        *,
        on_result: Callable[[list[dict[str, Any]]], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._runner.submit(
            self._sdk.get_relations,
            anime_id,
            on_success=on_result,
            on_error=on_error,
        )

    def _finish(self, status: str, callback: Callable[[Any], None], value: Any) -> None:
        self._status_cb(status)
        callback(value)

    def _fail(
        self,
        status: str,
        callback: Callable[[Exception], None],
        exc: Exception,
    ) -> None:
        self._status_cb(status)
        callback(exc)
