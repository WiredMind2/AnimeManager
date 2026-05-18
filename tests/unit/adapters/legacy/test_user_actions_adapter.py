"""Regression tests for :class:`LegacyUserActionsAdapter`.

These tests pin the persistence contract that the web/Tk UI relies on
and protect against the historical bug where tagging an anime more
than once silently failed -- ``REPLACE INTO`` was either creating
duplicate rows (no UNIQUE constraint) or wiping the unrelated column
(with a UNIQUE constraint), leaving ``get_user_state`` to return a
stale view of the world.

The fixture spins up a real in-memory SQLite database and wires it
through a minimal database wrapper that mimics the legacy contract
(``get_lock()`` + ``sql(query, params, save=True/False)``). That gives
us a *true* integration check of the adapter's SQL against a SQLite
backend without depending on the rest of the legacy bootstrap chain.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Any

import pytest

from adapters.legacy.runtime import LegacyUserActionsAdapter
from domain.errors import InfrastructureError


class _SqliteDatabase:
    """Tiny shim that mirrors the surface of the legacy DB wrapper.

    Only the calls used by ``LegacyUserActionsAdapter`` are
    implemented: a re-entrant ``get_lock()`` context manager and a
    ``sql(query, params, save=False)`` helper that returns rows or
    persists a write.
    """

    def __init__(self, *, with_unique_constraint: bool) -> None:
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._lock = threading.RLock()
        constraint = ", UNIQUE(anime_id, user_id)" if with_unique_constraint else ""
        self.conn.execute(
            f"""
            CREATE TABLE user_tags (
                anime_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                tag TEXT,
                liked INTEGER
                {constraint}
            )
            """
        )
        self.conn.commit()

    @contextmanager
    def get_lock(self):
        with self._lock:
            yield self

    def sql(
        self,
        query: str,
        params: tuple[Any, ...] = (),
        save: bool = False,
        to_dict: bool = False,
    ) -> list[tuple]:
        cur = self.conn.execute(query, tuple(params))
        if save:
            self.conn.commit()
            return []
        try:
            return list(cur.fetchall())
        finally:
            cur.close()

    # Helpers for tests
    def raw_rows(self) -> list[tuple]:
        return list(self.conn.execute("SELECT anime_id, user_id, tag, liked FROM user_tags"))

    def force_insert(self, anime_id: int, user_id: int, tag, liked) -> None:
        self.conn.execute(
            "INSERT INTO user_tags (anime_id, user_id, tag, liked) VALUES (?, ?, ?, ?)",
            (anime_id, user_id, tag, liked),
        )
        self.conn.commit()


class _Runtime:
    """Minimal stand-in for :class:`LegacyRuntime`."""

    def __init__(self, db: _SqliteDatabase) -> None:
        self.database = db


@pytest.fixture
def adapter_unique():
    """Adapter against a schema WITH a UNIQUE(anime_id, user_id) constraint."""
    db = _SqliteDatabase(with_unique_constraint=True)
    yield LegacyUserActionsAdapter(_Runtime(db)), db


@pytest.fixture
def adapter_no_constraint():
    """Adapter against the *historical* schema without a UNIQUE
    constraint -- the worst case where ``REPLACE INTO`` would silently
    accumulate duplicate rows."""
    db = _SqliteDatabase(with_unique_constraint=False)
    yield LegacyUserActionsAdapter(_Runtime(db)), db


# ---------------------------------------------------------------------------
# The core regression: tags must be modifiable after the first write.
# ---------------------------------------------------------------------------


def test_set_tag_can_be_modified_multiple_times(adapter_unique):
    adapter, db = adapter_unique

    adapter.set_tag(anime_id=23, tag="WATCHING", user_id=1)
    assert adapter.get_user_state(23, 1) == {"tag": "WATCHING", "liked": False}

    adapter.set_tag(anime_id=23, tag="WATCHLIST", user_id=1)
    assert adapter.get_user_state(23, 1) == {"tag": "WATCHLIST", "liked": False}

    adapter.set_tag(anime_id=23, tag="SEEN", user_id=1)
    assert adapter.get_user_state(23, 1) == {"tag": "SEEN", "liked": False}

    # Only ONE row exists for this (anime_id, user_id) -- no accumulation.
    rows = [r for r in db.raw_rows() if r[0] == 23 and r[1] == 1]
    assert len(rows) == 1


def test_set_tag_can_be_modified_when_table_has_no_unique_constraint(
    adapter_no_constraint,
):
    """The historical bug specifically required a UNIQUE constraint to
    not be present (which is the case in some pre-migration databases).
    Without the new UPDATE-or-INSERT logic, ``REPLACE INTO`` would just
    append rows and ``get_user_state`` returned the OLDEST one.
    """
    adapter, db = adapter_no_constraint

    adapter.set_tag(23, "WATCHING", 1)
    adapter.set_tag(23, "WATCHLIST", 1)
    adapter.set_tag(23, "SEEN", 1)

    assert adapter.get_user_state(23, 1)["tag"] == "SEEN"
    assert len(db.raw_rows()) == 1


def test_set_tag_does_not_overwrite_like(adapter_unique):
    """The smoking-gun behavior the user reported: liking + tagging
    must not clobber each other."""
    adapter, _ = adapter_unique

    adapter.set_like(anime_id=42, liked=True, user_id=1)
    adapter.set_tag(anime_id=42, tag="WATCHING", user_id=1)

    state = adapter.get_user_state(42, 1)
    assert state == {"tag": "WATCHING", "liked": True}


def test_set_like_does_not_overwrite_tag(adapter_unique):
    adapter, _ = adapter_unique

    adapter.set_tag(anime_id=42, tag="WATCHLIST", user_id=1)
    adapter.set_like(anime_id=42, liked=True, user_id=1)
    adapter.set_like(anime_id=42, liked=False, user_id=1)

    state = adapter.get_user_state(42, 1)
    assert state == {"tag": "WATCHLIST", "liked": False}


# ---------------------------------------------------------------------------
# Backward compatibility with legacy duplicate-row state.
# ---------------------------------------------------------------------------


def test_get_user_state_merges_legacy_duplicate_rows(adapter_no_constraint):
    """Users whose DB still contains duplicate rows from the buggy era
    must see a coherent view (last non-NULL value wins per column)."""
    adapter, db = adapter_no_constraint

    db.force_insert(99, 1, "WATCHING", None)
    db.force_insert(99, 1, None, 1)
    db.force_insert(99, 1, "SEEN", None)

    state = adapter.get_user_state(99, 1)
    assert state == {"tag": "SEEN", "liked": True}


def test_get_user_state_missing_row_returns_neutral_defaults(adapter_unique):
    adapter, _ = adapter_unique
    assert adapter.get_user_state(1, 1) == {"tag": "NONE", "liked": False}


# ---------------------------------------------------------------------------
# mark_seen and isolation
# ---------------------------------------------------------------------------


def test_mark_seen_writes_seen_tag(adapter_unique):
    adapter, _ = adapter_unique
    adapter.set_like(7, True, 1)
    adapter.mark_seen(7, file_name="ep01.mkv", user_id=1)

    assert adapter.get_user_state(7, 1) == {"tag": "SEEN", "liked": True}


def test_users_are_isolated(adapter_unique):
    adapter, _ = adapter_unique

    adapter.set_tag(15, "WATCHING", user_id=1)
    adapter.set_tag(15, "SEEN", user_id=2)

    assert adapter.get_user_state(15, 1)["tag"] == "WATCHING"
    assert adapter.get_user_state(15, 2)["tag"] == "SEEN"


# ---------------------------------------------------------------------------
# Defensive behavior
# ---------------------------------------------------------------------------


def test_upsert_rejects_unknown_column(adapter_unique):
    """Defense in depth: the column name is interpolated into SQL, so
    the adapter must refuse anything outside the whitelist."""
    adapter, _ = adapter_unique
    with pytest.raises(InfrastructureError):
        adapter._upsert_column(
            anime_id=1,
            user_id=1,
            column="tag; DROP TABLE user_tags",
            value="X",
            action_label="oops",
        )


def test_db_errors_surface_as_infrastructure_error():
    """Underlying DB errors are wrapped, never leaked raw to callers."""

    class _BrokenDB:
        @contextmanager
        def get_lock(self):
            yield self

        def sql(self, *_args, **_kwargs):
            raise sqlite3.OperationalError("disk full")

    adapter = LegacyUserActionsAdapter(_Runtime(_BrokenDB()))  # type: ignore[arg-type]
    with pytest.raises(InfrastructureError):
        adapter.set_tag(1, "SEEN", 1)
    with pytest.raises(InfrastructureError):
        adapter.set_like(1, True, 1)
    with pytest.raises(InfrastructureError):
        adapter.get_user_state(1, 1)


def test_episode_progress_roundtrip(adapter_unique):
    adapter, _ = adapter_unique
    adapter.set_episode_progress(1, 1, "ep-abc", "IN_PROGRESS", position_seconds=120.5)
    m = adapter.get_episode_progress_map(1, 1)
    assert m["ep-abc"]["status"] == "IN_PROGRESS"
    assert m["ep-abc"]["position_seconds"] == 120.5
    adapter.set_episode_progress(1, 1, "ep-abc", "SEEN", position_seconds=900.0)
    assert adapter.get_episode_progress_map(1, 1)["ep-abc"]["status"] == "SEEN"
    adapter.delete_episode_progress(1, 1, "ep-abc")
    assert adapter.get_episode_progress_map(1, 1) == {}


def test_episode_progress_rejects_bad_status(adapter_unique):
    adapter, _ = adapter_unique
    with pytest.raises(InfrastructureError):
        adapter.set_episode_progress(1, 1, "ep-x", "BOGUS", position_seconds=None)
