"""Legacy adapters runtime implemented through explicit composition."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any, Optional

try:
    from ..api import AnimeAPI
    from adapters.legacy.legacy_classes import Anime
    from application.services.database_manager import DatabaseManager
    from application.services.download_manager import DownloadManager
    from shared.config.constants import Constants
    from shared.config.getters import Getters
except ImportError:  # pragma: no cover - packaged install fallback
    from AnimeManager.adapters.api import AnimeAPI  # type: ignore
    from AnimeManager.adapters.legacy.legacy_classes import Anime  # type: ignore
    from AnimeManager.application.services.database_manager import DatabaseManager  # type: ignore
    from AnimeManager.application.services.download_manager import DownloadManager  # type: ignore
    from AnimeManager.shared.config.constants import Constants  # type: ignore
    from AnimeManager.shared.config.getters import Getters  # type: ignore

try:
    from shared.config import ConfigProvider
    from shared.telemetry import LoggerService
except ImportError:  # pragma: no cover - packaged install fallback
    from AnimeManager.shared.config import ConfigProvider  # type: ignore
    from AnimeManager.shared.telemetry import LoggerService  # type: ignore

try:
    from adapters.search import SearchFacade
except ImportError:  # pragma: no cover - packaged install fallback
    from AnimeManager.adapters.search import SearchFacade  # type: ignore

from domain.entities import AnimeEntity, from_legacy_anime
from domain.errors import InfrastructureError
from adapters.legacy.metadata_provider_adapter import LegacyMetadataProviderAdapter


class _LegacyRuntimeState:
    """Bridges legacy runtime attributes without multi-inheritance."""

    def __init__(
        self,
        *,
        constants: Constants,
        config: ConfigProvider,
        logger: LoggerService,
        api: Optional[Any] = None,
    ) -> None:
        self._constants = constants
        self._config = config
        self._logger = logger
        self.__dict__.update(constants.__dict__)
        self.database = Getters.getDatabase(self)
        self.api = api if api is not None else AnimeAPI(apis="all")
        Getters.getFileManager(self)
        Getters.getTorrentManager(self)

    def setSettings(self, settings):  # noqa: N802 - legacy naming
        updated = self._config.update_settings(settings)
        self.settings = updated
        try:
            self._constants.settings = updated
        except Exception:  # pragma: no cover
            pass
        return updated

    def log(self, *_args, **_kwargs):
        try:
            self._logger.log(*_args, **_kwargs) if _args else None
        except Exception:  # pragma: no cover
            pass
        return None

    def __getattr__(self, item: str):
        attr = getattr(self._constants, item, None)
        if attr is not None:
            return attr
        getter_fn = getattr(Getters, item, None)
        if callable(getter_fn):
            return lambda *args, **kwargs: getter_fn(self, *args, **kwargs)
        raise AttributeError(item)


class LegacyRuntime:
    """Composed runtime context used by adapters."""

    def __init__(
        self,
        *,
        config: Optional[ConfigProvider] = None,
        logger: Optional[LoggerService] = None,
        constants: Optional[Constants] = None,
        state: Optional[_LegacyRuntimeState] = None,
        api: Optional[Any] = None,
    ) -> None:
        self._constants = constants if constants is not None else Constants()
        self._config = config if config is not None else ConfigProvider(constants=self._constants)
        self._logger = logger if logger is not None else LoggerService.from_defaults()
        self._state = (
            state
            if state is not None
            else _LegacyRuntimeState(
                constants=self._constants,
                config=self._config,
                logger=self._logger,
                api=api,
            )
        )

    @property
    def database(self):
        return self._state.database

    @property
    def api(self):
        return self._state.api

    @property
    def fm(self):
        return getattr(self._state, "fm", None)

    @property
    def tm(self):
        return getattr(self._state, "tm", None)

    @property
    def settings(self):
        return getattr(self._state, "settings", {})

    @settings.setter
    def settings(self, value):  # pragma: no cover - mirror legacy mutation
        self._state.settings = value

    @property
    def settingsPath(self) -> str:  # noqa: N802 - legacy naming
        return self._config.settings_path

    @property
    def config(self) -> ConfigProvider:
        return self._config

    @property
    def logger(self) -> LoggerService:
        return self._logger

    def setSettings(self, settings):  # noqa: N802 - legacy compatibility
        return self._state.setSettings(settings)

    def log(self, *_args, **_kwargs):
        return self._state.log(*_args, **_kwargs)

    def __getattr__(self, item: str):
        state = self.__dict__.get("_state")
        if state is None:
            raise AttributeError(item)
        return getattr(state, item)


class LegacyAnimeRepositoryAdapter:
    """Adapter around DatabaseManager and raw DB helpers."""

    def __init__(self, runtime: LegacyRuntime) -> None:
        self._runtime = runtime
        self._db_manager = DatabaseManager()
        self._db_manager.set_database(runtime.database)
        self._torrent_search_memory_ready = False

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

    def get_anime(self, anime_id: int) -> Optional[AnimeEntity]:
        try:
            anime = self._runtime.database.get(anime_id, table="anime")
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
        try:
            rows = self._runtime.database.sql(
                "SELECT value FROM title_synonyms WHERE id=?",
                (anime_id,),
            )
        except Exception:
            return []
        return [str(row[0]).strip() for row in rows if row and row[0]]

    def add_search_term(self, anime_id: int, term: str) -> bool:
        try:
            with self._runtime.database.get_lock():
                exists = self._runtime.database.sql(
                    "SELECT EXISTS(SELECT 1 FROM title_synonyms WHERE id=? AND value=?)",
                    (anime_id, term),
                )
                if bool(exists[0][0]):
                    return False
                self._runtime.database.sql(
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
        try:
            with self._runtime.database.get_lock():
                self._runtime.database.sql(
                    "DELETE FROM title_synonyms WHERE id=? AND value=?",
                    (anime_id, term),
                    save=True,
                )
                return True
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to remove search term: {exc}"
            ) from exc

    def _ensure_torrent_search_memory_table(self) -> None:
        if self._torrent_search_memory_ready:
            return
        self._runtime.database.sql(
            (
                "CREATE TABLE IF NOT EXISTS anime_torrent_search_memory ("
                "anime_id INTEGER NOT NULL PRIMARY KEY, "
                "query TEXT NOT NULL DEFAULT ''"
                ")"
            ),
            (),
            save=True,
        )
        self._torrent_search_memory_ready = True

    def get_last_torrent_search_query(self, anime_id: int) -> Optional[str]:
        try:
            self._ensure_torrent_search_memory_table()
            rows = self._runtime.database.sql(
                "SELECT query FROM anime_torrent_search_memory WHERE anime_id=?",
                (anime_id,),
            )
        except Exception:
            return None
        if not rows or not rows[0] or rows[0][0] is None:
            return None
        out = str(rows[0][0]).strip()
        return out if out else None

    def set_last_torrent_search_query(self, anime_id: int, query: str) -> None:
        clean = (query or "").strip()[:2000]
        if not clean:
            return
        try:
            self._ensure_torrent_search_memory_table()
            with self._runtime.database.get_lock():
                db = self._runtime.database
                exists = db.sql(
                    "SELECT 1 FROM anime_torrent_search_memory WHERE anime_id=? LIMIT 1",
                    (anime_id,),
                )
                if exists:
                    db.sql(
                        "UPDATE anime_torrent_search_memory SET query=? WHERE anime_id=?",
                        (clean, anime_id),
                        save=True,
                    )
                else:
                    db.sql(
                        "INSERT INTO anime_torrent_search_memory(anime_id, query) VALUES(?,?)",
                        (anime_id, clean),
                        save=True,
                    )
        except Exception:
            return

    def get_settings(self) -> dict:
        settings = getattr(self._runtime, "settings", None)
        if isinstance(settings, dict):
            return settings
        return dict(self._runtime.config.settings)

    def update_settings(self, updates: dict) -> dict:
        return self._runtime.setSettings(updates)

    def get_relations(self, anime_id: int, relation_type: str = "anime") -> list[dict]:
        try:
            rows = self._runtime.database.sql(
                "SELECT * FROM animeRelations WHERE id=? AND type=?",
                (anime_id, relation_type),
                to_dict=True,
            )
        except Exception:
            return []
        return list(rows or [])

    def list_anime_characters(self, anime_id: int) -> list[dict]:
        """Join ``characterRelations`` with ``characters`` for this anime."""
        try:
            rel_rows = self._runtime.database.sql(
                "SELECT id, role FROM characterRelations WHERE anime_id=?",
                (int(anime_id),),
                to_dict=True,
            )
        except Exception:
            return []
        if not rel_rows:
            return []
        ids: list[int] = []
        for r in rel_rows:
            cid = r.get("id")
            if cid is None:
                continue
            try:
                ids.append(int(cid))
            except (TypeError, ValueError):
                continue
        if not ids:
            return []
        uniq = sorted(set(ids))
        placeholders = ",".join("?" * len(uniq))
        try:
            char_rows = self._runtime.database.sql(
                f"SELECT * FROM characters WHERE id IN ({placeholders})",
                tuple(uniq),
                to_dict=True,
            )
        except Exception:
            char_rows = []
        by_id: dict[int, dict] = {}
        for row in char_rows or []:
            if not isinstance(row, dict):
                continue
            cid = row.get("id")
            if cid is None:
                continue
            try:
                by_id[int(cid)] = dict(row)
            except (TypeError, ValueError):
                continue
        out: list[dict] = []
        for rel in rel_rows:
            cid_raw = rel.get("id")
            if cid_raw is None:
                continue
            try:
                cid = int(cid_raw)
            except (TypeError, ValueError):
                continue
            char = by_id.get(cid, {})
            synopsis = char.get("desc") or char.get("description")
            out.append(
                {
                    "id": cid,
                    "name": char.get("name") or f"Character #{cid}",
                    "picture": char.get("picture"),
                    "role": rel.get("role"),
                    "synopsis": synopsis,
                }
            )

        def _sort_key(d: dict) -> tuple[int, str]:
            role = str(d.get("role") or "").strip().lower()
            if role in ("main", "protagonist"):
                rank = 0
            elif "support" in role:
                rank = 2
            else:
                rank = 1
            return (rank, (d.get("name") or "").strip().lower())

        out.sort(key=_sort_key)
        return out

    def get_anime_torrents(self, anime_id: int) -> list[dict]:
        """Return every torrent persisted for ``anime_id``.

        Reads ``torrents`` joined with ``torrentsIndex`` so the per-anime
        download history survives across sessions even if the in-memory
        download manager has nothing in flight. Each row is a plain
        dict so the application layer never imports legacy classes.
        """
        try:
            rows = self._runtime.database.sql(
                (
                    "SELECT t.hash, t.name, t.trackers "
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
            except (TypeError, IndexError):
                continue
            entry: dict = {"hash": hash_, "name": name}
            if isinstance(trackers_raw, str) and trackers_raw:
                try:
                    import json as _json

                    entry["trackers"] = _json.loads(trackers_raw)
                except Exception:  # noqa: BLE001
                    entry["trackers"] = trackers_raw
            out.append(entry)
        return out

    def delete_anime(self, anime_id: int) -> bool:
        try:
            self._runtime.database.remove(None, id=anime_id, table="anime")
            return True
        except Exception:
            return False

    def get_anime_folder(self, anime_id: int) -> str:
        try:
            return str(self._runtime.getFolder(id=anime_id) or "")
        except Exception:
            return ""


class LegacyMediaLibraryAdapter:
    """Adapter exposing local episode files from the legacy runtime."""

    _VIDEO_SUFFIXES = frozenset({".mkv", ".mp4", ".avi"})

    def __init__(
        self,
        runtime: LegacyRuntime,
        *,
        download_port: Any | None = None,
    ) -> None:
        self._runtime = runtime
        self._download_port = download_port

    def _canonical_path_key(self, path: str) -> str:
        try:
            return os.path.normcase(os.path.realpath(os.path.normpath(path)))
        except OSError:
            return os.path.normcase(os.path.normpath(path))

    def _coerce_episode_dicts(self, raw: Any) -> list[dict[str, Any]]:
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
        return []

    def _collect_torrent_save_paths(self, anime_id: int) -> list[str]:
        """Paths reported by the download/torrent layer for this anime.

        The library scanner only walks ``getFolder(anime_id)``, which can
        miss real files when the on-disk layout or trailing ``- <id>``
        folder name does not match the catalogued id. Torrent rows still
        carry the client-reported save path, so we union those here.
        """
        port = self._download_port
        if port is None:
            return []
        candidates: list[str] = []
        try:
            for row in port.get_active_downloads() or []:
                if not isinstance(row, dict):
                    continue
                try:
                    if int(row.get("anime_id") or 0) != int(anime_id):
                        continue
                except (TypeError, ValueError):
                    continue
                p = str(row.get("path") or "").strip()
                if p:
                    candidates.append(p)
        except Exception:
            pass
        getter = getattr(port, "get_torrents_overview", None)
        if callable(getter):
            try:
                overview = getter() or {}
            except Exception:
                overview = {}
            for rows in overview.values():
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    try:
                        if int(row.get("anime_id") or 0) != int(anime_id):
                            continue
                    except (TypeError, ValueError):
                        continue
                    p = str(row.get("path") or "").strip()
                    if p:
                        candidates.append(p)
        ordered: list[str] = []
        seen: set[str] = set()
        for raw in candidates:
            norm = os.path.normpath(raw)
            key = self._canonical_path_key(norm)
            if key in seen:
                continue
            seen.add(key)
            ordered.append(norm)
        return ordered

    def _rows_from_scan_dicts(
        self, episodes: list[dict[str, Any]], start_idx: int
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for offset, item in enumerate(episodes):
            idx = start_idx + offset
            path = str(item.get("path") or "").strip()
            if not path:
                continue
            title = str(item.get("title") or os.path.basename(path)).strip()
            digest = hashlib.sha1(path.encode("utf-8")).hexdigest()[:16]
            file_id = f"ep-{idx:04d}-{digest}"
            size_bytes: int | None
            try:
                size_bytes = os.path.getsize(path)
            except OSError:
                size_bytes = None
            out.append(
                {
                    "file_id": file_id,
                    "path": path,
                    "title": title,
                    "size_bytes": size_bytes,
                    "season": _safe_int(item.get("season")),
                    "episode": _safe_int(item.get("episode")),
                }
            )
        return out

    def _torrent_save_root_norms(self, anime_id: int) -> list[str]:
        roots: list[str] = []
        for p in self._collect_torrent_save_paths(anime_id):
            base = p
            if os.path.isfile(base):
                base = os.path.dirname(base)
            try:
                roots.append(
                    os.path.normcase(os.path.realpath(os.path.normpath(base)))
                )
            except OSError:
                roots.append(os.path.normcase(os.path.normpath(base)))
        out: list[str] = []
        seen: set[str] = set()
        for r in roots:
            if r and r not in seen:
                seen.add(r)
                out.append(r)
        return out

    def _path_allowed_for_delete(self, anime_id: int, path_norm: str) -> bool:
        folder = self._runtime.getFolder(id=anime_id) or ""
        fm = self._runtime.fm
        if folder and fm is not None and fm.exists(folder):
            try:
                folder_norm = os.path.normcase(
                    os.path.realpath(os.path.normpath(folder))
                )
            except OSError:
                folder_norm = ""
            else:
                if path_norm != folder_norm and path_norm.startswith(
                    folder_norm + os.sep
                ):
                    return True
        for root in self._torrent_save_root_norms(anime_id):
            if path_norm == root or path_norm.startswith(root + os.sep):
                return True
        return False

    def list_episode_files(self, anime_id: int) -> list[dict[str, Any]]:
        folder = self._runtime.getFolder(id=anime_id)
        ep_raw = self._coerce_episode_dicts(
            self._runtime.getEpisodes(folder) or []
        )
        out = self._rows_from_scan_dicts(ep_raw, 0)
        seen = {
            self._canonical_path_key(str(r.get("path") or ""))
            for r in out
            if r.get("path")
        }

        for raw_p in self._collect_torrent_save_paths(anime_id):
            p = os.path.normpath(raw_p)
            if not p:
                continue
            if os.path.isfile(p):
                key = self._canonical_path_key(p)
                if key in seen:
                    continue
                suf = Path(p).suffix.lower()
                if suf not in self._VIDEO_SUFFIXES:
                    continue
                digest = hashlib.sha1(p.encode("utf-8")).hexdigest()[:16]
                file_id = f"ep-{len(out):04d}-{digest}"
                try:
                    size_bytes = os.path.getsize(p)
                except OSError:
                    size_bytes = None
                out.append(
                    {
                        "file_id": file_id,
                        "path": p,
                        "title": Path(p).stem,
                        "size_bytes": size_bytes,
                        "season": None,
                        "episode": None,
                    }
                )
                seen.add(key)
            elif os.path.isdir(p):
                nested = self._coerce_episode_dicts(
                    self._runtime.getEpisodes(p) or []
                )
                for row in self._rows_from_scan_dicts(nested, len(out)):
                    k2 = self._canonical_path_key(str(row.get("path") or ""))
                    if k2 in seen:
                        continue
                    seen.add(k2)
                    out.append(row)

        return out

    def delete_episode_file(self, anime_id: int, file_id: str) -> bool:
        """Remove a single episode file when ``file_id`` matches the library scan."""
        if not str(file_id).strip():
            return False
        fm = self._runtime.fm
        if fm is None:
            return False
        for item in self.list_episode_files(anime_id):
            if str(item.get("file_id") or "") != str(file_id).strip():
                continue
            path = str(item.get("path") or "").strip()
            if not path:
                return False
            try:
                path_norm = os.path.normcase(
                    os.path.realpath(os.path.normpath(path))
                )
            except OSError:
                return False
            if not self._path_allowed_for_delete(anime_id, path_norm):
                return False
            if not os.path.isfile(path):
                return False
            try:
                os.remove(path)
                return True
            except OSError:
                return False
        return False

    def get_stream_cache_root(self) -> str:
        fm = self._runtime.fm
        data_path = ""
        if fm is not None:
            settings = getattr(fm, "settings", None)
            if isinstance(settings, dict):
                data_path = str(settings.get("dataPath") or "").strip()
        root = os.path.join(data_path, "streams") if data_path else os.path.abspath(".streams")
        os.makedirs(root, exist_ok=True)
        return root


class LegacyDownloadAdapter:
    """Adapter around DownloadManager plus legacy managers."""

    def __init__(
        self,
        runtime: LegacyRuntime,
        repository: "LegacyAnimeRepositoryAdapter" | None = None,
    ) -> None:
        self._runtime = runtime
        self._user_actions = LegacyUserActionsAdapter(runtime)
        self._download_manager = DownloadManager()
        self._download_manager.set_torrent_manager(runtime.tm)
        self._download_manager.set_file_manager(runtime.fm)
        self._download_manager.set_watching_tag_callback(
            self._promote_watching_on_download_start
        )
        if repository is not None:
            self._download_manager.set_database_manager(
                repository._db_manager
            )
            self._download_manager.schedule_restore_persisted_torrents_after_startup()

    def _promote_watching_on_download_start(self, anime_id: int, user_id: int) -> None:
        """When a download is queued with a user, treat the title as actively watched."""
        try:
            state = self._user_actions.get_user_state(anime_id, user_id)
            tag = str(state.get("tag") or "NONE").upper()
            if tag in ("NONE", "WATCHLIST"):
                self._user_actions.set_tag(anime_id, "WATCHING", user_id)
        except Exception:  # noqa: BLE001
            return

    def start_download(
        self,
        anime_id: int,
        url: str | None = None,
        hash_value: str | None = None,
        user_id: int | None = None,
    ) -> bool:
        queue = self._download_manager.download_file(
            anime_id=anime_id,
            url=url,
            hash_value=hash_value,
            user_id=user_id,
        )
        return queue is not None

    def get_download_progress(self, anime_id: int) -> dict:
        return self._download_manager.get_download_status(anime_id) or {}

    def cancel_download(self, anime_id: int) -> bool:
        return self._download_manager.cancel_download(anime_id)

    def get_active_downloads(self) -> list[dict]:
        return self._download_manager.get_active_downloads()

    def get_torrents_overview(self) -> dict[str, list[dict]]:
        """Return the downloading / seeding / completed torrent buckets.

        Delegates to :meth:`DownloadManager.get_torrents_overview`. The
        method is wrapped here (rather than exposed directly) so the
        application service stays decoupled from the legacy download
        manager class.
        """
        getter = getattr(self._download_manager, "get_torrents_overview", None)
        if not callable(getter):
            return {
                "active": [],
                "seeding": [],
                "completed": [],
                "error": [],
                "other": [],
            }
        return getter()

    def redownload(self, anime_id: int) -> int:
        return int(self._download_manager.redownload(anime_id) or 0)

    def delete_all_files(self, anime_id: int, user_id: int | None = None) -> int:
        _ = user_id
        removed = 0
        media = LegacyMediaLibraryAdapter(self._runtime, download_port=self)
        for row in media.list_episode_files(anime_id):
            file_id = str(row.get("file_id") or "")
            if file_id and media.delete_episode_file(anime_id, file_id):
                removed += 1
        return removed

    def delete_seen_episodes(self, anime_id: int, user_id: int | None = None) -> int:
        _ = user_id
        media = LegacyMediaLibraryAdapter(self._runtime, download_port=self)
        files = media.list_episode_files(anime_id)
        last_seen = ""
        try:
            anime = self._runtime.database.get(anime_id, table="anime")
            if anime:
                last_seen = str(getattr(anime, "last_seen", None) or anime.get("last_seen") or "").strip()
        except Exception:
            last_seen = ""
        if not last_seen:
            return 0
        removed = 0
        for row in files:
            if str(row.get("path") or "") == last_seen:
                break
            file_id = str(row.get("file_id") or "")
            if file_id and media.delete_episode_file(anime_id, file_id):
                removed += 1
        return removed

    def search_torrents(
        self,
        terms: list[str],
        profile: str = "interactive",
        limit: int = 200,
    ) -> list[dict]:
        facade = SearchFacade.for_profile(profile)
        rows = list(facade.search(terms))
        rows.sort(key=lambda row: int(row.get("seeds") or 0), reverse=True)
        return rows[: max(1, limit)]

    def stream_torrents(
        self,
        terms: list[str],
        profile: str = "interactive",
        limit: int = 200,
    ):
        """Yield torrent dicts as soon as each engine returns a row."""
        facade = SearchFacade.for_profile(profile)
        max_results = max(1, limit)
        emitted = 0
        for row in facade.search(terms):
            yield row
            emitted += 1
            if emitted >= max_results:
                return


class LegacyUserActionsAdapter:
    """Adapter for user-tag actions using existing DB tables.

    The persistence layer uses a single ``user_tags`` row per
    ``(anime_id, user_id)`` pair that holds both the ``tag`` and
    ``liked`` columns. Earlier revisions used ``REPLACE INTO`` which
    has two failure modes depending on the schema:

    * If ``(anime_id, user_id)`` carries a UNIQUE/PRIMARY KEY
      constraint, ``REPLACE INTO`` deletes the existing row before
      inserting, which wipes whichever column is NOT in the
      ``VALUES`` clause -- so ``set_tag`` clobbers ``liked`` and
      ``set_like`` clobbers ``tag``.
    * If the constraint is missing, every call appends a new row and
      the subsequent ``SELECT ... LIMIT 1`` returns whichever row
      SQLite picks first (typically the oldest by ``rowid``), making
      the visible tag look frozen at its first value.

    This adapter now uses an explicit UPDATE-then-INSERT pattern that
    is portable across SQLite/MariaDB/MySQL, only touches the column
    being modified, and never creates duplicate rows. Read paths
    additionally merge any pre-existing duplicate rows so users who
    were affected by the legacy bug recover automatically the first
    time they look at the affected anime.

    Per-episode watch state lives in ``episode_progress`` (created on
    first use) keyed by the stable ``file_id`` from the media library.
    """

    _ALLOWED_COLUMNS = ("tag", "liked")
    _EPISODE_STATUSES = frozenset({"UNSEEN", "IN_PROGRESS", "SEEN"})

    def __init__(self, runtime: LegacyRuntime) -> None:
        self._runtime = runtime

    def _upsert_column(
        self,
        anime_id: int,
        user_id: int,
        *,
        column: str,
        value: Any,
        action_label: str,
    ) -> None:
        """Insert or update a single column in ``user_tags`` safely.

        The column name is whitelisted so we can interpolate it into
        the SQL statement directly (parameter binding does not support
        identifiers). All user-controlled values are still bound as
        positional parameters.
        """
        if column not in self._ALLOWED_COLUMNS:
            raise InfrastructureError(
                f"Refusing to write to unsupported column: {column}"
            )
        db = self._runtime.database
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

    def mark_seen(
        self, anime_id: int, file_name: str, user_id: int
    ) -> None:
        # Preserve compatibility by tagging as SEEN. Episode bookkeeping
        # can be extended by a dedicated adapter without changing
        # application contracts.
        _ = file_name
        self.set_tag(anime_id, "SEEN", user_id)

    def get_user_state(self, anime_id: int, user_id: int) -> dict:
        db = self._runtime.database
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

        # Merge across rows so callers see a consistent view even when
        # past ``REPLACE INTO`` writes left orphan rows that hold only
        # one column each. Last non-NULL value wins.
        tag: Optional[str] = None
        liked: Optional[int] = None
        for row in rows:
            row_tag = row[0] if len(row) > 0 else None
            row_liked = row[1] if len(row) > 1 else None
            if row_tag is not None:
                tag = row_tag
            if row_liked is not None:
                liked = row_liked
        return {"tag": tag or "NONE", "liked": bool(liked)}

    def _ensure_episode_progress_table(self) -> None:
        db = self._runtime.database
        # Use VARCHAR for key columns: MySQL/MariaDB reject TEXT/BLOB in a
        # PRIMARY KEY without a prefix length (error 1170). The web UI always
        # passes a user_id when listing episodes, so this DDL runs on every
        # detail page and a failed CREATE left ``episode_files`` empty after
        # the HTTP layer swallowed the infrastructure error.
        ddl = (
            "CREATE TABLE IF NOT EXISTS episode_progress ("
            "anime_id INTEGER NOT NULL, "
            "user_id INTEGER NOT NULL, "
            "file_id VARCHAR(255) NOT NULL, "
            "status VARCHAR(32) NOT NULL, "
            "position_seconds DOUBLE, "
            "updated_at DOUBLE NOT NULL, "
            "PRIMARY KEY (anime_id, user_id, file_id))"
        )
        try:
            with db.get_lock():
                db.sql(ddl, (), save=True)
        except Exception as exc:
            raise InfrastructureError(
                f"Failed to ensure episode_progress schema: {exc}"
            ) from exc

    def get_episode_progress_map(self, anime_id: int, user_id: int) -> dict[str, dict[str, Any]]:
        self._ensure_episode_progress_table()
        db = self._runtime.database
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
            pos: float | None
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
        pos_val: float | None
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
        db = self._runtime.database
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

    def delete_episode_progress(self, anime_id: int, user_id: int, file_id: str) -> None:
        self._ensure_episode_progress_table()
        fid = str(file_id or "").strip()
        if not fid:
            return
        db = self._runtime.database
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


__all__ = [
    "LegacyRuntime",
    "LegacyAnimeRepositoryAdapter",
    "LegacyMetadataProviderAdapter",
    "LegacyMediaLibraryAdapter",
    "LegacyDownloadAdapter",
    "LegacyUserActionsAdapter",
]


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
