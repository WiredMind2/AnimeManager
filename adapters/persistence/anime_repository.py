"""Anime catalogue and settings repository adapter."""

from __future__ import annotations

import json
from typing import Any, Optional

from adapters.persistence.models import Anime
from application.services.database_manager import DatabaseManager
from domain.entities import AnimeEntity, from_legacy_anime
from domain.errors import InfrastructureError
from shared.config import ConfigProvider


class AnimeRepositoryAdapter:
    """Implements :class:`ports.interfaces.AnimeRepositoryPort`."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        config: ConfigProvider,
    ) -> None:
        self._db_manager = db_manager
        self._config = config

    @property
    def _database(self):
        return self._db_manager.get_database()

    def search(self, query: str, limit: int = 50) -> list[AnimeEntity]:
        results = self._db_manager.search_anime(query, limit=limit)
        if not results:
            return []
        return [from_legacy_anime(item) for item in results]

    def list_anime(
        self,
        criteria: str,
        list_start: int,
        list_stop: int,
        hide_rated: Optional[bool],
        user_id: Optional[int],
    ) -> tuple[list[AnimeEntity], bool]:
        anime_list, next_page = self._db_manager.get_anime_list(
            criteria=criteria,
            listrange=(list_start, list_stop),
            hide_rated=hide_rated,
            user_id=user_id,
        )
        if not anime_list:
            return [], False
        return (
            [from_legacy_anime(item) for item in anime_list],
            next_page is not None,
        )

    def list_by_airing_season(
        self,
        year: int,
        season: str,
        limit: int = 50,
    ) -> list[AnimeEntity]:
        results = self._db_manager.list_anime_by_airing_season(
            year,
            season,
            limit=limit,
        )
        if not results:
            return []
        return [from_legacy_anime(item) for item in results]

    def get_anime(self, anime_id: int) -> Optional[AnimeEntity]:
        db = self._database
        if db is None:
            return None
        try:
            anime = db.get(anime_id, table="anime")
        except Exception:
            return None
        if not anime:
            return None
        if isinstance(anime, Anime):
            return from_legacy_anime(anime)
        if isinstance(anime, dict):
            return from_legacy_anime(anime)
        return None

    def get_search_terms(self, anime_id: int) -> list[str]:
        db = self._database
        if db is None:
            return []
        try:
            rows = db.sql(
                "SELECT value FROM title_synonyms WHERE id=?",
                (anime_id,),
            )
        except Exception:
            return []
        return [str(row[0]).strip() for row in rows if row and row[0]]

    def add_search_term(self, anime_id: int, term: str) -> bool:
        db = self._database
        if db is None:
            return False
        try:
            with db.get_lock():
                exists = db.sql(
                    "SELECT EXISTS(SELECT 1 FROM title_synonyms WHERE id=? AND value=?)",
                    (anime_id, term),
                )
                if bool(exists[0][0]):
                    return False
                db.sql(
                    "INSERT INTO title_synonyms(id, value) VALUES (?, ?)",
                    (anime_id, term),
                    save=True,
                )
                return True
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to add search term: {exc}"
            ) from exc

    def remove_search_term(self, anime_id: int, term: str) -> bool:
        db = self._database
        if db is None:
            return False
        try:
            with db.get_lock():
                db.sql(
                    "DELETE FROM title_synonyms WHERE id=? AND value=?",
                    (anime_id, term),
                    save=True,
                )
                return True
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to remove search term: {exc}"
            ) from exc

    def _ensure_disabled_search_titles_table(self) -> None:
        db = self._database
        if db is None:
            raise InfrastructureError("Database not initialized")
        ddl = (
            "CREATE TABLE IF NOT EXISTS disabled_search_titles ("
            "anime_id INTEGER NOT NULL, "
            "value TEXT NOT NULL, "
            "PRIMARY KEY (anime_id, value))"
        )
        try:
            with db.get_lock():
                db.sql(ddl, (), save=True)
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to ensure disabled_search_titles schema: {exc}"
            ) from exc

    def get_disabled_search_titles(self, anime_id: int) -> list[str]:
        self._ensure_disabled_search_titles_table()
        db = self._database
        try:
            rows = db.sql(
                "SELECT value FROM disabled_search_titles WHERE anime_id=?",
                (anime_id,),
            )
        except Exception:
            return []
        return [str(row[0]).strip() for row in rows if row and row[0]]

    def disable_search_title(self, anime_id: int, title: str) -> bool:
        self._ensure_disabled_search_titles_table()
        db = self._database
        try:
            with db.get_lock():
                exists = db.sql(
                    "SELECT EXISTS("
                    "SELECT 1 FROM disabled_search_titles "
                    "WHERE anime_id=? AND value=?)",
                    (anime_id, title),
                )
                if bool(exists[0][0]):
                    return False
                db.sql(
                    "INSERT INTO disabled_search_titles(anime_id, value) "
                    "VALUES (?, ?)",
                    (anime_id, title),
                    save=True,
                )
                return True
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to disable search title: {exc}"
            ) from exc

    def enable_search_title(self, anime_id: int, title: str) -> bool:
        self._ensure_disabled_search_titles_table()
        db = self._database
        try:
            with db.get_lock():
                db.sql(
                    "DELETE FROM disabled_search_titles "
                    "WHERE anime_id=? AND value=?",
                    (anime_id, title),
                    save=True,
                )
                return True
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to enable search title: {exc}"
            ) from exc

    def get_settings(self) -> dict:
        return dict(self._config.settings)

    def update_settings(self, updates: dict) -> dict:
        updated = self._config.update_settings(updates)
        return updated

    def get_relations(self, anime_id: int, relation_type: str = "anime") -> list[dict]:
        db = self._database
        if db is None:
            return []
        try:
            rows = db.sql(
                "SELECT * FROM animeRelations WHERE id=? AND type=?",
                (anime_id, relation_type),
                to_dict=True,
            )
        except Exception:
            return []
        return list(rows or [])

    def get_anime_torrents(self, anime_id: int) -> list[dict]:
        db = self._database
        if db is None:
            return []
        try:
            rows = db.sql(
                (
                    "SELECT t.hash, t.name, t.trackers, t.save_path, t.status "
                    "FROM torrents AS t "
                    "JOIN torrentsIndex AS i ON i.value = t.hash "
                    "WHERE i.id=?"
                ),
                (anime_id,),
            )
        except Exception:
            return []
        out: list[dict] = []
        for row in rows or []:
            if not row:
                continue
            try:
                hash_ = row[0]
                name = row[1]
                trackers_raw = row[2] if len(row) > 2 else None
                save_path = row[3] if len(row) > 3 else None
                status = row[4] if len(row) > 4 else None
            except (TypeError, IndexError):
                continue
            entry: dict = {"hash": hash_, "name": name}
            if save_path:
                entry["path"] = save_path
                entry["save_path"] = save_path
            if status is not None:
                entry["status"] = str(status).strip().lower()
            if isinstance(trackers_raw, str) and trackers_raw:
                try:
                    entry["trackers"] = json.loads(trackers_raw)
                except Exception:  # noqa: BLE001
                    entry["trackers"] = trackers_raw
            out.append(entry)
        return out
