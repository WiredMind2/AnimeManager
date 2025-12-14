import json
import os
import queue
import sys
import time
import hashlib
from collections import deque
from datetime import datetime, timedelta, timezone
from types import NoneType
from functools import wraps

import requests

try:
    from ..classes import Anime, Character, NoIdFound
    from ..constants import Constants
    from ..getters import Getters
    from ..logger import Logger
    from ..general_utils import dict_merge
except ImportError:
    from classes import Anime, Character, NoIdFound
    from constants import Constants
    from getters import Getters
    from logger import Logger
    from general_utils import dict_merge
    
    
    class APICache:
        """Intelligent caching system for API responses"""
    
        def __init__(self, max_size=1000, default_ttl=3600):  # 1 hour default TTL
            self.max_size = max_size
            self.default_ttl = default_ttl
            self.cache = {}
            self.access_times = {}
            self.cache_stats = {'hits': 0, 'misses': 0, 'evictions': 0}
    
        def _generate_key(self, url, method='GET', params=None, data=None):
            """Generate cache key from request details"""
            key_data = f"{method}:{url}"
            if params:
                key_data += f":{json.dumps(params, sort_keys=True)}"
            if data:
                key_data += f":{json.dumps(data, sort_keys=True)}"
            return hashlib.md5(key_data.encode()).hexdigest()
    
        def get(self, url, method='GET', params=None, data=None):
            """Get cached response if available and not expired"""
            key = self._generate_key(url, method, params, data)
    
            if key in self.cache:
                # Check if expired
                if time.time() - self.access_times[key] > self.default_ttl:
                    del self.cache[key]
                    del self.access_times[key]
                    self.cache_stats['evictions'] += 1
                    return None
    
                self.access_times[key] = time.time()
                self.cache_stats['hits'] += 1
                return self.cache[key]
    
            self.cache_stats['misses'] += 1
            return None
    
        def set(self, url, response, method='GET', params=None, data=None, ttl=None):
            """Cache API response"""
            key = self._generate_key(url, method, params, data)
    
            # Evict oldest entries if cache is full
            if len(self.cache) >= self.max_size:
                self._evict_oldest()
    
            self.cache[key] = response
            self.access_times[key] = time.time()
    
        def _evict_oldest(self):
            """Remove oldest cache entry"""
            if not self.access_times:
                return
    
            oldest_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
            del self.cache[oldest_key]
            del self.access_times[oldest_key]
            self.cache_stats['evictions'] += 1
    
        def clear(self):
            """Clear all cached responses"""
            self.cache.clear()
            self.access_times.clear()
    
        def get_stats(self):
            """Get cache statistics"""
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hit_rate': self.cache_stats['hits'] / max(1, self.cache_stats['hits'] + self.cache_stats['misses']),
                'hits': self.cache_stats['hits'],
                'misses': self.cache_stats['misses'],
                'evictions': self.cache_stats['evictions']
            }
    
    
    def cached_request(func):
        def wrapper(*args, **kwargs):
            self = args[0]
            self.queue.put((func, args, kwargs))
        return wrapper
    
    
    def cached_api_request(ttl=3600):
        """Decorator for caching API requests"""
        def decorator(func):
            @wraps(func)
            def wrapper(self, *args, **kwargs):
                # Generate cache key from function name and arguments
                cache_key = f"{func.__name__}:{json.dumps(args, sort_keys=True)}:{json.dumps(kwargs, sort_keys=True)}"
    
                # Check cache first
                cached_result = self.api_cache.get(cache_key)
                if cached_result is not None:
                    return cached_result
    
                # Make actual API call
                result = func(self, *args, **kwargs)
    
                # Cache the result
                if result is not None:
                    self.api_cache.set(cache_key, result, ttl=ttl)
    
                return result
            return wrapper
        return decorator


