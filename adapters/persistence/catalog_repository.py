"""Persistence adapters for catalogue identity and merge operations."""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Mapping, Optional

from shared.contracts import INDEX_PROVIDER_KEYS, RepairStrategy

_REPOINT_ID_TABLES = (
    "title_synonyms",
    "genres",
    "pictures",
    "broadcasts",
    "torrentsIndex",
    "torrents",
    "animeRelations",
)

_DELETE_ID_TABLES = (
    "anime",
    "title_synonyms",
    "torrentsIndex",
    "genres",
    "pictures",
    "broadcasts",
    "torrents",
    "animeRelations",
    "indexList",
)

_INDEX_COLUMNS = ("mal_id", "kitsu_id", "anilist_id", "anidb_id")


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
        with self._db.get_lock():
            for key, value in external_ids.items():
                if key not in INDEX_PROVIDER_KEYS or value is None:
                    continue
                self._db.sql(
                    f"UPDATE indexList SET {key}=? WHERE id=? AND {key} IS NULL",
                    (int(value), internal_id),
                    save=True,
                )

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

    def merge(self, duplicate_id: int, canonical_id: int) -> int:
        duplicate_id = int(duplicate_id)
        canonical_id = int(canonical_id)
        if duplicate_id == canonical_id:
            return canonical_id

        index_repo = CatalogIndexRepository(self._db)
        with self._db.get_lock():
            dup_ids = index_repo.get_external_ids(duplicate_id)
            index_repo.backfill_external_ids(canonical_id, dup_ids)

            for table in _REPOINT_ID_TABLES:
                try:
                    self._db.sql(
                        f"UPDATE {table} SET id=? WHERE id=?",
                        (canonical_id, duplicate_id),
                        save=True,
                    )
                except Exception as exc:
                    self._warn(f"merge repoint {table}: {exc}")

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
                    self._db.sql(sql[0], params, save=True)
                except Exception as exc:
                    self._warn(f"merge repoint relations: {exc}")

            for table in _DELETE_ID_TABLES:
                try:
                    self._db.sql(
                        f"DELETE FROM {table} WHERE id=?",
                        (duplicate_id,),
                        save=True,
                    )
                except Exception as exc:
                    self._warn(f"merge delete {table}: {exc}")

            try:
                self._db.sql(
                    "DELETE FROM characterRelations WHERE anime_id=?",
                    (duplicate_id,),
                    save=True,
                )
            except Exception as exc:
                self._warn(f"merge delete characterRelations: {exc}")

            if hasattr(self._db, "save"):
                try:
                    self._db.save()
                except Exception as exc:
                    self._warn(f"merge commit: {exc}")

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
                canonical = min(ids)
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
            canonical = min(ids)
            for duplicate in ids:
                if duplicate == canonical:
                    continue
                self.merge(duplicate, canonical)
                merged += 1
        return merged
