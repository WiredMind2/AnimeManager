"""Anime catalogue and settings repository adapter."""

from __future__ import annotations

import json
from typing import Any, Optional

from adapters.persistence.models import Anime
from application.services.database_manager import DatabaseManager
from domain.entities import AnimeEntity, enrich_anime_entity, from_legacy_anime
from shared.utils.anime_metadata import collect_anime_enrichment
from domain.errors import InfrastructureError, NotFoundError
from shared.config import ConfigProvider


class AnimeRepositoryAdapter:
    """Implements :class:`ports.interfaces.AnimeRepositoryPort`."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        config: ConfigProvider,
        *,
        api: Any | None = None,
    ) -> None:
        self._db_manager = db_manager
        self._config = config
        self._api = api

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

    def list_by_genre(self, genre: str, limit: int = 50) -> list[AnimeEntity]:
        results = self._db_manager.list_anime_by_genre(genre, limit=limit)
        if not results:
            return []
        return [from_legacy_anime(item) for item in results]

    def anime_row_exists(self, anime_id: int) -> bool:
        db = self._database
        if db is None:
            return False
        try:
            return bool(db.exists(anime_id, table="anime"))
        except Exception:
            return False

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
        if hasattr(anime, "metadata_keys"):
            for key in anime.metadata_keys:
                try:
                    getattr(anime, key)
                except Exception:
                    pass
        if isinstance(anime, Anime):
            if getattr(anime, "id", None) in (None, 0):
                return None
            entity = from_legacy_anime(anime)
        elif isinstance(anime, dict):
            if not anime.get("id"):
                return None
            entity = from_legacy_anime(anime)
        else:
            return None

        enrichment = collect_anime_enrichment(anime, db)
        return enrich_anime_entity(entity, **enrichment)

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

    def _relation_row_to_dict(self, row: dict) -> dict:
        rel_id = row.get("rel_id")
        if rel_id is None:
            rel_id = row.get("related_id")
        relation_name = row.get("name") or row.get("relation")
        media_type = row.get("type") or row.get("media_type") or "anime"
        return {
            "id": row.get("id"),
            "rel_id": rel_id,
            "anime_id": rel_id,
            "type": media_type,
            "media_type": media_type,
            "name": relation_name,
            "relation": relation_name,
            "title": row.get("title"),
            "picture": row.get("picture"),
            "status": row.get("status"),
            "date_from": row.get("date_from"),
            "episodes": row.get("episodes"),
        }

    def get_relations(self, anime_id: int, relation_type: str = "anime") -> list[dict]:
        db = self._database
        if db is None:
            return []
        try:
            rows = db.sql(
                (
                    "SELECT r.id, r.rel_id, r.type, r.name, "
                    "a.title, a.picture, a.status, a.date_from, a.episodes "
                    "FROM animeRelations AS r "
                    "LEFT JOIN anime AS a ON a.id = r.rel_id "
                    "WHERE r.id=? AND r.type=?"
                ),
                (anime_id, relation_type),
                to_dict=True,
            )
        except Exception:
            try:
                rows = db.sql(
                    (
                        "SELECT r.id, r.related_id AS rel_id, r.type, r.name, "
                        "a.title, a.picture, a.status, a.date_from, a.episodes "
                        "FROM animeRelations AS r "
                        "LEFT JOIN anime AS a ON a.id = r.related_id "
                        "WHERE r.id=? AND r.type=?"
                    ),
                    (anime_id, relation_type),
                    to_dict=True,
                )
            except Exception:
                return []
        return [
            self._relation_row_to_dict(row)
            for row in (rows or [])
            if row and (row.get("rel_id") is not None or row.get("related_id") is not None)
        ]

    def get_anime_torrents(self, anime_id: int) -> list[dict]:
        db = self._database
        if db is None:
            return []
        try:
            rows = db.sql(
                (
                    "SELECT t.hash, t.name, t.trackers, t.save_path, t.status "
                    "FROM torrents AS t "
                    "JOIN torrentsIndex AS i ON LOWER(i.value) = LOWER(t.hash) "
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

    def _require_api(self) -> Any:
        if self._api is None:
            raise InfrastructureError("Metadata API not configured")
        return self._api

    def _character_row_to_dict(self, row: dict, *, role: Optional[str] = None) -> dict:
        description = row.get("description") or row.get("desc")
        entry = {
            "id": row.get("id"),
            "name": row.get("name"),
            "picture": row.get("picture"),
            "description": description,
        }
        if role is not None:
            entry["role"] = role
        return entry

    def get_characters(self, anime_id: int) -> list[dict]:
        db = self._database
        if db is None:
            return []
        try:
            rows = db.sql(
                (
                    "SELECT c.id, c.name, c.picture, c.description, cr.role "
                    "FROM characterRelations AS cr "
                    "JOIN characters AS c ON c.id = cr.id "
                    "WHERE cr.anime_id=? "
                    "ORDER BY c.name"
                ),
                (anime_id,),
                to_dict=True,
            )
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to load characters for anime {anime_id}: {exc}"
            ) from exc
        return [
            self._character_row_to_dict(row, role=row.get("role"))
            for row in (rows or [])
            if row and row.get("id") is not None
        ]

    def get_character(self, character_id: int) -> Optional[dict]:
        db = self._database
        if db is None:
            return None
        try:
            row = db.get(character_id, table="characters")
        except Exception:
            row = None
        if not row:
            return None

        if hasattr(row, "items"):
            base = dict(row)
        else:
            base = {
                "id": getattr(row, "id", character_id),
                "name": getattr(row, "name", None),
                "picture": getattr(row, "picture", None),
                "description": getattr(row, "desc", None)
                or getattr(row, "description", None),
            }

        try:
            rel_rows = db.sql(
                (
                    "SELECT cr.anime_id, cr.role, a.title "
                    "FROM characterRelations AS cr "
                    "LEFT JOIN anime AS a ON a.id = cr.anime_id "
                    "WHERE cr.id=?"
                ),
                (character_id,),
                to_dict=True,
            )
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to load character animeography for {character_id}: {exc}"
            ) from exc

        animeography = []
        for rel in rel_rows or []:
            if not rel:
                continue
            animeography.append(
                {
                    "anime_id": rel.get("anime_id"),
                    "title": rel.get("title"),
                    "role": rel.get("role"),
                }
            )

        payload = self._character_row_to_dict(base)
        payload["animeography"] = animeography
        return payload

    def get_anime_pictures(self, anime_id: int) -> list[dict]:
        db = self._database
        if db is None:
            return []
        try:
            rows = db.sql(
                "SELECT url, size FROM pictures WHERE id=?",
                (anime_id,),
                to_dict=True,
            )
        except Exception as exc:
            message = str(exc).lower()
            if "locked" in message or "deadlock" in message:
                return []
            raise InfrastructureError(
                f"Failed to load pictures for anime {anime_id}: {exc}"
            ) from exc
        return [
            {"url": row.get("url"), "size": row.get("size")}
            for row in (rows or [])
            if row and row.get("url")
        ]

    def _resolve_character_role(self, character: Any, role: Optional[str] = None) -> str:
        if role:
            return str(role).strip().lower() or "unknown"
        if hasattr(character, "role"):
            value = getattr(character, "role", None)
            if value:
                return str(value).strip().lower()
        if isinstance(character, dict):
            value = character.get("role")
            if value:
                return str(value).strip().lower()
        return "unknown"

    def _upsert_character(
        self,
        character: Any,
        *,
        anime_id: Optional[int] = None,
        role: Optional[str] = None,
    ) -> None:
        if character is None:
            return

        if hasattr(character, "id"):
            char_id = getattr(character, "id", None)
            name = getattr(character, "name", None)
            picture = getattr(character, "picture", None)
            description = getattr(character, "desc", None) or getattr(
                character, "description", None
            )
            animeography = getattr(character, "animeography", None)
        elif isinstance(character, dict):
            char_id = character.get("id")
            name = character.get("name")
            picture = character.get("picture")
            description = character.get("desc") or character.get("description")
            animeography = character.get("animeography")
        else:
            return

        if char_id is None:
            return

        if callable(animeography):
            try:
                animeography = animeography()
            except Exception:
                animeography = None

        if anime_id is not None:
            if not isinstance(animeography, dict):
                animeography = {}
            if anime_id not in animeography:
                animeography[anime_id] = self._resolve_character_role(character, role)

        db = self._database
        if db is None:
            raise InfrastructureError("Database not initialized")

        try:
            with db.get_lock():
                exists = db.sql(
                    "SELECT EXISTS(SELECT 1 FROM characters WHERE id=?)",
                    (int(char_id),),
                )
                if bool(exists[0][0]):
                    db.sql(
                        (
                            "UPDATE characters "
                            "SET name=?, picture=?, description=? "
                            "WHERE id=?"
                        ),
                        (name, picture, description, int(char_id)),
                        save=True,
                    )
                else:
                    db.sql(
                        (
                            "INSERT INTO characters(id, name, picture, description) "
                            "VALUES (?, ?, ?, ?)"
                        ),
                        (int(char_id), name, picture, description),
                        save=True,
                    )

                if isinstance(animeography, dict):
                    for anime_id, role in animeography.items():
                        exists_rel = db.sql(
                            (
                                "SELECT EXISTS("
                                "SELECT 1 FROM characterRelations "
                                "WHERE id=? AND anime_id=?"
                                ")"
                            ),
                            (int(char_id), int(anime_id)),
                        )
                        if bool(exists_rel[0][0]):
                            db.sql(
                                (
                                    "UPDATE characterRelations "
                                    "SET role=? WHERE id=? AND anime_id=?"
                                ),
                                (role, int(char_id), int(anime_id)),
                                save=True,
                            )
                        else:
                            db.sql(
                                (
                                    "INSERT INTO characterRelations(id, anime_id, role) "
                                    "VALUES (?, ?, ?)"
                                ),
                                (int(char_id), int(anime_id), role),
                                save=True,
                            )
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to upsert character {char_id}: {exc}"
            ) from exc

    def refresh_anime_characters(self, anime_id: int) -> list[dict]:
        api = self._require_api()
        try:
            characters = api.animeCharacters(anime_id)
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to refresh characters for anime {anime_id}: {exc}"
            ) from exc
        for character in characters or []:
            self._upsert_character(character, anime_id=anime_id)
        return self.get_characters(anime_id)

    def refresh_character(self, character_id: int) -> dict:
        api = self._require_api()
        try:
            character = api.character(character_id)
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to refresh character {character_id}: {exc}"
            ) from exc
        if not character:
            raise NotFoundError(f"Character with id={character_id} not found")
        self._upsert_character(character)
        payload = self.get_character(character_id)
        if payload is None:
            raise NotFoundError(f"Character with id={character_id} not found")
        return payload

    def refresh_anime_pictures(self, anime_id: int) -> list[dict]:
        api = self._require_api()
        try:
            pictures = api.animePictures(anime_id)
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to refresh pictures for anime {anime_id}: {exc}"
            ) from exc

        normalized: list[dict] = []
        for pic in pictures or []:
            if not isinstance(pic, dict):
                getter = getattr(pic, "get", None)
                if callable(getter):
                    for size in ("small", "medium", "large", "original"):
                        url = getter(size)
                        if url:
                            normalized.append({"url": url, "size": size})
                continue
            if "url" in pic and pic.get("url"):
                normalized.append(
                    {"url": pic["url"], "size": pic.get("size") or "medium"}
                )
                continue
            jpg = pic.get("jpg") if isinstance(pic.get("jpg"), dict) else None
            if jpg:
                for size_key, size_label in (
                    ("small_image_url", "small"),
                    ("image_url", "medium"),
                    ("large_image_url", "large"),
                ):
                    url = jpg.get(size_key)
                    if url:
                        normalized.append({"url": url, "size": size_label})

        if normalized:
            try:
                api.save_pictures(anime_id, normalized)
            except Exception as exc:
                raise InfrastructureError(
                    f"Failed to persist pictures for anime {anime_id}: {exc}"
                ) from exc
        return self.get_anime_pictures(anime_id)
