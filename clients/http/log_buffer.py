"""In-memory log buffer for the live web UI log viewer.

This module defines a thread-safe ring buffer of recent
:class:`logging.LogRecord` payloads plus a custom
:class:`logging.Handler` that pushes records into it. SSE clients
subscribe via :func:`LogBuffer.subscribe` to receive a queue of new
records in real time.

Design notes
------------
* Records are normalized into plain dicts at capture time so the rest
  of the app (Jinja, JSON serializers, the SSE encoder) never has to
  introspect a ``LogRecord`` directly.
* The buffer is bounded (``maxlen=DEFAULT_BUFFER_SIZE``) so memory
  stays flat for long-running servers.
* Every record gets a monotonically increasing ``id`` so the JS client
  can resume / dedupe after a reconnect or tab refresh.
* Subscribers receive a :class:`queue.Queue` of payloads. When a
  subscriber falls behind (UI tab paused, network stall) the queue
  silently drops the oldest pending item so the live producer thread
  is never blocked by a slow consumer.
"""

from __future__ import annotations

import itertools
import logging
import queue
import re
import threading
import time
import traceback
from collections import deque
from typing import Any, Iterable, Iterator, Mapping

DEFAULT_BUFFER_SIZE = 2000
"""Maximum number of records kept in the ring buffer."""

DEFAULT_SUBSCRIBER_QUEUE = 500
"""Per-subscriber queue cap before old items are dropped."""

# Levels surfaced as filter choices in the UI. Matches stdlib ordering.
LEVEL_NAMES: tuple[str, ...] = (
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
)

# Canonical list of categories the UI exposes as toggles. Records that
# resolve to a category outside this list are still captured (their
# category gets registered on the buffer's "observed" set) so users can
# disable them too. The first ten entries match the legacy Tk logger's
# category list verbatim; the rest are introduced with the web log
# viewer to give modern Python loggers a meaningful home.
KNOWN_CATEGORIES: tuple[str, ...] = (
    # Legacy categories (preserved from the Tk logger).
    "DB_ERROR",
    "DB_UPDATE",
    "DISK_ERROR",
    "MAIN_STATE",
    "NETWORK",
    "NETWORK_DATA",
    "SERVER",
    "SETTINGS",
    "THREAD",
    "TIME",
    # Modern categories introduced with the live web log viewer.
    "HTTP",
    "DOWNLOAD",
    "SEARCH",
    "STARTUP",
    "OTHER",
)

# Logger-name prefix -> category. The list is ordered: longer / more
# specific prefixes come first so they win over short generic ones.
# A ``"DB_UPDATE"`` mapping is *promoted* to ``"DB_ERROR"`` when the
# record's level is >= ERROR; same trick for ``"NETWORK"`` ->
# ``"NETWORK_DATA"`` would just confuse users so we don't do it there.
_LOGGER_PREFIX_MAP: tuple[tuple[str, str], ...] = (
    ("application.services.download_manager", "DOWNLOAD"),
    ("application.services.startup_jobs", "STARTUP"),
    ("application.services", "MAIN_STATE"),
    ("adapters.persistence", "DB_UPDATE"),
    ("adapters.api", "NETWORK"),
    ("adapters.file", "DISK_ERROR"),
    ("adapters.torrent", "DOWNLOAD"),
    ("adapters.search", "SEARCH"),
    ("clients.http", "HTTP"),
    ("clients.tk", "HTTP"),
    ("clients.sdk", "MAIN_STATE"),
    ("composition", "MAIN_STATE"),
    ("bootstrap", "STARTUP"),
    ("animemanager.bootstrap", "STARTUP"),
    ("animemanager", "MAIN_STATE"),
    ("uvicorn", "SERVER"),
    ("fastapi", "SERVER"),
    ("starlette", "SERVER"),
    ("hypercorn", "SERVER"),
    ("watchfiles", "SERVER"),
    ("asyncio", "THREAD"),
    ("concurrent.futures", "THREAD"),
    ("threading", "THREAD"),
    ("shared.config", "SETTINGS"),
)

# Legacy Tk logger format: ``[ CATEGORY ] - message``.
_LEGACY_BRACKET_RE = re.compile(r"^\[\s*([A-Z][A-Z0-9_]+)\s*\]\s*-\s*(.*)$")


