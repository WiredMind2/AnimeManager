"""Persistence adapters for catalogue identity and merge operations."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from domain.catalog import preferred_catalog_id_from
from shared.contracts import INDEX_PROVIDER_KEYS, RepairStrategy

_DELETE_ID_TABLES = (
    "title_synonyms",
    "torrentsIndex",
    "genres",
    "pictures",
    "broadcasts",
    "animeRelations",
    "anime",
    "indexList",
)

_INDEX_COLUMNS = ("mal_id", "kitsu_id", "anilist_id", "anidb_id")


def _commit_deferred(db: Any) -> None:
    """Flush a deferred write batch on pooled or single-connection backends."""
    pinned = getattr(db, "_pinned_sql_conn", None)
    if pinned is not None and getattr(pinned, "db", None) is not None:
        commit_pinned = getattr(db, "commit_pinned_connection", None)
        if callable(commit_pinned):
            commit_pinned()
        else:
            pinned.db.commit()
    elif hasattr(db, "save"):
        db.save()


@contextmanager
def _batched_writes(db: Any) -> Iterator[None]:
    """Hold one transaction open; callers use ``save=False`` on ``sql()``."""
    pinned_ctx = getattr(db, "pinned_pool_connection", None)
    use_pool = bool(getattr(db, "USE_CONNECTION_POOL", False))
    if pinned_ctx is not None and use_pool:
        with pinned_ctx():
            yield
            _commit_deferred(db)
    else:
        with db.get_lock():
            yield
            _commit_deferred(db)


class CatalogIndexRepository:
    """``indexList`` lookups and allocation."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def _validate_key(self, provider_key: str) -> str:
        if provider_key not in INDEX_PROVIDER_KEYS:
            raise ValueError(f"Invalid provider key: {provider_key}")
        return provider_key

    def find_by_external(self, provider_key: str, external_id: int) -> Optional[int]:
        key = self._validate_key(provider_key)
        rows = self._db.sql(
            f"SELECT id FROM indexList WHERE {key}=?",
            (int(external_id),),
        )
        if not rows:
            return None
        return int(rows[0][0])

    def find_by_external_batch(
        self, pairs: Sequence[Tuple[str, int]]
    ) -> Dict[Tuple[str, int], int]:
        """Resolve many external ids with one query per provider column."""
        grouped: Dict[str, List[int]] = {}
        for provider_key, external_id in pairs:
            key = self._validate_key(provider_key)
            grouped.setdefault(key, []).append(int(external_id))

        out: Dict[Tuple[str, int], int] = {}
        for key, external_ids in grouped.items():
            unique_ids = list(dict.fromkeys(external_ids))
            if not unique_ids:
                continue
            placeholders = ",".join("?" * len(unique_ids))
            rows = self._db.sql(
                f"SELECT {key}, id FROM indexList WHERE {key} IN ({placeholders})",
                tuple(unique_ids),
            )
            for row in rows or []:
                out[(key, int(row[0]))] = int(row[1])
        return out

    def get_external_ids(self, internal_id: int) -> Dict[str, int]:
        rows = self._db.sql(
            "SELECT mal_id, kitsu_id, anilist_id, anidb_id FROM indexList WHERE id=?",
            (int(internal_id),),
        )
        if not rows:
            return {}
        row = rows[0]
        out: Dict[str, int] = {}
        for col, val in zip(_INDEX_COLUMNS, row):
            if val is not None:
                out[col] = int(val)
        return out

    def backfill_external_ids(
        self, internal_id: int, external_ids: Mapping[str, int]
    ) -> None:
        internal_id = int(internal_id)
        pinned = getattr(self._db, "_pinned_sql_conn", None)
        # Pooled backends run each sql() on a checkout connection; without
        # save=True those UPDATEs never commit and can leave row locks open.
        commit_each = pinned is None and bool(
            getattr(self._db, "USE_CONNECTION_POOL", False)
        )
        pending = False
        with self._db.get_lock():
            for key, value in external_ids.items():
                if key not in INDEX_PROVIDER_KEYS or value is None:
                    continue
                self._db.sql(
                    f"UPDATE indexList SET {key}=? WHERE id=? AND {key} IS NULL",
                    (int(value), internal_id),
                    save=commit_each,
                )
                pending = True
            if pending and not commit_each and pinned is None:
                _commit_deferred(self._db)

    def allocate(self, external_ids: Mapping[str, int]) -> int:
        normalized = {
            k: int(v)
            for k, v in external_ids.items()
            if k in INDEX_PROVIDER_KEYS and v is not None
        }
        if not normalized:
            raise ValueError("At least one external id is required to allocate a row")

        for key, ext in normalized.items():
            existing = self.find_by_external(key, ext)
            if existing is not None:
                self.backfill_external_ids(existing, normalized)
                return existing

        primary_key = sorted(normalized.keys())[0]
        if hasattr(self._db, "getId"):
            internal_id = self._db.getId(primary_key, normalized[primary_key])
            if internal_id is None:
                raise RuntimeError("getId failed to allocate indexList row")
            self.backfill_external_ids(int(internal_id), normalized)
            return int(internal_id)

        with self._db.get_lock():
            self._db.sql(
                f"INSERT INTO indexList({primary_key}) VALUES(?)",
                (normalized[primary_key],),
                save=True,
            )
            created = self.find_by_external(primary_key, normalized[primary_key])
            if created is None:
                raise RuntimeError("Failed to allocate indexList row")
            self.backfill_external_ids(created, normalized)
            return created


