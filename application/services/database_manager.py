"""
DatabaseManager component for handling all database operations.
Provides repository pattern for data access with connection pooling and transactions.
"""

import threading
from typing import Any, Dict, List, Optional, Tuple, Union, Callable
from contextlib import contextmanager
import json

from shared.base_component import BaseComponent
from adapters.persistence.queue import PersistenceQueue
from adapters.persistence.query_builder import ALLOWED_CRITERIA, build_anime_list_query
from shared.telemetry import get_telemetry
from application.bridges.legacy_entities import Anime, AnimeList
from adapters.persistence import databases
from application.services.anime_merge_service import AnimeMergeService, MergeResult


class DatabaseManager(BaseComponent):
    """
    Manages all database operations with proper connection pooling and transactions.
    Implements repository pattern for data access.
    """

    def __init__(self):
        super().__init__("DatabaseManager")
        self._database = None
        self._lock = threading.RLock()
        self._allowed_criteria = ALLOWED_CRITERIA
        self._telemetry = get_telemetry()
        self._write_queue: Optional[PersistenceQueue] = None
        self._write_queue_enabled = False

    def close(self) -> None:
        """Drain the optional write queue and release the DB connection."""
        if self._write_queue is not None:
            try:
                self._write_queue.stop(drain=True, timeout=5.0)
            except Exception as exc:
                self.log("DB_ERROR", f"Error draining write queue: {exc}")
            finally:
                self._write_queue = None
                self._write_queue_enabled = False
        with self._lock:
            if self._database:
                try:
                    self._database.close()
                    self.log("DB_MANAGER", "Database connection closed")
                except Exception as exc:
                    self.log("DB_ERROR", f"Error closing database: {exc}")
                finally:
                    self._database = None

    def _stop(self) -> None:
        """Lifecycle alias for :meth:`close`."""
        self.close()

    def enable_batched_writes(self, *, batch_size: int = 25, max_latency_ms: int = 250) -> None:
        """Spin up the batched persistence queue.

        Call this once after construction to opt into the high-throughput
        write path. Disabled by default to preserve legacy synchronous
        semantics during migration.
        """
        if self._write_queue is not None:
            return
        self._write_queue = PersistenceQueue(
            self._flush_write_batch,
            batch_size=batch_size,
            max_latency_ms=max_latency_ms,
            worker_name="DBPersistQueue",
        )
        self._write_queue.start()
        self._write_queue_enabled = True
        self.log("DB_MANAGER", "Batched write queue enabled")

    def write_queue_stats(self) -> Dict[str, Any]:
        """Return current write-queue stats; empty dict when disabled."""
        if self._write_queue is None:
            return {}
        return self._write_queue.stats()

    def _flush_write_batch(self, batch: List[Any]) -> None:
        """Internal: flush a batch from the persistence queue."""
        animes = [r for r in batch if r is not None]
        if not animes:
            return
        try:
            self.upsert_anime_batch(animes)
            self._telemetry.increment("db.queued_writes_flushed", len(animes))
        except Exception as exc:
            self.log("DB_ERROR", f"Queued write flush failed: {exc}")
            self._telemetry.increment("db.queued_write_errors")

    def set_database(self, database) -> None:
        """
        Set the database instance.

        Args:
            database: The database instance to use
        """
        with self._lock:
            self._database = database

    def get_database(self):
        """Get the current database instance."""
        return self._database

    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections.
        Ensures proper cleanup and transaction handling.
        """
        if not self._database:
            raise RuntimeError("Database not initialized")

        use_pool = bool(getattr(self._database, "USE_CONNECTION_POOL", False))
        if use_pool:
            try:
                yield self._database
            except Exception as e:
                self.log("DB_ERROR", f"Database operation failed: {e}")
                raise
        else:
            with self._database.get_lock():
                try:
                    yield self._database
                except Exception as e:
                    self.log("DB_ERROR", f"Database operation failed: {e}")
                    raise

    def is_initialized(self) -> bool:
        """Check if database is initialized."""
        return self._database is not None and self._database.is_initialized()

    def search_anime(self, terms: str, limit: int = 50) -> Optional[AnimeList]:
        """
        Search for anime in the database.

        Args:
            terms: Search terms
            limit: Maximum results to return

        Returns:
            AnimeList or None if no results
        """
        if not terms or not terms.strip():
            return None

        cleaned_terms = "".join([c if c.isalnum() or c == " " else " " for c in terms])
        cleaned_terms = " ".join(cleaned_terms.split())

        if not cleaned_terms:
            return None

        try:
            with self.get_connection() as db:
                args, results = db.procedure("search_anime_fast", cleaned_terms, limit)

                if not results or len(results) == 0:
                    return None

                keys = [
                    "id", "title", "picture", "date_from", "date_to", "synopsis",
                    "episodes", "duration", "rating", "status", "broadcast",
                    "last_seen", "trailer", "relevance"
                ]

                anime_batch = []
                for row in results:
                    if isinstance(row, dict):
                        row_values = [row.get(key) for key in keys[:-1]]
                    else:
                        row_values = row[:-1]  # Exclude relevance score

                    anime_data = dict(zip(keys[:-1], row_values))
                    anime_batch.append(Anime(**anime_data))

                anime_batch = db.get_all_metadata_bulk(anime_batch, use_eager_loading=True)
                return AnimeList(anime_batch)

        except Exception as e:
            self.log("DB_ERROR", f"Search failed: {e}")
            return None

    def get_anime_list(self, criteria: str, listrange: Tuple[int, int] = (0, 50),
                      hide_rated: Optional[bool] = None, user_id: Optional[int] = None) -> Tuple[Optional[AnimeList], Optional[callable]]:
        """
        Get a filtered anime list.

        Args:
            criteria: Filter criteria
            listrange: Range of results (start, end)
            hide_rated: Whether to hide rated content
            user_id: User ID for filtering

        Returns:
            Tuple of (anime_list, next_page_function)
        """
        if user_id is None:
            user_id = 4

        if hide_rated is None:
            hide_rated = getattr(self, 'hide_rated', True)

        args = self._build_query_args(criteria, listrange, hide_rated, user_id)

        def get_next(args):
            with self.get_connection() as db:
                new_list = db.filter(**args)
                next_list = None

                if not new_list.empty():
                    next_range = (listrange[1], listrange[1] + listrange[1] - listrange[0])
                    next_args = args.copy()
                    next_args["range"] = next_range

                    def create_next_list(args=next_args):
                        return get_next(args)

                    next_list = create_next_list

                return new_list, next_list

        try:
            return get_next(args)
        except Exception as e:
            self.log("DB_ERROR", f"Failed to get anime list: {e}")
            return None, None

    def _build_query_args(self, criteria: str, listrange: Tuple[int, int],
                         hide_rated: bool, user_id: int) -> Dict[str, Any]:
        """Build query arguments for anime list filtering.

        Delegates to the centralized whitelisted query builder, which
        returns SQL constants plus a `params` mapping for bind values.
        """
        query = build_anime_list_query(
            criteria,
            listrange,
            hide_rated=hide_rated,
            user_id=user_id,
        )
        return query.to_args()

    def save_torrent(self, anime_id: int, torrent) -> None:
        """Persist a torrent's metadata and its anime mapping.

        Each ``INSERT`` is committed inline (``save=True``) because the
        MariaDB backend uses a per-call connection pool: ``db.sql(...,
        save=False)`` runs on a pool connection that is recycled before
        the trailing ``db.save()`` on the long-lived main connection
        ever fires, so the writes are effectively rolled back. Without
        this commit semantics the ``torrents`` / ``torrentsIndex``
        tables stay empty across restarts and the LibTorrent cold-start
        restore (which reads from those tables) has nothing to re-add,
        which is what users see as "the app forgot my torrents".
        """
        if torrent is None or not getattr(torrent, "hash", None):
            return
        try:
            with self.get_connection() as db:
                raw_trackers = getattr(torrent, "trackers", None)
                if isinstance(raw_trackers, (list, tuple, set)):
                    trackers = json.dumps(list(raw_trackers))
                elif isinstance(raw_trackers, str):
                    # Already JSON? keep as-is; otherwise wrap the single
                    # tracker URL so we always store a JSON array.
                    stripped = raw_trackers.strip()
                    if stripped.startswith("["):
                        trackers = stripped
                    else:
                        trackers = json.dumps([stripped]) if stripped else json.dumps([])
                else:
                    trackers = json.dumps([])

                exists = db.sql(
                    "SELECT EXISTS(SELECT 1 FROM torrentsIndex WHERE id=? AND value=?)",
                    (anime_id, torrent.hash),
                )
                if not exists or not exists[0][0]:
                    db.sql(
                        "INSERT INTO torrentsIndex(id, value) VALUES(?, ?)",
                        (anime_id, torrent.hash),
                        save=True,
                    )

                exists = db.sql(
                    "SELECT EXISTS(SELECT 1 FROM torrents WHERE hash=?)",
                    (torrent.hash,),
                )
                if not exists or not exists[0][0]:
                    db.sql(
                        "INSERT INTO torrents(hash, name, trackers) VALUES(?, ?, ?)",
                        (torrent.hash, getattr(torrent, "name", None), trackers),
                        save=True,
                    )
        except Exception as e:
            self.log("DB_ERROR", f"Failed to save torrent: {e}")
            raise

    def get_torrent_data(self, hash_value: str) -> Optional[Tuple]:
        """
        Get torrent data by hash.

        Args:
            hash_value: Torrent hash

        Returns:
            Tuple of (name, trackers) or None
        """
        try:
            with self.get_connection() as db:
                data = db.sql(
                    "SELECT name, trackers FROM torrents WHERE hash=? LIMIT 1",
                    (hash_value,),
                )
                return data[0] if data else None
        except Exception as e:
            self.log("DB_ERROR", f"Failed to get torrent data: {e}")
            return None

    def list_anime_torrent_pairs(self) -> List[Tuple[int, str]]:
        """Return distinct ``(anime_id, info_hash)`` rows from the torrent index.

        Used after a cold start to re-attach embedded LibTorrent to torrents
        that were already saved for the library (so seeding can resume once
        data files are still on disk under the anime folder).
        """
        try:
            with self.get_connection() as db:
                rows = db.sql(
                    "SELECT DISTINCT i.id, t.hash FROM torrentsIndex AS i "
                    "INNER JOIN torrents AS t "
                    "ON LOWER(i.value) = LOWER(t.hash)"
                )
        except Exception as exc:
            self.log("DB_ERROR", f"Failed to list anime torrent pairs: {exc}")
            return []
        out: List[Tuple[int, str]] = []
        for row in rows or []:
            if not row or len(row) < 2:
                continue
            try:
                aid = int(row[0])
                h = str(row[1]).strip()
            except (TypeError, ValueError):
                continue
            if h:
                out.append((aid, h))
        return out

    def get_anime_ids_by_hashes(
        self, hashes: List[str]
    ) -> Dict[str, int]:
        """Return ``{hash_lower: anime_id}`` for every persisted torrent.

        Used by the downloads/seeding overview so the live torrent
        listing (which only carries an info-hash) can be annotated with
        the anime each torrent belongs to without per-row lookups.

        Unknown hashes are simply omitted from the result map. The
        method is read-only and silently degrades to an empty dict if
        the underlying query fails so the overview keeps rendering.
        """
        normalised = [str(h).strip().lower() for h in hashes if h]
        if not normalised:
            return {}
        out: Dict[str, int] = {}
        try:
            with self.get_connection() as db:
                placeholders = ",".join("?" for _ in normalised)
                rows = db.sql(
                    "SELECT LOWER(value), id FROM torrentsIndex "
                    f"WHERE LOWER(value) IN ({placeholders})",
                    tuple(normalised),
                )
        except Exception as exc:
            self.log("DB_ERROR", f"Failed to map torrents to anime: {exc}")
            return {}
        for row in rows or []:
            if not row:
                continue
            try:
                key = str(row[0]).strip().lower()
                aid = int(row[1])
            except (TypeError, ValueError, IndexError):
                continue
            if key:
                out[key] = aid
        return out

    def get_anime_titles(self, anime_ids: List[int]) -> Dict[int, str]:
        """Resolve ``{anime_id: title}`` for the ``anime_ids`` set.

        Returns an empty dict when the DB lookup fails so the caller
        can fall back to a generic ``"Anime #<id>"`` label without
        propagating the error.
        """
        cleaned: List[int] = []
        for aid in anime_ids or []:
            try:
                cleaned.append(int(aid))
            except (TypeError, ValueError):
                continue
        if not cleaned:
            return {}
        out: Dict[int, str] = {}
        try:
            with self.get_connection() as db:
                placeholders = ",".join("?" for _ in cleaned)
                rows = db.sql(
                    f"SELECT id, title FROM anime WHERE id IN ({placeholders})",
                    tuple(cleaned),
                )
        except Exception as exc:
            self.log("DB_ERROR", f"Failed to look up anime titles: {exc}")
            return {}
        for row in rows or []:
            if not row:
                continue
            try:
                aid = int(row[0])
            except (TypeError, ValueError, IndexError):
                continue
            title = str(row[1]) if len(row) > 1 and row[1] else ""
            if title:
                out[aid] = title
        return out

    def get_anime_metadata(self, anime: Anime) -> Anime:
        """
        Get all metadata for an anime.

        Args:
            anime: Anime object

        Returns:
            Anime with metadata
        """
        try:
            with self.get_connection() as db:
                return db.get_all_metadata(anime)
        except Exception as e:
            self.log("DB_ERROR", f"Failed to get anime metadata: {e}")
            return anime

    def update_anime(self, anime: Anime) -> None:
        """
        Update anime in database.

        Args:
            anime: Anime object to update
        """
        try:
            with self.get_connection() as db:
                self._persist_anime_record(db, anime, commit=True)
        except Exception as e:
            self.log("DB_ERROR", f"Failed to update anime: {e}")
            raise

    def upsert_anime_batch(self, records: List[Anime]) -> int:
        """Persist anime objects, committing each row inline.

        The natural shape here is "open a transaction, INSERT every
        record, commit once at the end". The MariaDB backend uses a
        per-call connection pool though (``USE_CONNECTION_POOL``), so
        the ``db.set(..., save=False)`` calls each run on a pool
        connection that is recycled before the trailing ``db.save()``
        on the long-lived main connection ever fires -- the writes are
        then effectively rolled back. Until the persistence layer
        exposes "checkout a connection for the whole batch" we commit
        each row inline. The throughput hit is negligible for the
        startup-jobs use case (tens of records) and the alternative is
        silent data loss.
        """
        if not records:
            return 0
        saved = 0
        with self._telemetry.time("db.upsert_anime_batch_ms"):
            with self.get_connection() as db:
                for anime in records:
                    try:
                        self._persist_anime_record(db, anime, commit=True)
                        saved += 1
                    except Exception as exc:
                        self.log(
                            "DB_ERROR",
                            f"Failed upserting anime {getattr(anime, 'id', None)}: {exc}",
                        )
        self._telemetry.increment("db.upserts_committed", saved)
        return saved

    def _persist_anime_record(self, db, anime: Anime, *, commit: bool) -> None:
        """Upsert a single anime record through the backend's ``set()`` API.

        ``BaseDB.save()`` is the no-argument transaction-commit hook, not
        an upsert entrypoint. Routing record persistence through
        ``db.set(id, data, "anime", save=...)`` keeps the per-row write
        and the per-batch commit on separate methods, which is required
        by every concrete BaseDB subclass (EmbeddedMariaDB / MySQL /
        SQLite).
        """
        anime_id = getattr(anime, "id", None)
        if anime_id is None and isinstance(anime, dict):
            anime_id = anime.get("id")
        if anime_id is None:
            raise ValueError("Anime record has no 'id' attribute")

        if hasattr(anime, "save_format"):
            data, metadata = anime.save_format()
        elif isinstance(anime, dict):
            data, metadata = dict(anime), {}
        elif hasattr(anime, "__dict__"):
            data = {
                k: v
                for k, v in vars(anime).items()
                if not k.startswith("_") and not callable(v)
            }
            metadata = {}
        else:
            raise TypeError(
                f"Cannot persist {type(anime).__name__}: not dict-like"
            )

        if "id" not in data:
            data["id"] = anime_id

        db.set(anime_id, data, "anime", save=commit)

        if metadata:
            try:
                db.save_metadata(anime_id, metadata)
            except Exception as exc:
                self.log(
                    "DB_WARNING",
                    f"Failed saving metadata for {anime_id}: {exc}",
                )

    def enqueue_anime(self, record: Anime) -> bool:
        """Add a record to the async batched write queue.

        Returns True if accepted, False when the queue is disabled or full.
        Falls back to synchronous upsert when the queue is disabled, so
        callers never silently lose data during the migration.
        """
        if self._write_queue is None:
            self.upsert_anime_batch([record])
            return True
        return self._write_queue.put(record)

    def upsert_metadata_batch(self, records: List[Tuple[int, Dict[str, Any]]]) -> int:
        """Persist metadata records in batch-friendly form."""
        if not records:
            return 0
        saved = 0
        with self.get_connection() as db:
            for anime_id, metadata in records:
                if not metadata:
                    continue
                try:
                    db.save_metadata(anime_id, metadata)
                    saved += 1
                except Exception as exc:
                    self.log("DB_ERROR", f"Failed saving metadata for {anime_id}: {exc}")
        return saved

    def merge_anime_ids(self, canonical_id: int, duplicate_id: int) -> bool:
        """Merge ``duplicate_id`` into ``canonical_id`` preserving user data."""
        try:
            with self.get_connection() as db:
                merger = AnimeMergeService(db, log=self.log)
                return merger.merge_two_ids(int(canonical_id), int(duplicate_id))
        except Exception as exc:
            self.log(
                "DB_ERROR",
                f"Failed merging anime ids {duplicate_id}->{canonical_id}: {exc}",
            )
            return False

    def merge_anime_by_external_mapping(
        self, source_id: int, mapped: List[Tuple[str, Any]]
    ) -> MergeResult:
        """Merge duplicates discovered from explicit external-id mappings."""
        try:
            with self.get_connection() as db:
                merger = AnimeMergeService(db, log=self.log)
                return merger.merge_from_external_mappings(int(source_id), mapped)
        except Exception as exc:
            self.log(
                "DB_ERROR",
                f"Failed merge-by-mapping for anime {source_id}: {exc}",
            )
            return MergeResult(canonical_id=int(source_id), skipped_reason="error")

    def backfill_external_id_duplicates(self, *, max_passes: int = 8) -> Dict[str, int]:
        """Run a deterministic one-time merge pass across existing duplicates."""
        try:
            with self.get_connection() as db:
                merger = AnimeMergeService(db, log=self.log)
                return merger.backfill_existing_duplicates(max_passes=max_passes)
        except Exception as exc:
            self.log("DB_ERROR", f"Backfill merge failed: {exc}")
            return {"passes": 0, "merged": 0, "groups": 0}
