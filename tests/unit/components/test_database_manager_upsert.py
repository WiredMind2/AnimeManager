"""Regression tests for `DatabaseManager.upsert_anime_batch` / `update_anime`.

These tests model the real :class:`adapters.persistence.base.BaseDB`
contract where ``save()`` is the no-argument transaction-commit hook and
``set(id, data, table, save=...)`` is the upsert entrypoint.

The legacy implementation called ``db.save(anime)`` directly which fails
against every real backend (the GUI log emits
``EmbeddedMariaDB.save() takes 1 positional argument but 2 were given``
for every record in the batch). These tests pin the corrected wiring so
the regression cannot reappear silently.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Tuple
from contextlib import contextmanager

import pytest


@pytest.fixture
def DatabaseManager():
    from application.services.database_manager import DatabaseManager as _DM

    return _DM


def _silent_logger(*_args, **_kwargs):
    return None


class _NopLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class BaseDBLikeStub:
    """A stub that mirrors the real :class:`BaseDB` surface.

    Crucially, ``save()`` takes **no positional arguments** (it is the
    commit hook), and persistence goes through ``set(id, data, table,
    save=...)``. Calling ``save(anime)`` raises the same
    ``TypeError`` Python raises in production.
    """

    USE_CONNECTION_POOL = False

    def __init__(self) -> None:
        self._lock = _NopLock()
        self.rows: Dict[int, Dict[str, Any]] = {}
        self.metadata: Dict[int, Dict[str, Any]] = {}
        self.commit_count = 0
        self.set_calls: List[Tuple[int, Dict[str, Any], str, bool]] = []
        self.fail_set_for: set[int] = set()

    def get_lock(self):
        return self._lock

    def save(self) -> None:
        """Commit the current transaction. No arguments (matches BaseDB)."""
        self.commit_count += 1

    def set(self, id, data, table, save: bool = True) -> None:
        """Insert-or-update one row, optionally committing."""
        if id in self.fail_set_for:
            raise RuntimeError(f"forced failure for {id}")
        self.set_calls.append((id, dict(data), table, save))
        row = dict(data)
        row.setdefault("id", id)
        self.rows[id] = row
        if save:
            self.save()

    def exists(self, id, table) -> bool:
        return id in self.rows

    def insert(self, data, table, save: bool = True) -> None:
        self.set(data.get("id"), data, table, save=save)

    def update(self, id, data, table, save: bool = True) -> None:
        self.set(id, data, table, save=save)

    def save_metadata(self, anime_id, meta) -> None:
        self.metadata.setdefault(anime_id, {}).update(meta)

    def is_initialized(self) -> bool:
        return True

    def close(self) -> None:
        return None


class _PooledDBStub(BaseDBLikeStub):
    """Stub mimicking EmbeddedMariaDB pooled batch writes."""

    USE_CONNECTION_POOL = True

    def __init__(self) -> None:
        super().__init__()
        self.checkout_count = 0
        self._pinned_sql_conn = None

    @contextmanager
    def pinned_pool_connection(self):
        self.checkout_count += 1
        self._pinned_sql_conn = self
        try:
            yield self
        finally:
            self._pinned_sql_conn = None

    def commit_pinned_connection(self) -> None:
        self.commit_count += 1


# ---------------------------------------------------------------------------
# Reproduction tests for the production crash
# ---------------------------------------------------------------------------


class TestUpsertAnimeBatchAgainstRealContract:
    """These tests fail when `DatabaseManager` calls ``db.save(anime)``.

    They reproduce the GUI log message
    ``EmbeddedMariaDB.save() takes 1 positional argument but 2 were given``
    using a stub that mirrors the real backend signature.
    """

    def test_upsert_batch_persists_rows_via_set(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = BaseDBLikeStub()
        mgr.set_database(db)

        animes = [
            SimpleNamespace(id=130, title="Foo"),
            SimpleNamespace(id=131, title="Bar"),
        ]

        saved = mgr.upsert_anime_batch(animes)

        assert saved == 2, (
            "All rows should be persisted when the backend implements the "
            "real BaseDB.save() / set() contract."
        )
        assert set(db.rows.keys()) == {130, 131}
        # Every persisted row must travel through set(), not save().
        assert len(db.set_calls) == 2

    def test_upsert_batch_commits_each_row_inline(self, DatabaseManager):
        """Non-pooled backends still commit every row inline."""
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = BaseDBLikeStub()
        mgr.set_database(db)

        mgr.upsert_anime_batch(
            [SimpleNamespace(id=i, title=f"t{i}") for i in range(5)]
        )

        assert db.commit_count == 5
        assert len(db.rows) == 5

    def test_upsert_batch_uses_single_pool_checkout(self, DatabaseManager):
        """Pooled backends pin one connection for the entire batch."""
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _PooledDBStub()
        mgr.set_database(db)

        mgr.upsert_anime_batch(
            [SimpleNamespace(id=i, title=f"t{i}") for i in range(5)]
        )

        assert db.checkout_count == 1
        assert db.commit_count == 1
        assert len(db.rows) == 5

    def test_upsert_batch_single_commit_with_metadata(self, DatabaseManager):
        """Metadata writes defer commits when the pool connection is pinned."""
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = _PooledDBStub()
        mgr.set_database(db)

        class _AnimeWithMeta:
            def __init__(self, anime_id: int, title: str, genres: list[str]) -> None:
                self.id = anime_id
                self.title = title
                self._genres = genres

            def save_format(self):
                return {"id": self.id, "title": self.title}, {"genres": self._genres}

        mgr.upsert_anime_batch(
            [
                _AnimeWithMeta(1, "a", ["Action", "Drama"]),
                _AnimeWithMeta(2, "b", ["Comedy"]),
            ]
        )

        assert db.commit_count == 1
        assert db.metadata[1]["genres"] == ["Action", "Drama"]
        assert db.metadata[2]["genres"] == ["Comedy"]

    def test_upsert_batch_skips_individual_failures(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = BaseDBLikeStub()
        db.fail_set_for = {2}
        mgr.set_database(db)

        saved = mgr.upsert_anime_batch(
            [
                SimpleNamespace(id=1, title="ok"),
                SimpleNamespace(id=2, title="bad"),
                SimpleNamespace(id=3, title="ok"),
            ]
        )

        assert saved == 2
        assert set(db.rows.keys()) == {1, 3}

    def test_upsert_batch_records_telemetry(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = BaseDBLikeStub()
        mgr.set_database(db)

        mgr.upsert_anime_batch([SimpleNamespace(id=10), SimpleNamespace(id=11)])

        snap = mgr._telemetry.snapshot()
        assert snap["counters"].get("db.upserts_committed", 0) >= 2
        assert "db.upsert_anime_batch_ms" in snap["timers"]

    def test_update_anime_uses_set_not_save_with_arg(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = BaseDBLikeStub()
        mgr.set_database(db)

        mgr.update_anime(SimpleNamespace(id=42, title="Updated"))

        assert 42 in db.rows
        assert db.rows[42]["title"] == "Updated"
        assert len(db.set_calls) == 1

    def test_enqueue_anime_with_disabled_queue_uses_real_contract(self, DatabaseManager):
        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = BaseDBLikeStub()
        mgr.set_database(db)

        assert mgr.enqueue_anime(SimpleNamespace(id=7, title="Solo")) is True
        assert 7 in db.rows


class TestLegacyAnimeBatch:
    """Make sure :class:`adapters.persistence.models.Anime` records also
    persist correctly - they are dict-subclasses with `metadata_keys`.
    """

    def test_legacy_anime_persists_scalar_fields_via_set(self, DatabaseManager):
        from adapters.persistence.models import Anime

        mgr = DatabaseManager()
        mgr.log = _silent_logger
        db = BaseDBLikeStub()
        mgr.set_database(db)

        anime = Anime()
        anime.id = 757
        anime.title = "Cowboy Bebop"
        anime.episodes = 26

        saved = mgr.upsert_anime_batch([anime])

        assert saved == 1
        assert 757 in db.rows
        assert db.rows[757]["title"] == "Cowboy Bebop"
        assert db.rows[757]["episodes"] == 26
