"""
DatabaseManager component for handling all database operations.
Provides repository pattern for data access with connection pooling and transactions.
"""

import threading
from typing import Any, Dict, List, Optional, Tuple, Union, Callable
from contextlib import contextmanager

from ..core import BaseComponent
from ..classes import Anime, AnimeList
from ..db_managers import databases


class DatabaseManager(BaseComponent):
    """
    Manages all database operations with proper connection pooling and transactions.
    Implements repository pattern for data access.
    """

    def __init__(self):
        super().__init__("DatabaseManager")
        self._database = None
        self._lock = threading.RLock()

    def _initialize(self) -> None:
        """Initialize the database manager."""
        self.log("DB_MANAGER", "Initializing Database Manager")

    def _start(self) -> None:
        """Start the database manager."""
        self.log("DB_MANAGER", "Starting Database Manager")

    def _stop(self) -> None:
        """Stop the database manager."""
        with self._lock:
            if self._database:
                try:
                    self._database.close()
                    self.log("DB_MANAGER", "Database connection closed")
                except Exception as e:
                    self.log("DB_ERROR", f"Error closing database: {e}")
                finally:
                    self._database = None

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

        # Clean the search terms
        cleaned_terms = "".join([c if c.isalnum() or c == " " else " " for c in terms])
        cleaned_terms = " ".join(cleaned_terms.split())

        if not cleaned_terms:
            return None

        try:
            with self.get_connection() as db:
                # Call the optimized stored procedure
                args, results = db.procedure("search_anime_fast", cleaned_terms, limit)

                if not results or len(results) == 0:
                    return None

                # Column names from the stored procedure
                keys = [
                    "id", "title", "picture", "date_from", "date_to", "synopsis",
                    "episodes", "duration", "rating", "status", "broadcast",
                    "last_seen", "trailer", "relevance"
                ]

                # Generator to convert results to Anime objects
                def anime_generator():
                    for row in results:
                        # Ensure row is a sequence
                        if isinstance(row, dict):
                            row_values = [row.get(key) for key in keys[:-1]]
                        else:
                            row_values = row[:-1]  # Exclude relevance score

                        anime_data = dict(zip(keys[:-1], row_values))
                        anime = db.get_all_metadata(Anime(**anime_data))
                        yield anime

                return AnimeList(anime_generator())

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

        # Build query parameters
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
        """Build query arguments for anime list filtering."""
        if criteria == "DEFAULT":
            table = f"anime LEFT JOIN user_tags ON user_tags.anime_id = anime.id AND user_id={int(user_id)}"
            filter_clause = "anime.status != 'UPCOMING' AND anime.status != 'UNKNOWN'"
            if hide_rated:
                filter_clause += " AND (rating NOT IN('R+','Rx') OR rating IS null)"
            sort = "DESC"
            order = "anime.date_from"

        else:
            table = f"anime LEFT JOIN user_tags ON user_tags.anime_id = anime.id AND user_id={int(user_id)}"
            common_filter = "\nAND status != 'UPCOMING'"
            order = "date_from"
            sort = "DESC"

            if hide_rated:
                common_filter += " \nAND (rating NOT IN('R+','Rx') OR rating IS null)"

            if criteria == "LIKED":
                filter_clause = "liked = 1" + common_filter

            elif criteria == "NONE":
                filter_clause = "tag IS null OR tag = 'NONE'" + common_filter

            elif criteria in ["UPCOMING", "FINISHED", "AIRING"]:
                if criteria == "UPCOMING":
                    common_filter = ("\nAND (rating NOT IN('R+','Rx') OR rating IS null)"
                                   if hide_rated else "")
                    sort = "ASC"
                filter_clause = f"status = '{criteria}'" + common_filter

            elif criteria == "RATED":
                filter_clause = "rating IN('R+','Rx')\nAND status != 'UPCOMING'"

            elif criteria == "RANDOM":
                order = "RANDOM()"
                filter_clause = "anime.picture is not null"

            else:
                if criteria == "WATCHING":
                    common_filter = "\nAND status != 'UPCOMING'"
                    table = (f"anime LEFT JOIN broadcasts ON anime.id = broadcasts.id "
                           f"LEFT JOIN user_tags ON user_tags.anime_id = anime.id AND user_id={int(user_id)}")
                    # Complex ordering for watching list - simplified for now
                    order = "date_from"
                filter_clause = f"tag = '{criteria}'" + common_filter

        return {
            "table": table,
            "sort": sort,
            "range": listrange,
            "order": order,
            "filter": filter_clause,
        }

    def save_torrent(self, anime_id: int, torrent) -> None:
        """
        Save torrent data to database.

        Args:
            anime_id: Anime ID
            torrent: Torrent object
        """
        try:
            with self.get_connection() as db:
                db.save_torrent(anime_id, torrent)
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
                args, data = db.procedure("get_torrent_data", hash_value)
                return next(data, None)
        except Exception as e:
            self.log("DB_ERROR", f"Failed to get torrent data: {e}")
            return None

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
                db.save(anime)
        except Exception as e:
            self.log("DB_ERROR", f"Failed to update anime: {e}")
            raise