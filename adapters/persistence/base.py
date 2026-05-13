import threading
import queue
import time
from functools import wraps, lru_cache
from contextlib import contextmanager
from typing import Dict, Any, Optional, Tuple

try:
    from adapters.legacy.legacy_classes import NoneDict
    from shared.telemetry.logger import log
except ImportError:  # pragma: no cover - packaged install fallback
    from AnimeManager.adapters.legacy.legacy_classes import NoneDict  # type: ignore
    from AnimeManager.shared.telemetry.logger import log  # type: ignore


class ConnectionPool:
    """Database connection pool for improved performance and resource management"""

    def __init__(self, factory, pool_size=10, max_idle_time=300, health_check_interval=60):
        self.factory = factory  # Function to create new connections
        self.pool_size = pool_size
        self.max_idle_time = max_idle_time
        self.health_check_interval = health_check_interval

        self._pool = queue.Queue(maxsize=pool_size)
        self._created_connections = 0
        self._lock = threading.RLock()
        self._last_health_check = time.time()

        # Initialize pool with minimum connections
        self._initialize_pool()

        # Start health check thread
        self._health_check_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self._health_check_thread.start()

    def _initialize_pool(self):
        """Initialize the connection pool"""
        for _ in range(min(5, self.pool_size)):  # Start with 5 connections
            try:
                conn = self.factory()
                self._pool.put((conn, time.time()))
                self._created_connections += 1
            except Exception as e:
                log("DB_POOL", f"Failed to create initial connection: {e}")

    def get_connection(self, timeout=30):
        """Get a connection from the pool"""
        with self._lock:
            try:
                # Try to get an existing connection
                conn, last_used = self._pool.get_nowait()

                # Check if connection is still valid
                if self._is_connection_valid(conn):
                    return conn
                else:
                    # Connection is invalid, create a new one
                    try:
                        conn.close()
                    except:
                        pass
                    conn = self.factory()
                    self._created_connections += 1
                    return conn

            except queue.Empty:
                # No available connections, create a new one if under limit
                if self._created_connections < self.pool_size:
                    try:
                        conn = self.factory()
                        self._created_connections += 1
                        return conn
                    except Exception as e:
                        log("DB_POOL", f"Failed to create new connection: {e}")
                        raise

                # Wait for a connection to become available
                try:
                    conn, last_used = self._pool.get(timeout=timeout)
                    if self._is_connection_valid(conn):
                        return conn
                    else:
                        try:
                            conn.close()
                        except:
                            pass
                        conn = self.factory()
                        self._created_connections += 1
                        return conn
                except queue.Empty:
                    raise RuntimeError("Connection pool timeout - no connections available")

    def return_connection(self, conn):
        """Return a connection to the pool"""
        with self._lock:
            if self._pool.qsize() < self.pool_size and self._is_connection_valid(conn):
                try:
                    self._pool.put_nowait((conn, time.time()))
                except queue.Full:
                    # Pool is full, close the connection
                    try:
                        conn.close()
                    except:
                        pass
            else:
                # Pool is full or connection is invalid, close it
                try:
                    conn.close()
                except:
                    pass
                self._created_connections -= 1

    def _is_connection_valid(self, conn):
        """Check if a connection is still valid"""
        try:
            # Try a simple query to test the connection
            if hasattr(conn, 'ping'):
                conn.ping(reconnect=False)
            elif hasattr(conn, 'is_connected'):
                return conn.is_connected()
            else:
                # For other connection types, assume valid if not explicitly closed
                return True
        except:
            return False

    def _health_check_loop(self):
        """Background thread to perform health checks and cleanup"""
        while True:
            time.sleep(self.health_check_interval)
            self._perform_health_check()

    def _perform_health_check(self):
        """Perform health check on pooled connections"""
        with self._lock:
            current_time = time.time()
            temp_connections = []

            # Drain the pool and check each connection
            while not self._pool.empty():
                try:
                    conn, last_used = self._pool.get_nowait()

                    # Check if connection has been idle too long
                    if current_time - last_used > self.max_idle_time:
                        try:
                            conn.close()
                        except:
                            pass
                        self._created_connections -= 1
                    elif self._is_connection_valid(conn):
                        temp_connections.append((conn, last_used))
                    else:
                        try:
                            conn.close()
                        except:
                            pass
                        self._created_connections -= 1

                except queue.Empty:
                    break

            # Put valid connections back
            for conn, last_used in temp_connections:
                try:
                    self._pool.put_nowait((conn, last_used))
                except queue.Full:
                    try:
                        conn.close()
                    except:
                        pass
                    self._created_connections -= 1

    def close_all(self):
        """Close all connections in the pool"""
        with self._lock:
            while not self._pool.empty():
                try:
                    conn, _ = self._pool.get_nowait()
                    try:
                        conn.close()
                    except:
                        pass
                except queue.Empty:
                    break
            self._created_connections = 0

    def get_stats(self):
        """Get pool statistics"""
        return {
            'pool_size': self.pool_size,
            'created_connections': self._created_connections,
            'available_connections': self._pool.qsize(),
            'utilization_rate': (self._created_connections - self._pool.qsize()) / max(1, self._created_connections)
        }


