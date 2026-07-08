"""User tag and episode progress persistence."""

from __future__ import annotations

import time
from typing import Any

from domain.errors import InfrastructureError


class UserActionsRepository:
    """Implements :class:`ports.interfaces.UserActionsPort`."""

    _ALLOWED_COLUMNS = ("tag", "liked")
    _EPISODE_STATUSES = frozenset({"UNSEEN", "IN_PROGRESS", "SEEN"})

    def __init__(self, database: Any) -> None:
        self._database = database

    def _upsert_column(
        self,
        anime_id: int,
        user_id: int,
        *,
        column: str,
        value: Any,
        action_label: str,
    ) -> None:
        if column not in self._ALLOWED_COLUMNS:
            raise InfrastructureError(
                f"Refusing to write to unsupported column: {column}"
            )
        db = self._database
        try:
            with db.get_lock():
                existing = db.sql(
                    "SELECT 1 FROM user_tags WHERE anime_id=? AND user_id=? LIMIT 1",
                    (anime_id, user_id),
                )
                if existing:
                    db.sql(
                        f"UPDATE user_tags SET {column}=? "
                        "WHERE anime_id=? AND user_id=?",
                        (value, anime_id, user_id),
                        save=True,
                    )
                else:
                    db.sql(
                        "INSERT INTO user_tags "
                        f"(anime_id, user_id, {column}) VALUES (?, ?, ?)",
                        (anime_id, user_id, value),
                        save=True,
                    )
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to update {action_label}: {exc}"
            ) from exc

    def set_tag(self, anime_id: int, tag: str, user_id: int) -> None:
        self._upsert_column(
            anime_id, user_id, column="tag", value=tag, action_label="tag"
        )

    def set_like(self, anime_id: int, liked: bool, user_id: int) -> None:
        self._upsert_column(
            anime_id,
            user_id,
            column="liked",
            value=1 if liked else 0,
            action_label="like flag",
        )

    def mark_seen(self, anime_id: int, file_name: str, user_id: int) -> None:
        self.set_tag(anime_id, "SEEN", user_id)
        clean_name = str(file_name or "").strip()
        if not clean_name:
            return
        db = self._database
        try:
            with db.get_lock():
                db.sql(
                    "UPDATE anime SET last_seen=? WHERE id=?",
                    (clean_name, anime_id),
                    save=True,
                )
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to persist last_seen for anime {anime_id}: {exc}"
            ) from exc

    def get_user_state(self, anime_id: int, user_id: int) -> dict:
        db = self._database
        try:
            rows = db.sql(
                "SELECT tag, liked FROM user_tags "
                "WHERE anime_id=? AND user_id=?",
                (anime_id, user_id),
            )
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to load user state: {exc}"
            ) from exc
        if not rows:
            return {"tag": "NONE", "liked": False}

        tag: str | None = None
        liked: int | None = None
        for row in rows:
            row_tag = row[0] if len(row) > 0 else None
            row_liked = row[1] if len(row) > 1 else None
            if row_tag is not None:
                tag = row_tag
            if row_liked is not None:
                liked = row_liked
        return {"tag": tag or "NONE", "liked": bool(liked)}

    def _ensure_episode_progress_table(self) -> None:
        db = self._database
        ddl = (
            "CREATE TABLE IF NOT EXISTS episode_progress ("
            "anime_id INTEGER NOT NULL, "
            "user_id INTEGER NOT NULL, "
            "file_id TEXT NOT NULL, "
            "status TEXT NOT NULL, "
            "position_seconds REAL, "
            "updated_at REAL NOT NULL, "
            "PRIMARY KEY (anime_id, user_id, file_id))"
        )
        try:
            with db.get_lock():
                db.sql(ddl, (), save=True)
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to ensure episode_progress schema: {exc}"
            ) from exc

    def get_episode_progress_map(
        self, anime_id: int, user_id: int
    ) -> dict[str, dict[str, Any]]:
        self._ensure_episode_progress_table()
        db = self._database
        try:
            rows = db.sql(
                "SELECT file_id, status, position_seconds FROM episode_progress "
                "WHERE anime_id=? AND user_id=?",
                (anime_id, user_id),
            )
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to load episode progress: {exc}"
            ) from exc
        out: dict[str, dict[str, Any]] = {}
        for row in rows or []:
            if not row or len(row) < 2:
                continue
            fid = str(row[0] or "").strip()
            if not fid:
                continue
            st = str(row[1] or "UNSEEN").upper()
            pos_raw = row[2] if len(row) > 2 else None
            try:
                pos = float(pos_raw) if pos_raw is not None else None
            except (TypeError, ValueError):
                pos = None
            out[fid] = {"status": st, "position_seconds": pos}
        return out

    def set_episode_progress(
        self,
        anime_id: int,
        user_id: int,
        file_id: str,
        status: str,
        position_seconds: float | None = None,
    ) -> None:
        self._ensure_episode_progress_table()
        fid = str(file_id or "").strip()
        if not fid:
            raise InfrastructureError("file_id is required for episode progress")
        status_u = str(status or "UNSEEN").upper()
        if status_u not in self._EPISODE_STATUSES:
            raise InfrastructureError(f"Invalid episode status: {status!r}")
        if position_seconds is None:
            pos_val = None
        else:
            try:
                pos_val = float(position_seconds)
            except (TypeError, ValueError):
                pos_val = None
            if pos_val is not None and pos_val < 0:
                pos_val = 0.0
        now = time.time()
        db = self._database
        try:
            with db.get_lock():
                existing = db.sql(
                    "SELECT 1 FROM episode_progress WHERE anime_id=? AND user_id=? AND file_id=? LIMIT 1",
                    (anime_id, user_id, fid),
                )
                if existing:
                    db.sql(
                        "UPDATE episode_progress SET status=?, position_seconds=?, updated_at=? "
                        "WHERE anime_id=? AND user_id=? AND file_id=?",
                        (status_u, pos_val, now, anime_id, user_id, fid),
                        save=True,
                    )
                else:
                    db.sql(
                        "INSERT INTO episode_progress "
                        "(anime_id, user_id, file_id, status, position_seconds, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (anime_id, user_id, fid, status_u, pos_val, now),
                        save=True,
                    )
        except InfrastructureError:
            raise
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to save episode progress: {exc}"
            ) from exc

    def delete_episode_progress(
        self, anime_id: int, user_id: int, file_id: str
    ) -> None:
        self._ensure_episode_progress_table()
        fid = str(file_id or "").strip()
        if not fid:
            return
        db = self._database
        try:
            with db.get_lock():
                db.sql(
                    "DELETE FROM episode_progress WHERE anime_id=? AND user_id=? AND file_id=?",
                    (anime_id, user_id, fid),
                    save=True,
                )
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to delete episode progress: {exc}"
            ) from exc