def derive_category(payload: Mapping[str, Any]) -> str:
    """Classify a record into one of :data:`KNOWN_CATEGORIES` (or a
    custom category if the record carries one).

    Detection order:

    1. Legacy ``[CATEGORY]`` bracket prefix in the message (matches
       both the Tk logger output and any external module that follows
       the same convention).
    2. Logger-name prefix lookup against :data:`_LOGGER_PREFIX_MAP`.
    3. Fallback to ``"OTHER"``.
    """
    msg = str(payload.get("message") or "")
    m = _LEGACY_BRACKET_RE.match(msg)
    if m:
        return m.group(1)

    logger_name = str(payload.get("logger") or "").lower()
    levelno = int(payload.get("levelno") or 0)
    for prefix, category in _LOGGER_PREFIX_MAP:
        if logger_name == prefix or logger_name.startswith(prefix + "."):
            if category == "DB_UPDATE" and levelno >= logging.ERROR:
                return "DB_ERROR"
            return category
    return "OTHER"


def strip_legacy_bracket(message: str) -> tuple[str, str | None]:
    """Return ``(clean_message, category | None)``.

    When the message starts with a legacy ``[ CATEGORY ] -`` prefix
    the prefix is removed and the category returned alongside the
    clean text so the UI can render the category in its own column.
    """
    if not message:
        return message, None
    m = _LEGACY_BRACKET_RE.match(message)
    if not m:
        return message, None
    return m.group(2), m.group(1)


def _level_value(name: str | int | None, default: int = logging.NOTSET) -> int:
    """Best-effort coercion of a level filter to a numeric threshold."""
    if name is None or name == "":
        return default
    if isinstance(name, int):
        return name
    try:
        return int(name)
    except (TypeError, ValueError):
        pass
    upper = str(name).strip().upper()
    if not upper:
        return default
    candidate = logging.getLevelName(upper)
    if isinstance(candidate, int):
        return candidate
    return default


class LogBuffer:
    """Thread-safe ring buffer of recent log records with live fan-out.

    There is one process-wide instance exposed as
    :data:`global_buffer`. The instance is intentionally cheap to
    construct so tests can spin up isolated buffers without touching
    the global one.
    """

    def __init__(self, max_records: int = DEFAULT_BUFFER_SIZE) -> None:
        self._records: deque[dict[str, Any]] = deque(maxlen=max_records)
        self._lock = threading.RLock()
        self._counter = itertools.count(1)
        # ``WeakSet`` would be tempting here but we want the buffer to
        # keep subscribers alive for as long as the route handler holds
        # a reference; ``unsubscribe`` is called explicitly in the SSE
        # generator's ``finally`` block.
        self._subscribers: set[queue.Queue] = set()
        # Categories the user has switched off in settings. Records
        # whose derived category is in this set are dropped at capture
        # time so the buffer doesn't waste space on silenced channels.
        self._disabled_categories: set[str] = set()
        # Every category we've ever observed flowing through this
        # buffer. The settings UI joins this with KNOWN_CATEGORIES so
        # users can opt out of categories nobody anticipated.
        self._observed_categories: set[str] = set()

    # ------------------------------------------------------------------
    # Producer side
    # ------------------------------------------------------------------
    def add(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Append ``payload`` (an already-formatted record dict).

        Assigns the next monotonic ``id``, registers the record's
        category as observed, and broadcasts to subscribers. Returns
        the stored payload (with the assigned id) so callers can chain.

        If the record's ``category`` is currently disabled the record
        is dropped: ``None`` is returned and no subscriber is notified.
        """
        with self._lock:
            payload = dict(payload)
            payload.setdefault("ts", time.time())
            category = payload.get("category") or "OTHER"
            payload["category"] = category
            self._observed_categories.add(category)
            if category in self._disabled_categories:
                return None
            payload["id"] = next(self._counter)
            self._records.append(payload)
            subs = tuple(self._subscribers)

        # Fan-out happens outside the lock so subscriber callbacks
        # cannot deadlock the producer (e.g. by re-entering logging).
        for sub in subs:
            try:
                sub.put_nowait(payload)
            except queue.Full:
                # Slow consumer: discard the oldest pending entry and
                # retry once. If even that fails we just drop the new
                # one -- the live stream is best-effort by design.
                try:
                    sub.get_nowait()
                    sub.put_nowait(payload)
                except (queue.Empty, queue.Full):
                    pass
        return payload

    def clear(self) -> int:
        """Wipe the buffer. Returns the number of records dropped."""
        with self._lock:
            count = len(self._records)
            self._records.clear()
        return count

    # ------------------------------------------------------------------
    # Category management
    # ------------------------------------------------------------------
    def set_disabled_categories(self, values: Iterable[str] | None) -> set[str]:
        """Replace the set of categories that are dropped on capture.

        Pass ``None`` or an empty iterable to disable nothing (the
        default). Returns the new disabled set so callers can confirm
        what stuck.
        """
        if values is None:
            new_set: set[str] = set()
        else:
            new_set = {str(v).strip().upper() for v in values if str(v).strip()}
        with self._lock:
            self._disabled_categories = new_set
        return set(new_set)

    @property
    def disabled_categories(self) -> set[str]:
        with self._lock:
            return set(self._disabled_categories)

    def known_categories(self) -> list[str]:
        """Return :data:`KNOWN_CATEGORIES` plus any categories the
        buffer has actually seen at runtime, de-duplicated, with the
        canonical ordering preserved for known names and observed-only
        names sorted alphabetically at the end.
        """
        known = list(KNOWN_CATEGORIES)
        with self._lock:
            extras = sorted(self._observed_categories - set(KNOWN_CATEGORIES))
        return known + extras

    # ------------------------------------------------------------------
    # Consumer side
    # ------------------------------------------------------------------
    def snapshot(
        self,
        *,
        min_level: int = logging.NOTSET,
        logger_substr: str | None = None,
        text: str | None = None,
        categories: Iterable[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return the recent records that match the supplied filter.

        Filter semantics:

        * ``min_level`` - only records whose ``levelno`` is ``>=`` this.
        * ``logger_substr`` - case-insensitive substring match against
          the record's ``logger`` (logger name) and ``module``.
        * ``text`` - case-insensitive substring match against the
          formatted ``message`` and the truncated traceback (if any).
        * ``categories`` - whitelist of categories to surface. ``None``
          or an empty iterable accepts every category.
        * ``limit`` - last N matches (most recent).
        """
        with self._lock:
            records = list(self._records)
        cat_set = _normalize_category_set(categories)
        filtered = [
            r
            for r in records
            if _matches(r, min_level, logger_substr, text, cat_set)
        ]
        if limit is not None and limit > 0:
            filtered = filtered[-limit:]
        return filtered

    def latest_id(self) -> int:
        """Return the id of the most recently appended record (or 0)."""
        with self._lock:
            if not self._records:
                return 0
            return int(self._records[-1].get("id") or 0)

    def subscribe(self, maxsize: int = DEFAULT_SUBSCRIBER_QUEUE) -> queue.Queue:
        """Register a new subscriber and return its queue."""
        sub: queue.Queue = queue.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: queue.Queue) -> None:
        """Remove a previously registered subscriber."""
        with self._lock:
            self._subscribers.discard(sub)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