class _PooledConnectionHandle:
    """Per-call connection wrapper yielded by :meth:`BaseDB.pooled_connection`.

    Exists purely so that the body of ``with self.pooled_connection() as
    conn_mgr:`` can talk to ``conn_mgr.db`` / ``conn_mgr.cur`` /
    ``conn_mgr.get_cursor()`` exactly like it used to when those were
    instance attributes on the shared ``BaseDB`` object -- only now the
    state is private to a single call, which makes the pool actually
    safe to use from more than one thread at a time. The pool itself
    is responsible for handing out unique ``conn`` objects (and for
    pinging them on checkout); this handle owns the cursor lifecycle
    inside one logical operation.
    """

    __slots__ = ("db", "cur")

    def __init__(self, conn):
        self.db = conn
        self.cur = None

    def get_cursor(self):
        if self.cur is not None:
            try:
                self.cur.close()
            except Exception:
                pass
        # Snapshot the connection locally for the same reason
        # ``EmbeddedMariaDB.get_cursor`` does -- the pool can replace a
        # broken connection underneath us, but the handle's job is to
        # bind a cursor to the connection it was handed, not to chase
        # replacements. ``self.db`` will only be ``None`` here if the
        # pool's ``get_connection`` itself returned ``None``, which it
        # never does in practice; the guard keeps the error message
        # clear if that contract is ever violated.
        db = self.db
        if db is None:
            raise RuntimeError("Database connection not established")
        self.cur = db.cursor(buffered=True)
        return self.cur