class CatalogMergeRepository:
    """Multi-table consolidation of duplicate catalogue ids."""

    def __init__(self, db: Any, *, log_fn=None) -> None:
        self._db = db
        self._log = log_fn

    def _warn(self, message: str) -> None:
        if self._log:
            self._log(message)

    def _repoint_torrents_index(self, duplicate_id: int, canonical_id: int) -> None:
        """Repoint anime→hash links; dedupe when canonical already owns the hash."""
        try:
            rows = self._db.sql(
                "SELECT value FROM torrentsIndex WHERE id=?",
                (duplicate_id,),
            )
        except Exception as exc:
            self._warn(f"merge scan torrentsIndex: {exc}")
            return

        for row in rows or []:
            hash_value = row[0]
            if hash_value is None:
                continue
            try:
                exists = self._db.sql(
                    "SELECT EXISTS(SELECT 1 FROM torrentsIndex "
                    "WHERE id=? AND value=?)",
                    (canonical_id, hash_value),
                )
                if exists and exists[0][0]:
                    self._db.sql(
                        "DELETE FROM torrentsIndex WHERE id=? AND value=?",
                        (duplicate_id, hash_value),
                        save=False,
                    )
                else:
                    self._db.sql(
                        "UPDATE torrentsIndex SET id=? WHERE id=? AND value=?",
                        (canonical_id, duplicate_id, hash_value),
                        save=False,
                    )
            except Exception as exc:
                self._warn(f"merge repoint torrentsIndex: {exc}")

    def _repoint_id_value_rows(
        self, duplicate_id: int, canonical_id: int, table: str
    ) -> None:
        """Repoint ``(id, value)`` metadata rows; drop duplicates canonical already has."""
        try:
            rows = self._db.sql(
                f"SELECT value FROM {table} WHERE id=?",
                (duplicate_id,),
            )
        except Exception as exc:
            self._warn(f"merge scan {table}: {exc}")
            return

        for row in rows or []:
            value = row[0]
            if value is None:
                continue
            try:
                exists = self._db.sql(
                    f"SELECT EXISTS(SELECT 1 FROM {table} WHERE id=? AND value=?)",
                    (canonical_id, value),
                )
                if exists and exists[0][0]:
                    self._db.sql(
                        f"DELETE FROM {table} WHERE id=? AND value=?",
                        (duplicate_id, value),
                        save=False,
                    )
                else:
                    self._db.sql(
                        f"UPDATE {table} SET id=? WHERE id=? AND value=?",
                        (canonical_id, duplicate_id, value),
                        save=False,
                    )
            except Exception as exc:
                self._warn(f"merge repoint {table}: {exc}")

    def _repoint_pictures(self, duplicate_id: int, canonical_id: int) -> None:
        """Repoint picture rows keyed by ``(id, size)``."""
        try:
            rows = self._db.sql(
                "SELECT size FROM pictures WHERE id=?",
                (duplicate_id,),
            )
        except Exception as exc:
            self._warn(f"merge scan pictures: {exc}")
            return

        for row in rows or []:
            size = row[0]
            try:
                exists = self._db.sql(
                    "SELECT EXISTS(SELECT 1 FROM pictures WHERE id=? AND size=?)",
                    (canonical_id, size),
                )
                if exists and exists[0][0]:
                    self._db.sql(
                        "DELETE FROM pictures WHERE id=? AND size=?",
                        (duplicate_id, size),
                        save=False,
                    )
                else:
                    self._db.sql(
                        "UPDATE pictures SET id=? WHERE id=? AND size=?",
                        (canonical_id, duplicate_id, size),
                        save=False,
                    )
            except Exception as exc:
                self._warn(f"merge repoint pictures: {exc}")

    def _repoint_broadcasts(self, duplicate_id: int, canonical_id: int) -> None:
        """Repoint broadcast row when canonical has none; otherwise drop duplicate."""
        try:
            dup_rows = self._db.sql(
                "SELECT 1 FROM broadcasts WHERE id=? LIMIT 1",
                (duplicate_id,),
            )
            if not dup_rows:
                return
            exists = self._db.sql(
                "SELECT EXISTS(SELECT 1 FROM broadcasts WHERE id=?)",
                (canonical_id,),
            )
            if exists and exists[0][0]:
                self._db.sql(
                    "DELETE FROM broadcasts WHERE id=?",
                    (duplicate_id,),
                    save=False,
                )
            else:
                self._db.sql(
                    "UPDATE broadcasts SET id=? WHERE id=?",
                    (canonical_id, duplicate_id),
                    save=False,
                )
        except Exception as exc:
            self._warn(f"merge repoint broadcasts: {exc}")

    def _repoint_anime_relations(self, duplicate_id: int, canonical_id: int) -> None:
        """Repoint relation rows; dedupe on ``(type, rel_id)``."""
        rel_col: Optional[str] = None
        rows = None
        for candidate in ("rel_id", "related_id"):
            try:
                rows = self._db.sql(
                    f"SELECT type, {candidate} FROM animeRelations WHERE id=?",
                    (duplicate_id,),
                )
                rel_col = candidate
                break
            except Exception:
                continue
        if rel_col is None:
            self._warn("merge scan animeRelations: unsupported schema")
            return

        for row in rows or []:
            rel_type, rel_id = row[0], row[1]
            if rel_id is None:
                continue
            try:
                exists = self._db.sql(
                    f"SELECT EXISTS(SELECT 1 FROM animeRelations "
                    f"WHERE id=? AND type=? AND {rel_col}=?)",
                    (canonical_id, rel_type, rel_id),
                )
                if exists and exists[0][0]:
                    self._db.sql(
                        f"DELETE FROM animeRelations WHERE id=? AND type=? AND {rel_col}=?",
                        (duplicate_id, rel_type, rel_id),
                        save=False,
                    )
                else:
                    self._db.sql(
                        f"UPDATE animeRelations SET id=? "
                        f"WHERE id=? AND type=? AND {rel_col}=?",
                        (canonical_id, duplicate_id, rel_type, rel_id),
                        save=False,
                    )
            except Exception as exc:
                self._warn(f"merge repoint animeRelations: {exc}")

    def merge(self, duplicate_id: int, canonical_id: int) -> int:
        duplicate_id = int(duplicate_id)
        canonical_id = int(canonical_id)
        if duplicate_id == canonical_id:
            return canonical_id

        index_repo = CatalogIndexRepository(self._db)
        with _batched_writes(self._db):
            dup_ids = index_repo.get_external_ids(duplicate_id)
            index_repo.backfill_external_ids(canonical_id, dup_ids)
            self._repoint_torrents_index(duplicate_id, canonical_id)
            self._repoint_id_value_rows(duplicate_id, canonical_id, "title_synonyms")
            self._repoint_id_value_rows(duplicate_id, canonical_id, "genres")
            self._repoint_pictures(duplicate_id, canonical_id)
            self._repoint_broadcasts(duplicate_id, canonical_id)
            self._repoint_anime_relations(duplicate_id, canonical_id)

            for sql, params in (
                (
                    "UPDATE characterRelations SET anime_id=? WHERE anime_id=?",
                    (canonical_id, duplicate_id),
                ),
                (
                    "UPDATE user_tags SET anime_id=? WHERE anime_id=?",
                    (canonical_id, duplicate_id),
                ),
            ):
                try:
                    self._db.sql(sql, params, save=False)
                except Exception as exc:
                    self._warn(f"merge repoint relations: {exc}")

            for table in _DELETE_ID_TABLES:
                try:
                    self._db.sql(
                        f"DELETE FROM {table} WHERE id=?",
                        (duplicate_id,),
                        save=False,
                    )
                except Exception as exc:
                    self._warn(f"merge delete {table}: {exc}")

            try:
                self._db.sql(
                    "DELETE FROM characterRelations WHERE anime_id=?",
                    (duplicate_id,),
                    save=False,
                )
            except Exception as exc:
                self._warn(f"merge delete characterRelations: {exc}")

        return canonical_id

    def repair_duplicates(
        self, *, strategy: RepairStrategy = RepairStrategy.PROVIDER_ID
    ) -> int:
        merged = 0
        if strategy in (RepairStrategy.PROVIDER_ID, RepairStrategy.ALL):
            merged += self._repair_by_provider_id()
        if strategy in (RepairStrategy.TITLE, RepairStrategy.ALL):
            merged += self._repair_by_title()
        return merged

    def _repair_by_provider_id(self) -> int:
        merged = 0
        for col in INDEX_PROVIDER_KEYS:
            try:
                rows = self._db.sql(
                    f"SELECT id, {col} FROM indexList WHERE {col} IS NOT NULL"
                )
            except Exception as exc:
                self._warn(f"repair scan {col}: {exc}")
                continue
            groups: dict[int, List[int]] = {}
            for row in rows or []:
                internal_id, ext_id = int(row[0]), int(row[1])
                groups.setdefault(ext_id, []).append(internal_id)
            for ids in groups.values():
                if len(ids) < 2:
                    continue
                canonical = preferred_catalog_id_from(ids)
                for duplicate in ids:
                    if duplicate == canonical:
                        continue
                    self.merge(duplicate, canonical)
                    merged += 1
        return merged

    def _repair_by_title(self) -> int:
        merged = 0
        try:
            title_groups = self._db.sql(
                "SELECT LOWER(TRIM(title)) AS norm_title, "
                "GROUP_CONCAT(id ORDER BY id) AS ids "
                "FROM anime "
                "WHERE title IS NOT NULL AND TRIM(title) <> '' "
                "GROUP BY LOWER(TRIM(title)) "
                "HAVING COUNT(*) > 1"
            )
        except Exception as exc:
            self._warn(f"repair title scan: {exc}")
            return 0

        for row in title_groups or []:
            id_blob = row[1]
            if not id_blob:
                continue
            ids = [int(part) for part in str(id_blob).split(",") if part.strip()]
            if len(ids) < 2:
                continue
            canonical = preferred_catalog_id_from(ids)
            for duplicate in ids:
                if duplicate == canonical:
                    continue
                self.merge(duplicate, canonical)
                merged += 1
        return merged

    def purge_provisional_anime_rows(self) -> int:
        """Delete orphan anime rows whose primary key is a provisional (negative) id.

        These rows are created when schedule-light fingerprints leak into
        persistence without catalogue identity assignment. They have no
        usable ``indexList`` mapping and break UI detail links.
        """
        try:
            rows = self._db.sql("SELECT id FROM anime WHERE id < 0")
        except Exception as exc:
            self._warn(f"provisional purge scan: {exc}")
            return 0

        deleted = 0
        for row in rows or []:
            orphan_id = int(row[0])
            with _batched_writes(self._db):
                for table in _DELETE_ID_TABLES:
                    try:
                        self._db.sql(
                            f"DELETE FROM {table} WHERE id=?",
                            (orphan_id,),
                            save=False,
                        )
                    except Exception as exc:
                        self._warn(f"provisional purge delete {table}: {exc}")
                for sql, params in (
                    (
                        "DELETE FROM characterRelations WHERE anime_id=?",
                        (orphan_id,),
                    ),
                    (
                        "DELETE FROM user_tags WHERE anime_id=?",
                        (orphan_id,),
                    ),
                ):
                    try:
                        self._db.sql(sql, params, save=False)
                    except Exception as exc:
                        self._warn(f"provisional purge relations: {exc}")
            deleted += 1
        return deleted