# ---------------------------------------------------------------------------
# Filtering helpers
# ---------------------------------------------------------------------------


def _normalize_category_set(values: Iterable[str] | None) -> set[str] | None:
    if not values:
        return None
    out = {str(v).strip().upper() for v in values if str(v).strip()}
    return out or None


def _matches(
    record: dict[str, Any],
    min_level: int,
    logger_substr: str | None,
    text: str | None,
    categories: set[str] | None = None,
) -> bool:
    if min_level and int(record.get("levelno") or 0) < min_level:
        return False
    if categories and str(record.get("category") or "").upper() not in categories:
        return False
    if logger_substr:
        needle = logger_substr.lower()
        haystack = (
            f"{record.get('logger') or ''}\n{record.get('module') or ''}"
        ).lower()
        if needle not in haystack:
            return False
    if text:
        needle = text.lower()
        haystack = (
            f"{record.get('message') or ''}\n{record.get('exc_info') or ''}"
        ).lower()
        if needle not in haystack:
            return False
    return True


def stream_filtered(
    sub: queue.Queue,
    *,
    min_level: int = logging.NOTSET,
    logger_substr: str | None = None,
    text: str | None = None,
    categories: Iterable[str] | None = None,
    timeout: float = 15.0,
) -> Iterator[dict[str, Any] | None]:
    """Yield filtered records from ``sub`` until the queue is closed.

    Yields ``None`` whenever ``timeout`` elapses without a match so
    the caller can emit an SSE heartbeat / check for disconnects.
    """
    cat_set = _normalize_category_set(categories)
    while True:
        try:
            record = sub.get(timeout=timeout)
        except queue.Empty:
            yield None
            continue
        if record is _SENTINEL:
            return
        if _matches(record, min_level, logger_substr, text, cat_set):
            yield record