class BaseDB:
    """Database manager using sqlite3"""

    THREAD_SAFE = False  # By default, let's assume that it is not thread safe
    USE_CONNECTION_POOL = False  # Enable connection pooling

    def __init__(self, settings=None):
        self.settings = settings or {}
        self.connection_pool = None

        if not self.THREAD_SAFE:
            self.lock = threading.RLock()

        # Initialize connection pool if enabled
        if self.USE_CONNECTION_POOL:
            self._init_connection_pool()

        # Initialize query cache
        self._query_cache = {}
        self._cache_timestamps = {}
        self._cache_max_size = 1000
        self._cache_ttl = 300  # 5 minutes default TTL
        self._cache_stats = {'hits': 0, 'misses': 0, 'evictions': 0}

    def _init_connection_pool(self):
        """Initialize the connection pool"""
        raise NotImplementedError("Subclasses must implement _init_connection_pool")

    def _create_connection(self):
        """Create a new database connection"""
        raise NotImplementedError("Subclasses must implement _create_connection")

    @contextmanager
    def pooled_connection(self):
        """Context manager that yields a per-call connection handle.

        The previous implementation reassigned ``self.db`` and
        ``self.cur`` while the ``with`` block was active and restored
        the originals on exit. That works for a single thread but is
        catastrophic under concurrency: two threads racing through
        ``pooled_connection`` see each other's pool connection in the
        shared attributes, "restore" each other's value, and end up
        running SQL against the wrong connection (or against ``None``).
        This was the root cause behind the recurring
        ``'NoneType' object has no attribute 'cursor'`` / ``'commit'``
        errors during simultaneous search + upsert workloads -- the
        symptoms moved around the code base every time we plugged a
        single leak because the underlying state was being trampled by
        a sibling thread.

        The handle approach below scopes ``db`` / ``cur`` to the
        per-call object, so two threads can hold two pool connections
        simultaneously with zero shared mutable state. ``self.db`` /
        ``self.cur`` are no longer touched here; the long-lived main
        connection used by code paths that don't (yet) flow through
        the pool stays exactly as it was.
        """
        if not self.USE_CONNECTION_POOL:
            yield self
            return

        conn = None
        handle = None
        try:
            conn = self.connection_pool.get_connection()
            handle = _PooledConnectionHandle(conn)
            yield handle
        finally:
            if handle is not None and handle.cur is not None:
                try:
                    handle.cur.close()
                except Exception:
                    pass
            if conn is not None:
                self.connection_pool.return_connection(conn)

    def _get_cache_key(self, sql: str, params: tuple) -> str:
        """Generate a cache key for the query"""
        import hashlib
        key_data = f"{sql}:{str(params)}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _is_cacheable_query(self, sql: str) -> bool:
        """Determine if a query should be cached"""
        sql_upper = sql.upper().strip()
        # Only cache SELECT queries that don't modify data
        return sql_upper.startswith('SELECT') and not any(keyword in sql_upper for keyword in
            ['INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER', 'TRUNCATE'])

    def _get_cached_result(self, cache_key: str) -> Optional[Any]:
        """Get result from cache if valid"""
        if cache_key in self._query_cache:
            timestamp = self._cache_timestamps.get(cache_key, 0)
            if time.time() - timestamp < self._cache_ttl:
                self._cache_stats['hits'] += 1
                return self._query_cache[cache_key]
            else:
                # Cache expired, remove it
                del self._query_cache[cache_key]
                del self._cache_timestamps[cache_key]

        self._cache_stats['misses'] += 1
        return None

    def _set_cached_result(self, cache_key: str, result: Any):
        """Store result in cache"""
        # Evict oldest entries if cache is full
        if len(self._query_cache) >= self._cache_max_size:
            self._evict_oldest_cache_entries()

        self._query_cache[cache_key] = result
        self._cache_timestamps[cache_key] = time.time()

    def _evict_oldest_cache_entries(self):
        """Remove oldest cache entries to make room"""
        if not self._cache_timestamps:
            return

        # Remove 20% of oldest entries
        entries_to_remove = int(len(self._cache_timestamps) * 0.2)
        oldest_keys = sorted(self._cache_timestamps.keys(),
                           key=lambda k: self._cache_timestamps[k])[:entries_to_remove]

        for key in oldest_keys:
            del self._query_cache[key]
            del self._cache_timestamps[key]
            self._cache_stats['evictions'] += 1

    def invalidate_cache(self, pattern: Optional[str] = None):
        """Invalidate cache entries, optionally matching a pattern"""
        if pattern is None:
            # Clear all cache
            self._query_cache.clear()
            self._cache_timestamps.clear()
        else:
            # Clear cache entries matching pattern
            keys_to_remove = [k for k in self._query_cache.keys() if pattern in k]
            for key in keys_to_remove:
                del self._query_cache[key]
                del self._cache_timestamps[key]

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        total_requests = self._cache_stats['hits'] + self._cache_stats['misses']
        hit_rate = (self._cache_stats['hits'] / max(1, total_requests)) * 100

        return {
            'cache_size': len(self._query_cache),
            'max_size': self._cache_max_size,
            'ttl_seconds': self._cache_ttl,
            'hit_rate_percent': hit_rate,
            'total_hits': self._cache_stats['hits'],
            'total_misses': self._cache_stats['misses'],
            'total_evictions': self._cache_stats['evictions']
        }

    def __enter__(self):
        """Use the database as a context manager
        It is good to use the db as a context manager to allow for thread-safe operations
        """
        if not self.THREAD_SAFE:
            self.lock.acquire(True)
        return self.get_lock()

    def get_lock(self):

        return self

    def __exit__(self, *_, close_cursor=True):
        """Exits the context manager"""
        if not self.THREAD_SAFE:
            self.lock.release()

        if close_cursor:
            self.close()

        # return True

    def createNewDb(self):
        """Create a new database"""
        raise NotImplementedError()

    def is_initialized(self):
        """Check if the database is properly initialized"""
        raise NotImplementedError()

    def close(self):
        """Close the connection to the database"""
        if self.cur is not None:
            self.cur.close()

    def sql(self, sql, params=[], save=False, to_dict=False):
        """Run the sql request and can also save or format the output"""

        # Check cache for read-only queries
        cache_key = None
        if not save and self._is_cacheable_query(sql):
            cache_key = self._get_cache_key(sql, tuple(params) if params else ())
            cached_result = self._get_cached_result(cache_key)
            if cached_result is not None:
                return cached_result

        try:
            self.execute(sql, params)

        except Exception as e:
            raise e

        else:
            if save:
                self.save()
                # Invalidate cache on data modification
                self.invalidate_cache()

            elif to_dict:
                out = []
                cols = [e[0] for e in self.cur.description]
                for data in self.cur.fetchall():
                    out.append(NoneDict(keys=cols, values=data, default=None))

                # Cache the result if it's a cacheable query
                if cache_key is not None:
                    self._set_cached_result(cache_key, out)

                return out

            else:
                try:
                    data = self.cur.fetchall()
                except TypeError as e:
                    if e.args[0] == "'NoneType' object is not subscriptable":
                        # Sql request didn't return rows, ignore
                        pass
                    else:
                        raise
                except Exception as e:
                    raise
                else:
                    # Cache the result if it's a cacheable query
                    if cache_key is not None:
                        self._set_cached_result(cache_key, data)

                    return data

    def execute(self, sql, *args):
        """Run the sql command directly"""
        self.cur.execute(sql, *args)

    def executemany(self, sql, *args):
        """Run sql commands as a batch, should be faster than execute()"""
        self.cur.executemany(sql, *args)

    def save(self):
        """Save the current transaction"""
        raise NotImplementedError()

    def procedure(self, name, *args):
        """Run a stored procedure"""
        raise NotImplementedError()

    def exists(self, id, table):
        """Check if an entity exists. Id can be either a single value, a list of values or a dict of key, value pairs."""
        raise NotImplementedError()

    def get(self, id, table):
        """Get the first row that match the id in table. Id can be either a single value, a list of values or a dict of key, value pairs."""
        raise NotImplementedError()

    def getId(self, apiKey, apiId, table="anime", add_meta=False):
        """Should be implemented somewhere else"""
        raise NotImplementedError()

    def set(self, id, data, table, save=True):
        """Either insert or update, depending on if id exists. Id can be either a single value, a list of values or a dict of key, value pairs."""
        # Kinda messy, I would rather not reimplement this method
        raise NotImplementedError()

    def insert(self, data, table, save=True):
        """Insert data in table"""
        raise NotImplementedError()

    def update(self, id, data, table, save=True):
        """Update data for the given id. Id can be either a single value, a list of values or a dict of key, value pairs."""
        raise NotImplementedError()

    def remove(self, id=None, table=None, save=True):
        """Remove all row that match id from a table. Id can be either a single value, a list of values or a dict of key, value pairs."""
        raise NotImplementedError()

    def filter(self, table=None, sort=None, range=(0, 50), order=None, filter=None):
        """Should be implemented somewhere else"""
        raise NotImplementedError()

    def get_all_metadata(self, item):
        """Get metadata from other tables matching id. Can return generators to improve performances."""
        for key in item.metadata_keys:
            item[key] = lambda id=item.id, key=key: self.get_metadata(id, key)

        return item

    def get_all_metadata_bulk(self, items, use_eager_loading=True):
        """Get metadata for multiple items in a single batch operation to avoid N+1 queries.

        Args:
            items: List of items with metadata_keys and id attributes
            use_eager_loading: If True, load all metadata upfront. If False, use lazy loading.

        Returns:
            List of items with metadata populated
        """
        if not items:
            return items

        if use_eager_loading:
            return self._get_all_metadata_eager(items)
        else:
            # Fallback to original lazy loading
            return [self.get_all_metadata(item) for item in items]

    def _get_all_metadata_eager(self, items):
        """Eager load metadata for multiple items to avoid N+1 queries"""
        # Collect all unique metadata keys and item IDs
        all_keys = set()
        item_ids = []

        for item in items:
            if hasattr(item, 'metadata_keys') and hasattr(item, 'id'):
                all_keys.update(item.metadata_keys)
                item_ids.append(item.id)

        if not all_keys or not item_ids:
            return items

        # Remove duplicates
        item_ids = list(set(item_ids))
        all_keys = list(all_keys)

        # Build metadata map: {item_id: {key: [values]}}
        metadata_map = self._fetch_bulk_metadata(item_ids, all_keys)

        # Populate items with metadata
        for item in items:
            if hasattr(item, 'id') and item.id in metadata_map:
                item_metadata = metadata_map[item.id]
                for key in item.metadata_keys:
                    if key in item_metadata:
                        # Store actual values instead of lazy lambdas
                        values = item_metadata[key]
                        item[key] = values[0] if len(values) == 1 else values
                    else:
                        item[key] = None

        return items

    def _fetch_bulk_metadata(self, item_ids, keys):
        """Fetch metadata for multiple items and keys in batch queries"""
        metadata = {}

        for key in keys:
            # Build query for this metadata key
            placeholders = ','.join(['?' for _ in item_ids])
            sql = f"SELECT id, value FROM {key} WHERE id IN ({placeholders})"

            try:
                results = self.sql(sql, item_ids)
                if results:
                    for result in results:
                        item_id, value = result
                        if item_id not in metadata:
                            metadata[item_id] = {}
                        if key not in metadata[item_id]:
                            metadata[item_id][key] = []
                        metadata[item_id][key].append(value)
            except Exception as e:
                # Log error but continue with other keys
                self.log("ERROR", f"Failed to fetch bulk metadata for key {key}: {e}")

        return metadata

    def get_metadata(self, id, key):
        """Get metadata for a specific id and key. Should not return a generator."""
        raise NotImplementedError()

    def save_metadata(self, id, metadata):
        """Save metadata for the given id."""
        raise NotImplementedError()

    def _iterate_ids(self, id):
        """Convert id into a list of key, value pairs. Id can be either a single value, a list of values or a dict of key, value pairs."""

        if isinstance(id, (list, tuple)):
            for i in id:
                yield {"id": i}
        elif isinstance(id, dict):
            yield id
        else:
            yield {"id": id}

    def id_wrapper(*func, single_id=False):
        """Wrapper to handle the different id format"""

        def decorated(func):
            @wraps(func)
            def wrapper(self, *args, **kwargs):
                if "id" in kwargs:
                    ids = kwargs.pop("id")
                elif not args:
                    # No id provided?
                    raise ValueError("No id was provided!")
                else:
                    ids, args = args[0], args[1:]

                out = []
                with self:  # Get lock
                    iter = self._iterate_ids(ids)
                    if single_id:
                        iter = [next(iter)]

                    for id in iter:
                        try:
                            output = func(self, id["id"], *args, **kwargs)
                        except Exception as e:
                            # TODO - Maybe handle some exceptions, like disconnection etc
                            raise e
                        else:
                            out.append(output)

                if kwargs.get("save", False) is True:
                    self.commit()

                if len(out) == 1:
                    return out[0]
                else:
                    return out

            return wrapper

        if func:
            return decorated(func[-1])
        else:
            return decorated

    def log(self, *args, **kwargs):
        # TODO - Correct formatting and stuff?
        return log(*args, **kwargs)
