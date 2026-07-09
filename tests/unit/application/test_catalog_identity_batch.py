"""Tests for batched catalogue identity resolution."""

from __future__ import annotations

from application.services.catalog_identity import CatalogIdentityService
from adapters.persistence.catalog_repository import CatalogIndexRepository


class _BatchDB:
    USE_CONNECTION_POOL = False

    def __init__(self) -> None:
        self.commits = 0
        self.queries: list[str] = []
        self.rows = {
            ("mal_id", 42): 7,
            ("mal_id", 55): 7,
        }

    def get_lock(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def sql(self, query, params=(), save=False):
        self.queries.append(query)
        if "FROM indexList WHERE mal_id IN" in query:
            mal_ids = [int(value) for value in params]
            out = []
            for mal_id in mal_ids:
                internal = self.rows.get(("mal_id", mal_id))
                if internal is not None:
                    out.append((mal_id, internal))
            return out
        if query.startswith("SELECT id FROM indexList WHERE mal_id=?"):
            mal_id = int(params[0])
            internal = self.rows.get(("mal_id", mal_id))
            return [(internal,)] if internal is not None else []
        if "UPDATE indexList SET" in query:
            if save:
                self.commits += 1
            return []
        raise AssertionError(f"Unexpected SQL: {query!r} {params!r}")

    def save(self) -> None:
        self.commits += 1


class _MergeStub:
    def merge(self, duplicate_id: int, canonical_id: int) -> int:
        return canonical_id


def test_find_by_external_batch_uses_grouped_lookup():
    db = _BatchDB()
    repo = CatalogIndexRepository(db)

    found = repo.find_by_external_batch([("mal_id", 42), ("mal_id", 55), ("mal_id", 99)])

    assert found[("mal_id", 42)] == 7
    assert found[("mal_id", 55)] == 7
    assert ("mal_id", 99) not in found
    assert sum(1 for q in db.queries if "mal_id IN" in q) == 1


def test_resolve_external_ids_batch_commits_once_for_existing_rows():
    db = _BatchDB()
    service = CatalogIdentityService(db, merge_service=_MergeStub())

    results = service.resolve_external_ids_batch(
        [
            {"mal_id": 42},
            {"mal_id": 55},
        ]
    )

    assert len(results) == 2
    assert results[0].catalog_id == 7
    assert results[1].catalog_id == 7
    assert any("mal_id IN" in query for query in db.queries)