_SENTINEL = object()


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class BufferingHandler(logging.Handler):
    """``logging.Handler`` that pushes formatted records into a buffer.

    The handler uses :meth:`logging.Handler.format` (with a fallback
    when no formatter is configured) so any user-supplied formatter on
    the root logger still wins for the *message* field. Structured
    metadata (logger name, levelno, module, etc.) is captured
    separately so the UI can colorize / filter on them.
    """

    def __init__(self, buffer: LogBuffer, level: int = logging.NOTSET) -> None:
        super().__init__(level=level)
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401 - stdlib protocol
        try:
            # ``getMessage`` returns the message text with ``%``-style
            # args substituted but *without* the traceback appendix that
            # ``Formatter.format`` would otherwise pin onto the end --
            # we surface the traceback separately in ``exc_info`` so the
            # UI can render it in its own block.
            try:
                message = record.getMessage()
            except Exception:  # noqa: BLE001
                message = str(record.msg)

            exc_text: str | None = None
            if record.exc_info:
                try:
                    exc_text = "".join(
                        traceback.format_exception(*record.exc_info)
                    ).rstrip()
                except Exception:  # noqa: BLE001
                    exc_text = None
            elif getattr(record, "exc_text", None):
                exc_text = record.exc_text

            # If the message uses the legacy ``[CATEGORY] -`` prefix we
            # strip it here so the UI's "message" column stays clean and
            # the category is surfaced through its own field.
            clean_message, bracket_category = strip_legacy_bracket(message)

            payload = {
                "ts": record.created,
                "levelno": record.levelno,
                "level": record.levelname,
                "logger": record.name,
                "module": record.module,
                "func": record.funcName,
                "line": record.lineno,
                "thread": record.threadName,
                "message": clean_message,
                "exc_info": exc_text,
            }
            payload["category"] = bracket_category or derive_category(payload)
            self._buffer.add(payload)
        except Exception:  # noqa: BLE001 - last-resort guard
            self.handleError(record)


# ---------------------------------------------------------------------------
# Process-wide singleton wiring
# ---------------------------------------------------------------------------


global_buffer = LogBuffer()
"""Default buffer used by the FastAPI app."""

_installed = False
_install_lock = threading.Lock()


def install(
    *,
    buffer: LogBuffer | None = None,
    level: int = logging.INFO,
    capture_root: bool = True,
) -> BufferingHandler:
    """Attach a :class:`BufferingHandler` to the root logger.

    Safe to call multiple times -- subsequent calls return the same
    handler. ``level`` only filters at the handler boundary; the
    root logger's own level is respected. We *do not* raise the root
    level here so applications that started with the default
    ``WARNING`` will still need to enable ``INFO`` / ``DEBUG``
    elsewhere if they want those records to flow.
    """
    global _installed
    target = buffer or global_buffer

    with _install_lock:
        if _installed:
            for handler in logging.getLogger().handlers:
                if isinstance(handler, BufferingHandler):
                    return handler

        handler = BufferingHandler(target, level=level)

        if capture_root:
            root = logging.getLogger()
            root.addHandler(handler)
            # If the root has no handler-derived level set and is still
            # at WARNING (Python's default) we *do* lower it to INFO so
            # the UI shows something useful out of the box. Anything
            # the app explicitly configured (DEBUG, ERROR, ...) is left
            # untouched.
            if root.level in (logging.WARNING, logging.NOTSET):
                root.setLevel(logging.INFO)

        _installed = True
        return handler


def iter_records(buffer: LogBuffer | None = None) -> Iterable[dict[str, Any]]:
    """Convenience iterator over a snapshot of the global buffer."""
    return (buffer or global_buffer).snapshot()


def sync_from_settings(
    settings: Mapping[str, Any] | None,
    *,
    buffer: LogBuffer | None = None,
) -> set[str]:
    """Push the user's category preferences from ``settings`` into the
    buffer.

    Reads ``settings.logs.enabled_categories`` -- a whitelist of
    category names the live log viewer should capture. Three states
    are recognised:

    * key missing entirely  -> no filter, every category is captured.
    * present list, empty   -> nothing is captured (silence everything).
    * present list, populated -> only listed categories are captured.

    Internally this is expressed by computing the *complement* set
    against the buffer's known categories and pushing that as the
    disabled set, because the buffer drop-list is a more efficient
    runtime check than a whitelist (most records pass).

    Returns the resulting disabled set so callers can log / display
    confirmation.
    """
    target = buffer or global_buffer
    if not isinstance(settings, Mapping):
        return target.set_disabled_categories(None)
    logs_section = settings.get("logs")
    if not isinstance(logs_section, Mapping):
        return target.set_disabled_categories(None)
    if "enabled_categories" not in logs_section:
        return target.set_disabled_categories(None)
    raw = logs_section.get("enabled_categories")
    if not isinstance(raw, (list, tuple)):
        return target.set_disabled_categories(None)
    enabled = {str(v).strip().upper() for v in raw if str(v).strip()}
    known = set(target.known_categories()) | set(KNOWN_CATEGORIES)
    disabled = known - enabled
    return target.set_disabled_categories(disabled)


__all__ = [
    "BufferingHandler",
    "DEFAULT_BUFFER_SIZE",
    "KNOWN_CATEGORIES",
    "LEVEL_NAMES",
    "LogBuffer",
    "_level_value",
    "derive_category",
    "global_buffer",
    "install",
    "iter_records",
    "stream_filtered",
    "strip_legacy_bracket",
    "sync_from_settings",
]