class APIUtils(Logger, Getters):
    def __init__(self):
        Logger.__init__(self, logs="ALL")
        self.states = {
            "airing": "AIRING",
            "Currently Airing": "AIRING",
            "completed": "FINISHED",
            "complete": "FINISHED",
            "Finished Airing": "FINISHED",
            "to_be_aired": "UPCOMING",
            "tba": "UPCOMING",
            "upcoming": "UPCOMING",
            "Not yet aired": "UPCOMING",
            "NONE": "UNKNOWN",
        }

        # self.database = DummyDB(self.getDatabase())
        self.database = self.getDatabase()
        self.queue = queue.Queue()

        # Initialize API response cache for performance optimization
        self.api_cache = APICache(max_size=1000, default_ttl=3600)  # 1 hour TTL

    @property
    def __name__(self):
        return str(self.__class__).split("'")[1].split(".")[-1]

    def getStatusFromData(self, data, reverse=True):
        """Get status from raw API data dictionary (different from getStatus static method)"""
        if data["date_from"] is None:
            status = "UNKNOWN"
        else:
            if not isinstance(data["date_from"], int):
                status = "UPDATE"
            else:
                try:
                    # Use datetime constructor for negative timestamps (pre-1970 dates)
                    # Windows doesn't support fromtimestamp() with negative values
                    if data["date_from"] < 0:
                        # For negative timestamps, calculate from epoch manually
                        date_from_dt = datetime(
                            1970, 1, 1, tzinfo=timezone.utc
                        ) + timedelta(seconds=data["date_from"])
                    else:
                        date_from_dt = datetime.fromtimestamp(
                            data["date_from"], timezone.utc
                        )

                    now = datetime.now(timezone.utc)

                    if date_from_dt > now:
                        status = "UPCOMING"
                    else:
                        if data["date_to"] is None:
                            if data["episodes"] == 1:
                                status = "FINISHED"
                            else:
                                status = "AIRING"
                        else:
                            try:
                                # Handle negative timestamps for date_to as well
                                if data["date_to"] < 0:
                                    date_to_dt = datetime(
                                        1970, 1, 1, tzinfo=timezone.utc
                                    ) + timedelta(seconds=data["date_to"])
                                else:
                                    date_to_dt = datetime.fromtimestamp(
                                        data["date_to"], timezone.utc
                                    )

                                if date_to_dt > now:
                                    status = "AIRING"
                                else:
                                    status = "FINISHED"
                            except (OSError, ValueError, OverflowError):
                                # Invalid date_to timestamp, default to AIRING
                                status = "AIRING"
                except (OSError, ValueError, OverflowError):
                    # Invalid timestamp (too large or out of range)
                    status = "UNKNOWN"
        return status

    def getId(
        self, id, table="anime"
    ):  # TODO - Same name as in database.py -> need renaming
        """Get the internal id for an external id. Uses self.apiKey to determine the column to search!"""

        table = {"anime": "indexList", "characters": "charactersIndex"}.get(
            table, table
        )

        sql = f"SELECT {self.apiKey} FROM {table} WHERE id=?"
        with self.database.get_lock():
            api_id = self.database.sql(sql, (id,))

        if api_id == []:
            # self.log("Key not found!", sql, id)
            raise NoIdFound(id)
        return api_id[0][0]

    def getRates(self, name):
        with self.database.get_lock():
            data = self.database.sql(
                "SELECT value FROM rateLimiters WHERE id=? AND name=?",
                (self.apiKey, name),
            )
            if len(data) == 0:
                return None
            else:
                return data[0][0]

    def setRates(self, name, value):
        with self.database.get_lock():
            self.database.sql(
                "INSERT OR REPLACE INTO rateLimiters(value) VALUES (?) WHERE id=? AND name=?",
                (value, self.apiKey, name),
                save=True,
            )  # TODO - Maybe save later?

    # Anime metadata

    @cached_request
    def save_relations(self, id, rels):
        # Rels must be a list of dicts, each containing three fields: 'type', 'name', 'rel_id'
        if len(rels) == 0:
            return

        with self.database.get_lock():
            db_rels = self.get_relations(id)
            for rel in rels:
                if (
                    rel["type"] == "anime"
                ):  # TODO - Add support for other types or relations
                    rel["id"] = int(id)

                    # Get internal id for relation
                    rel["rel_id"] = self.database.getId(
                        self.apiKey, rel["rel_id"], table="anime"
                    )

                    rel["type"] = str(rel["type"]).lower().strip()
                    rel["name"] = str(rel["name"]).lower().strip()

                    # Check if relation already exists
                    found = False
                    for e in db_rels:
                        if e["id"] == id and rel["rel_id"] in e["rel_id"]:
                            if e["type"] != rel["type"] or e["name"] != rel["name"]:
                                # TODO - What to do if the relation's name/type is different?
                                pass  # Ignore for now

                            found = True
                            break

                    if not found:
                        k, v = list(zip(*rel.items()))
                        sql = (
                            "INSERT INTO animeRelations ("
                            + ",".join(k)
                            + ") VALUES ("
                            + ", ".join("?" * len(rel))
                            + ");"
                        )
                        self.database.execute(sql, v)

    @cached_request
    def save_mapped(self, id, mapped):
        # mapped must be a list of tuples, each containing two elements: 'api_key' and 'api_id'
        if len(mapped) == 0:
            return

        return  # TODO - Implement this
        with self.database.get_lock():
            for m in mapped:  # Iterate over each external anime
                api_key, api_ip = m

                # Get the id of the external anime
                sql = f"SELECT id FROM indexList WHERE {api_key}=?"

                associated = self.database.sql(sql, (api_ip,))
                if len(associated) == 0:
                    continue

                ass_id = associated[0][0]
                if ass_id != id:  # Merge both ids

                    # Remove new id and merge with old one
                    self.database.remove(id=id)

                    # Merge
                    self.database.sql(
                        f"UPDATE indexList SET {api_key} = ? WHERE id=?",
                        (api_ip, ass_id),
                    )

                    # TODO - Also update animeRelations!

    @cached_request
    def save_pictures(self, id, pictures):
        # pictures must be a list of dicts, each containing two fields: 'url', 'size'
        # return # TODO - Put all that stuff in a queue and process everything at once
        valid_sizes = ("small", "medium", "large", "original")
        data = []
        for pic in pictures:
            if pic["size"] not in valid_sizes or pic["url"] is None:
                continue
            data.append(pic)

        args, out = self.database.procedure("save_picture", id, json.dumps(pictures))

    @cached_request
    def save_broadcast(self, id, w, h, m):
        with self.database.get_lock():
            args, out = self.database.procedure("save_broadcast", id, w, h, m)

    @cached_request
    def save_genres(self, id, genres):
        # Genres must be an iterable of str, the genre name

        if len(genres) == 0:
            return

        def format(g):
            return g.title().strip()

        genres = list(sorted(map(format, set(genres))))

        with self.database.get_lock():
            args, out = self.database.procedure("save_genres", id, json.dumps(genres))

    # Character metadata

    def save_animeography(self, character_id, animes):
        # animes must be a dict with keys being anime ids and values the role of the character
        return  # TODO - Implement this

        with self.database.get_lock():
            for anime_id, role in animes.items():
                sql = "SELECT EXISTS(SELECT 1 FROM characterRelations WHERE id = ? AND anime_id = ?);"
                exists = bool(self.database.sql(sql, (character_id, anime_id))[0][0])

                if exists:
                    # The relation already existed
                    sql = "UPDATE characterRelations SET role = ? WHERE id = ? AND anime_id = ?;"
                    self.database.sql(sql, (role, character_id, anime_id))
                else:
                    # Create new relation
                    sql = "INSERT INTO characterRelations(id, anime_id, role) VALUES(?, ?, ?);"
                    self.database.sql(sql, (character_id, anime_id, role))

            # self.database.save()

    # def save_mapped_characters(self, ) TODO

    def handle_sql_queue(self):
        with self.database.get_lock():
            while not self.queue.empty():
                func, args, kwargs = self.queue.get()
                func(*args, **kwargs)

    def reroute_sql_queue(self, queue):
        old_queue = self.queue
        self.queue = queue

        while not old_queue.empty():
            data = old_queue.get()
            queue.put(data)


