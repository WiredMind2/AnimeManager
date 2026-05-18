"""Helpers for safely merging duplicate anime IDs.

The merge is strict and deterministic: IDs are merged only when an explicit
cross-provider external mapping proves they represent the same anime.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


_EXTERNAL_ID_COLUMNS: Tuple[str, ...] = (
    "mal_id",
    "kitsu_id",
    "anilist_id",
    "anidb_id",
)


@dataclass(frozen=True)
class MergeResult:
    canonical_id: int
    merged_ids: Tuple[int, ...] = ()
    skipped_reason: str = ""


class AnimeMergeService:
    """Backend-agnostic anime ID merge orchestration."""

    def __init__(self, db: Any, log: Optional[Callable[..., None]] = None) -> None:
        self._db = db
        self._log = log or (lambda *_a, **_k: None)
        self._table_exists_cache: Dict[str, bool] = {}

    def merge_from_external_mappings(
        self, source_id: int, mapped: Sequence[Tuple[str, Any]]
    ) -> MergeResult:
        source_id = int(source_id)
        cleaned = self._normalise_mappings(mapped)
        if not cleaned:
            return MergeResult(canonical_id=source_id, skipped_reason="no_mappings")

        self._ensure_index_row(source_id)
        self._persist_external_ids(source_id, cleaned)

        linked_ids = {source_id}
        for api_key, api_id in cleaned:
            rows = self._db.sql(
                f"SELECT id FROM indexList WHERE {api_key}=?",
                (api_id,),
            )
            for row in rows or []:
                try:
                    linked_ids.add(int(row[0]))
                except (TypeError, ValueError, IndexError):
                    continue

        if len(linked_ids) <= 1:
            return MergeResult(canonical_id=source_id)

        canonical = self._select_canonical_id(linked_ids)
        merged: List[int] = []
        for anime_id in sorted(linked_ids):
            if anime_id == canonical:
                continue
            if self.merge_two_ids(canonical, anime_id):
                merged.append(anime_id)
        return MergeResult(canonical_id=canonical, merged_ids=tuple(merged))

    def merge_two_ids(self, canonical_id: int, duplicate_id: int) -> bool:
        canonical_id = int(canonical_id)
        duplicate_id = int(duplicate_id)
        if canonical_id == duplicate_id:
            return False

        if not self._table_exists("indexList"):
            return False

        winner = self._fetch_index_row(canonical_id)
        loser = self._fetch_index_row(duplicate_id)
        if winner is None or loser is None:
            return False

        for column in _EXTERNAL_ID_COLUMNS:
            w = winner.get(column)
            l = loser.get(column)
            if w is not None and l is not None and str(w) != str(l):
                self._log(
                    "API_MERGE",
                    f"Skipped merge {duplicate_id}->{canonical_id}: "
                    f"conflicting {column} ({w} vs {l})",
                )
                return False

        self._merge_anime_scalar_fields(canonical_id, duplicate_id)
        self._merge_external_id_columns(canonical_id, duplicate_id, winner, loser)
        self._remap_user_state(canonical_id, duplicate_id)

        if self._table_exists("anime"):
            self._db.sql("DELETE FROM anime WHERE id=?", (duplicate_id,), save=True)
        self._db.sql("DELETE FROM indexList WHERE id=?", (duplicate_id,), save=True)
        return True

    def backfill_existing_duplicates(self, *, max_passes: int = 8) -> Dict[str, int]:
        if not self._table_exists("indexList"):
            return {"passes": 0, "merged": 0, "groups": 0}
        merged = 0
        passes = 0
        groups = 0
        for _ in range(max(1, int(max_passes))):
            duplicate_groups = self._collect_duplicate_groups()
            if not duplicate_groups:
                break
            passes += 1
            groups += len(duplicate_groups)
            changed_this_pass = 0
            for ids in duplicate_groups:
                canonical = self._select_canonical_id(ids)
                for anime_id in sorted(ids):
                    if anime_id == canonical:
                        continue
                    if self.merge_two_ids(canonical, anime_id):
                        merged += 1
                        changed_this_pass += 1
            if changed_this_pass == 0:
                break
        return {"passes": passes, "merged": merged, "groups": groups}

    def _normalise_mappings(
        self, mapped: Sequence[Tuple[str, Any]]
    ) -> List[Tuple[str, int]]:
        out: List[Tuple[str, int]] = []
        for item in mapped or ():
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            api_key = str(item[0]).strip()
            if api_key not in _EXTERNAL_ID_COLUMNS:
                continue
            try:
                api_id = int(item[1])
            except (TypeError, ValueError):
                continue
            out.append((api_key, api_id))
        return out

    def _collect_duplicate_groups(self) -> List[set[int]]:
        groups: List[set[int]] = []
        for col in _EXTERNAL_ID_COLUMNS:
            rows = self._db.sql(
                f"SELECT id, {col} FROM indexList WHERE {col} IS NOT NULL"
            )
            by_external: Dict[str, set[int]] = {}
            for row in rows or []:
                try:
                    anime_id = int(row[0])
                    ext = str(row[1]).strip()
                except (TypeError, ValueError, IndexError):
                    continue
                if not ext:
                    continue
                by_external.setdefault(ext, set()).add(anime_id)
            for ids in by_external.values():
                if len(ids) > 1:
                    groups.append(set(ids))

        if not groups:
            return []
        merged: List[set[int]] = []
        for ids in groups:
            fused = set(ids)
            changed = True
            while changed:
                changed = False
                for other in groups:
                    if fused.intersection(other) and not other.issubset(fused):
                        fused.update(other)
                        changed = True
            if not any(fused == existing for existing in merged):
                merged.append(fused)
        return merged

    def _select_canonical_id(self, ids: Iterable[int]) -> int:
        ranked = sorted(
            (int(i) for i in ids),
            key=lambda anime_id: (-self._score_anime_id(anime_id), anime_id),
        )
        return ranked[0]

    def _score_anime_id(self, anime_id: int) -> int:
        score = 0
        score += 100 * self._count_rows("episode_progress", "anime_id", anime_id)
        score += 50 * self._count_rows("torrentsIndex", "id", anime_id)
        score += 25 * self._count_rows("anime_torrent_search_memory", "anime_id", anime_id)
        score += 20 * self._count_rows("user_tags", "anime_id", anime_id)
        score += 5 * self._count_rows("title_synonyms", "id", anime_id)
        score += 3 * self._count_rows("genres", "id", anime_id)
        score += 2 * self._count_rows("animeRelations", "id", anime_id)
        return score

    def _count_rows(self, table: str, column: str, anime_id: int) -> int:
        if not self._table_exists(table):
            return 0
        try:
            rows = self._db.sql(
                f"SELECT COUNT(1) FROM {table} WHERE {column}=?",
                (anime_id,),
            )
            if rows:
                return int(rows[0][0] or 0)
        except Exception:
            return 0
        return 0

    def _table_exists(self, table: str) -> bool:
        cached = self._table_exists_cache.get(table)
        if cached is not None:
            return cached
        try:
            self._db.sql(f"SELECT 1 FROM {table} LIMIT 1")
            self._table_exists_cache[table] = True
            return True
        except Exception:
            self._table_exists_cache[table] = False
            return False

    def _ensure_index_row(self, anime_id: int) -> None:
        if not self._table_exists("indexList"):
            return
        exists = self._db.sql("SELECT 1 FROM indexList WHERE id=? LIMIT 1", (anime_id,))
        if exists:
            return
        self._db.sql("INSERT INTO indexList(id) VALUES(?)", (anime_id,), save=True)

    def _persist_external_ids(self, anime_id: int, mapped: Sequence[Tuple[str, int]]) -> None:
        for api_key, api_id in mapped:
            rows = self._db.sql(
                f"SELECT {api_key} FROM indexList WHERE id=? LIMIT 1", (anime_id,)
            )
            current = rows[0][0] if rows else None
            if current is None or str(current) == str(api_id):
                self._db.sql(
                    f"UPDATE indexList SET {api_key}=? WHERE id=?",
                    (api_id, anime_id),
                    save=True,
                )

    def _fetch_index_row(self, anime_id: int) -> Optional[Dict[str, Any]]:
        cols = ", ".join(("id",) + _EXTERNAL_ID_COLUMNS)
        rows = self._db.sql(f"SELECT {cols} FROM indexList WHERE id=? LIMIT 1", (anime_id,))
        if not rows:
            return None
        row = rows[0]
        return {
            "id": row[0],
            "mal_id": row[1],
            "kitsu_id": row[2],
            "anilist_id": row[3],
            "anidb_id": row[4],
        }

    def _merge_anime_scalar_fields(self, canonical_id: int, duplicate_id: int) -> None:
        if not self._table_exists("anime"):
            return
        cols = (
            "title",
            "picture",
            "date_from",
            "date_to",
            "synopsis",
            "episodes",
            "duration",
            "rating",
            "status",
            "broadcast",
            "trailer",
        )
        column_sql = ", ".join(cols)
        winner_rows = self._db.sql(
            f"SELECT {column_sql} FROM anime WHERE id=? LIMIT 1",
            (canonical_id,),
        )
        loser_rows = self._db.sql(
            f"SELECT {column_sql} FROM anime WHERE id=? LIMIT 1",
            (duplicate_id,),
        )
        if not winner_rows or not loser_rows:
            return
        winner = dict(zip(cols, winner_rows[0]))
        loser = dict(zip(cols, loser_rows[0]))

        merged: Dict[str, Any] = {}
        for field in cols:
            w = winner.get(field)
            l = loser.get(field)
            if field == "synopsis":
                w_text = str(w or "").strip()
                l_text = str(l or "").strip()
                if len(l_text) > len(w_text):
                    merged[field] = l
                continue
            if self._is_empty(w) and not self._is_empty(l):
                merged[field] = l
        if not merged:
            return
        sets = ", ".join(f"{field}=?" for field in merged.keys())
        self._db.sql(
            f"UPDATE anime SET {sets} WHERE id=?",
            tuple(merged.values()) + (canonical_id,),
            save=True,
        )

    @staticmethod
    def _is_empty(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        return False

    def _merge_external_id_columns(
        self,
        canonical_id: int,
        duplicate_id: int,
        winner: Dict[str, Any],
        loser: Dict[str, Any],
    ) -> None:
        for column in _EXTERNAL_ID_COLUMNS:
            if winner.get(column) is None and loser.get(column) is not None:
                self._db.sql(
                    f"UPDATE indexList SET {column}=? WHERE id=?",
                    (loser[column], canonical_id),
                    save=True,
                )
        self._db.sql(
            "DELETE FROM indexList WHERE id=?",
            (duplicate_id,),
            save=True,
        )

    def _remap_user_state(self, canonical_id: int, duplicate_id: int) -> None:
        self._merge_id_value_table("torrentsIndex", "id", canonical_id, duplicate_id)
        self._merge_id_value_table("title_synonyms", "id", canonical_id, duplicate_id)
        self._merge_id_value_table("genres", "id", canonical_id, duplicate_id)
        self._merge_user_tags(canonical_id, duplicate_id)
        self._merge_episode_progress(canonical_id, duplicate_id)
        self._merge_search_memory(canonical_id, duplicate_id)
        self._merge_anime_relations(canonical_id, duplicate_id)
        self._remap_single_column("characterRelations", "anime_id", canonical_id, duplicate_id)

    def _merge_id_value_table(
        self, table: str, id_col: str, canonical_id: int, duplicate_id: int
    ) -> None:
        if not self._table_exists(table):
            return
        rows = self._db.sql(f"SELECT value FROM {table} WHERE {id_col}=?", (duplicate_id,))
        for row in rows or []:
            value = row[0] if row else None
            if value is None:
                continue
            exists = self._db.sql(
                f"SELECT 1 FROM {table} WHERE {id_col}=? AND value=? LIMIT 1",
                (canonical_id, value),
            )
            if not exists:
                self._db.sql(
                    f"INSERT INTO {table}({id_col}, value) VALUES(?, ?)",
                    (canonical_id, value),
                    save=True,
                )
        self._db.sql(f"DELETE FROM {table} WHERE {id_col}=?", (duplicate_id,), save=True)

    def _merge_user_tags(self, canonical_id: int, duplicate_id: int) -> None:
        if not self._table_exists("user_tags"):
            return
        rows = self._db.sql(
            "SELECT user_id, tag, liked FROM user_tags WHERE anime_id=?",
            (duplicate_id,),
        )
        for user_id, tag, liked in rows or []:
            existing = self._db.sql(
                "SELECT tag, liked FROM user_tags WHERE anime_id=? AND user_id=? LIMIT 1",
                (canonical_id, user_id),
            )
            if not existing:
                self._db.sql(
                    "INSERT INTO user_tags(anime_id, user_id, tag, liked) VALUES(?, ?, ?, ?)",
                    (canonical_id, user_id, tag, liked),
                    save=True,
                )
                continue
            current_tag, current_liked = existing[0]
            merged_tag = current_tag if current_tag not in (None, "") else tag
            merged_liked = current_liked if current_liked is not None else liked
            self._db.sql(
                "UPDATE user_tags SET tag=?, liked=? WHERE anime_id=? AND user_id=?",
                (merged_tag, merged_liked, canonical_id, user_id),
                save=True,
            )
        self._db.sql("DELETE FROM user_tags WHERE anime_id=?", (duplicate_id,), save=True)

    def _merge_episode_progress(self, canonical_id: int, duplicate_id: int) -> None:
        if not self._table_exists("episode_progress"):
            return
        rows = self._db.sql(
            "SELECT user_id, file_id, status, position_seconds, updated_at "
            "FROM episode_progress WHERE anime_id=?",
            (duplicate_id,),
        )
        for user_id, file_id, status, position_seconds, updated_at in rows or []:
            existing = self._db.sql(
                "SELECT status, position_seconds, updated_at "
                "FROM episode_progress "
                "WHERE anime_id=? AND user_id=? AND file_id=? LIMIT 1",
                (canonical_id, user_id, file_id),
            )
            if not existing:
                self._db.sql(
                    "INSERT INTO episode_progress("
                    "anime_id, user_id, file_id, status, position_seconds, updated_at"
                    ") VALUES(?, ?, ?, ?, ?, ?)",
                    (
                        canonical_id,
                        user_id,
                        file_id,
                        status,
                        position_seconds,
                        updated_at,
                    ),
                    save=True,
                )
                continue
            cur_status, cur_pos, cur_updated = existing[0]
            if self._pick_secondary_progress(cur_pos, cur_updated, position_seconds, updated_at):
                self._db.sql(
                    "UPDATE episode_progress SET status=?, position_seconds=?, updated_at=? "
                    "WHERE anime_id=? AND user_id=? AND file_id=?",
                    (
                        status,
                        position_seconds,
                        updated_at,
                        canonical_id,
                        user_id,
                        file_id,
                    ),
                    save=True,
                )
            else:
                self._db.sql(
                    "UPDATE episode_progress SET status=? "
                    "WHERE anime_id=? AND user_id=? AND file_id=?",
                    (cur_status or status, canonical_id, user_id, file_id),
                    save=True,
                )
        self._db.sql(
            "DELETE FROM episode_progress WHERE anime_id=?",
            (duplicate_id,),
            save=True,
        )

    @staticmethod
    def _pick_secondary_progress(
        current_pos: Any,
        current_updated: Any,
        incoming_pos: Any,
        incoming_updated: Any,
    ) -> bool:
        cur_stamp = AnimeMergeService._to_timestamp(current_updated)
        inc_stamp = AnimeMergeService._to_timestamp(incoming_updated)
        if inc_stamp > cur_stamp:
            return True
        if inc_stamp < cur_stamp:
            return False
        try:
            return float(incoming_pos or 0) > float(current_pos or 0)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _to_timestamp(value: Any) -> float:
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
        text = str(value).strip()
        if not text:
            return 0.0
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    def _merge_search_memory(self, canonical_id: int, duplicate_id: int) -> None:
        if not self._table_exists("anime_torrent_search_memory"):
            return
        loser = self._db.sql(
            "SELECT query FROM anime_torrent_search_memory WHERE anime_id=? LIMIT 1",
            (duplicate_id,),
        )
        if not loser:
            return
        loser_query = loser[0][0]
        winner = self._db.sql(
            "SELECT query FROM anime_torrent_search_memory WHERE anime_id=? LIMIT 1",
            (canonical_id,),
        )
        if not winner:
            self._db.sql(
                "INSERT INTO anime_torrent_search_memory(anime_id, query) VALUES(?, ?)",
                (canonical_id, loser_query),
                save=True,
            )
        elif (winner[0][0] in (None, "")) and loser_query not in (None, ""):
            self._db.sql(
                "UPDATE anime_torrent_search_memory SET query=? WHERE anime_id=?",
                (loser_query, canonical_id),
                save=True,
            )
        self._db.sql(
            "DELETE FROM anime_torrent_search_memory WHERE anime_id=?",
            (duplicate_id,),
            save=True,
        )

    def _merge_anime_relations(self, canonical_id: int, duplicate_id: int) -> None:
        if not self._table_exists("animeRelations"):
            return
        self._remap_single_column("animeRelations", "id", canonical_id, duplicate_id)
        self._remap_single_column("animeRelations", "rel_id", canonical_id, duplicate_id)

    def _remap_single_column(
        self, table: str, column: str, canonical_id: int, duplicate_id: int
    ) -> None:
        if not self._table_exists(table):
            return
        self._db.sql(
            f"UPDATE {table} SET {column}=? WHERE {column}=?",
            (canonical_id, duplicate_id),
            save=True,
        )
