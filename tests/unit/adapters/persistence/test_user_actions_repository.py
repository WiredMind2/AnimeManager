"""Regression tests for :class:`UserActionsRepository`."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Any

import pytest

from adapters.persistence.user_actions_repository import UserActionsRepository
from domain.errors import InfrastructureError


class _SqliteDatabase:
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
        self.conn.execute(
            "CREATE TABLE anime (id INTEGER PRIMARY KEY, last_seen TEXT)"
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

    def raw_rows(self) -> list[tuple]:
        return list(self.conn.execute("SELECT anime_id, user_id, tag, liked FROM user_tags"))

    def force_insert(self, anime_id: int, user_id: int, tag, liked) -> None:
        self.conn.execute(
            "INSERT INTO user_tags (anime_id, user_id, tag, liked) VALUES (?, ?, ?, ?)",
            (anime_id, user_id, tag, liked),
        )
        self.conn.commit()


@pytest.fixture
def adapter_unique():
    db = _SqliteDatabase(with_unique_constraint=True)
    yield UserActionsRepository(db), db


@pytest.fixture
def adapter_no_constraint():
    db = _SqliteDatabase(with_unique_constraint=False)
    yield UserActionsRepository(db), db


def test_set_tag_can_be_modified_multiple_times(adapter_unique):
    adapter, db = adapter_unique

    adapter.set_tag(anime_id=23, tag="WATCHING", user_id=1)
    assert adapter.get_user_state(23, 1) == {
        "tag": "WATCHING",
        "liked": False,
        "auto_download": True,
    }

    adapter.set_tag(anime_id=23, tag="WATCHLIST", user_id=1)
    assert adapter.get_user_state(23, 1) == {
        "tag": "WATCHLIST",
        "liked": False,
        "auto_download": True,
    }

    adapter.set_tag(anime_id=23, tag="SEEN", user_id=1)
    assert adapter.get_user_state(23, 1) == {
        "tag": "SEEN",
        "liked": False,
        "auto_download": True,
    }

    rows = [r for r in db.raw_rows() if r[0] == 23 and r[1] == 1]
    assert len(rows) == 1


def test_set_tag_can_be_modified_when_table_has_no_unique_constraint(
    adapter_no_constraint,
):
    adapter, db = adapter_no_constraint

    adapter.set_tag(23, "WATCHING", 1)
    adapter.set_tag(23, "WATCHLIST", 1)
    adapter.set_tag(23, "SEEN", 1)

    assert adapter.get_user_state(23, 1)["tag"] == "SEEN"
    assert len(db.raw_rows()) == 1


def test_set_tag_does_not_overwrite_like(adapter_unique):
    adapter, _ = adapter_unique

    adapter.set_like(anime_id=42, liked=True, user_id=1)
    adapter.set_tag(anime_id=42, tag="WATCHING", user_id=1)

    state = adapter.get_user_state(42, 1)
    assert state == {"tag": "WATCHING", "liked": True, "auto_download": True}


def test_set_like_does_not_overwrite_tag(adapter_unique):
    adapter, _ = adapter_unique

    adapter.set_tag(anime_id=42, tag="WATCHLIST", user_id=1)
    adapter.set_like(anime_id=42, liked=True, user_id=1)
    adapter.set_like(anime_id=42, liked=False, user_id=1)

    state = adapter.get_user_state(42, 1)
    assert state == {"tag": "WATCHLIST", "liked": False, "auto_download": False}


def test_get_user_state_merges_legacy_duplicate_rows(adapter_no_constraint):
    adapter, db = adapter_no_constraint

    db.force_insert(99, 1, "WATCHING", None)
    db.force_insert(99, 1, None, 1)
    db.force_insert(99, 1, "SEEN", None)

    state = adapter.get_user_state(99, 1)
    assert state == {"tag": "SEEN", "liked": True, "auto_download": False}


def test_get_user_state_missing_row_returns_neutral_defaults(adapter_unique):
    adapter, _ = adapter_unique
    assert adapter.get_user_state(1, 1) == {
        "tag": "NONE",
        "liked": False,
        "auto_download": False,
    }


def test_mark_seen_writes_seen_tag(adapter_unique):
    adapter, db = adapter_unique
    db.conn.execute("INSERT INTO anime (id, last_seen) VALUES (7, NULL)")
    db.conn.commit()
    adapter.set_like(7, True, 1)
    adapter.mark_seen(7, file_name="ep01.mkv", user_id=1)

    assert adapter.get_user_state(7, 1) == {
        "tag": "SEEN",
        "liked": True,
        "auto_download": False,
    }


def test_list_anime_ids_with_tag(adapter_unique):
    adapter, _ = adapter_unique
    adapter.set_tag(1, "SEEN", user_id=1)
    adapter.set_tag(2, "WATCHING", user_id=1)
    adapter.set_tag(3, "seen", user_id=2)
    adapter.set_tag(1, "SEEN", user_id=2)

    assert set(adapter.list_anime_ids_with_tag("SEEN")) == {1, 3}
    assert adapter.list_anime_ids_with_tag("WATCHING") == [2]
    assert adapter.list_anime_ids_with_tag("") == []


def test_mark_seen_persists_last_seen_on_anime_row(adapter_unique):
    adapter, db = adapter_unique
    db.conn.execute("CREATE TABLE IF NOT EXISTS anime (id INTEGER PRIMARY KEY, last_seen TEXT)")
    db.conn.execute("INSERT INTO anime (id, last_seen) VALUES (7, NULL)")
    db.conn.commit()

    adapter.mark_seen(7, file_name="ep02.mkv", user_id=1)

    row = db.sql("SELECT last_seen FROM anime WHERE id=7")
    assert row == [("ep02.mkv",)]


def test_users_are_isolated(adapter_unique):
    adapter, _ = adapter_unique

    adapter.set_tag(15, "WATCHING", user_id=1)
    adapter.set_tag(15, "SEEN", user_id=2)

    assert adapter.get_user_state(15, 1)["tag"] == "WATCHING"
    assert adapter.get_user_state(15, 2)["tag"] == "SEEN"


def test_upsert_rejects_unknown_column(adapter_unique):
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
    class _BrokenDB:
        @contextmanager
        def get_lock(self):
            yield self

        def sql(self, *_args, **_kwargs):
            raise sqlite3.OperationalError("disk full")

    adapter = UserActionsRepository(_BrokenDB())  # type: ignore[arg-type]
    with pytest.raises(InfrastructureError):
        adapter.set_tag(1, "SEEN", 1)
    with pytest.raises(InfrastructureError):
        adapter.set_like(1, True, 1)
    with pytest.raises(InfrastructureError):
        adapter.get_user_state(1, 1)


def test_episode_progress_round_trip(adapter_unique):
    adapter, _ = adapter_unique
    adapter.set_episode_progress(1, 1, "ep-001", "IN_PROGRESS", 42.5)
    progress = adapter.get_episode_progress_map(1, 1)
    assert progress["ep-001"] == {
        "status": "IN_PROGRESS",
        "position_seconds": 42.5,
    }

    adapter.set_episode_progress(1, 1, "ep-001", "SEEN", 120.0)
    progress = adapter.get_episode_progress_map(1, 1)
    assert progress["ep-001"]["status"] == "SEEN"
    assert progress["ep-001"]["position_seconds"] == 120.0


def test_episode_progress_update_existing_row(adapter_unique):
    adapter, _ = adapter_unique
    adapter.set_episode_progress(2, 1, "ep-002", "UNSEEN")
    adapter.set_episode_progress(2, 1, "ep-002", "IN_PROGRESS", 10.0)
    progress = adapter.get_episode_progress_map(2, 1)
    assert progress["ep-002"]["status"] == "IN_PROGRESS"


def test_episode_progress_status_only_preserves_position(adapter_unique):
    adapter, _ = adapter_unique
    adapter.set_episode_progress(4, 1, "ep-004", "IN_PROGRESS", 708.0)
    adapter.set_episode_progress(4, 1, "ep-004", "SEEN")
    progress = adapter.get_episode_progress_map(4, 1)
    assert progress["ep-004"]["status"] == "SEEN"
    assert progress["ep-004"]["position_seconds"] == 708.0


def test_episode_progress_delete(adapter_unique):
    adapter, _ = adapter_unique
    adapter.set_episode_progress(3, 1, "ep-003", "SEEN")
    adapter.delete_episode_progress(3, 1, "ep-003")
    assert adapter.get_episode_progress_map(3, 1) == {}


def test_episode_progress_invalid_status_raises(adapter_unique):
    adapter, _ = adapter_unique
    with pytest.raises(InfrastructureError):
        adapter.set_episode_progress(1, 1, "ep-x", "INVALID")


def test_episode_progress_empty_file_id_raises(adapter_unique):
    adapter, _ = adapter_unique
    with pytest.raises(InfrastructureError):
        adapter.set_episode_progress(1, 1, "  ", "SEEN")


def test_delete_episode_progress_noop_for_empty_file_id(adapter_unique):
    adapter, _ = adapter_unique
    adapter.delete_episode_progress(1, 1, "")


def test_set_auto_download_toggle_and_eligibility(adapter_unique):
    adapter, _ = adapter_unique
    adapter.set_tag(10, "WATCHING", user_id=1)
    assert adapter.get_user_state(10, 1)["auto_download"] is True
    assert adapter.list_auto_download_eligible(1) == [10]

    adapter.set_auto_download(10, False, user_id=1)
    assert adapter.get_user_state(10, 1)["auto_download"] is False
    assert adapter.list_auto_download_eligible(1) == []

    # Opt-out is preserved when re-tagging WATCHING.
    adapter.set_tag(10, "WATCHLIST", user_id=1)
    adapter.set_tag(10, "WATCHING", user_id=1)
    assert adapter.get_user_state(10, 1)["auto_download"] is False
    assert adapter.list_auto_download_eligible(1) == []

    adapter.set_auto_download(10, True, user_id=1)
    assert adapter.list_auto_download_eligible(1) == [10]


def test_legacy_watching_without_column_value_is_eligible(adapter_unique):
    adapter, db = adapter_unique
    db.force_insert(11, 1, "WATCHING", 0)
    # Ensure column exists but leave NULL for this row.
    adapter._ensure_auto_download_column()
    db.conn.execute(
        "UPDATE user_tags SET auto_download=NULL WHERE anime_id=11 AND user_id=1"
    )
    db.conn.commit()
    assert adapter.get_user_state(11, 1)["auto_download"] is True
    assert adapter.list_auto_download_eligible(1) == [11]
