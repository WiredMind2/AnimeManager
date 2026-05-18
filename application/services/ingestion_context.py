"""Context helpers for canonical metadata ingestion runs."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable, Iterator


@contextmanager
def deferred_provider_writes(providers: Iterable[Any]) -> Iterator[None]:
    """Enable ``defer_writes`` on providers for the duration of a pipeline run.

    Side-effect helpers (``save_pictures``, ``save_genres``, …) queue SQL
  instead of hitting the database immediately. Callers should persist the
    primary anime payload through ``DatabaseManager.upsert_anime_batch`` and
    then flush queued side effects via :func:`flush_deferred_provider_writes`.
    """
    touched = []
    previous: list[tuple[Any, bool]] = []
    for provider in providers:
        if provider is None:
            continue
        touched.append(provider)
        had = bool(getattr(provider, "defer_writes", False))
        previous.append((provider, had))
        provider.defer_writes = True
    try:
        yield
    finally:
        for provider, had in previous:
            provider.defer_writes = had


def flush_deferred_provider_writes(providers: Iterable[Any]) -> None:
    """Drain deferred SQL queues on provider instances."""
    for provider in providers:
        if provider is None:
            continue
        handler = getattr(provider, "handle_sql_queue", None)
        if callable(handler):
            try:
                handler()
            except Exception:
                pass


__all__ = ["deferred_provider_writes", "flush_deferred_provider_writes"]