class EnhancedSession(requests.Session):
    def __init__(self, timeout=(3.05, 4), api_cache=None):
        self.timeout = timeout
        self.api_cache = api_cache
        return super().__init__()

    def request(self, method, url, **kwargs):
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.timeout

        # Check cache for GET requests
        if self.api_cache and method.upper() == 'GET':
            cached_response = self.api_cache.get(url, method, kwargs.get('params'), kwargs.get('data'))
            if cached_response is not None:
                # Return cached response
                return cached_response

        # Make actual request
        response = super().request(method, url, **kwargs)

        # Cache successful GET responses
        if self.api_cache and method.upper() == 'GET' and response.status_code == 200:
            self.api_cache.set(url, response, method, kwargs.get('params'), kwargs.get('data'))

        return response


class DummyDB:
    """Fake db to cache requests. Will only run SELECT comands"""

    def __init__(self, db) -> NoneType:
        self.db = db
        self.cache = deque()

    def sql(self, sql, *args, **kwargs):
        if sql.startswith("SELECT "):
            return self.db.sql(sql, *args, **kwargs)
        else:
            self.cache.append(("sql", sql, args, kwargs))

    def cache_wrapper(self, func_name):
        def wrapper(*args, **kwargs):
            self.cache.append((func_name, args, kwargs))

        if func_name in ("save",):
            return lambda *args, **kwargs: None
        return wrapper

    def __getattr__(self, name):
        if name in (
            "getId",
            "get_lock",
        ):
            return self.db.__getattribute__(name)

        return self.cache_wrapper(name)
        # return super().__getattr__(name)
