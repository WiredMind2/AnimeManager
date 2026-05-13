Persistence
===========

Persistence is the most legacy-heavy part of AnimeManager. The local
catalogue, the torrent index, the user tags and the cached metadata
all live in the same relational store; three different database
backends are supported; and the migration from the original
multi-inheritance ``Manager`` god class to a port-based application
service is still in progress. This page explains how the database
layer is structured today, what each component is responsible for,
and how the boundary between domain code and infrastructure is
maintained.

Layered view
------------

::

    ┌────────────────────────────────────────────────────────────┐
    │ AnimeApplicationService                                    │
    │   uses AnimeRepositoryPort (Protocol)                      │
    └────────────────────────────────┬───────────────────────────┘
                                     │
                                     ▼
    ┌────────────────────────────────────────────────────────────┐
    │ LegacyAnimeRepositoryAdapter                               │
    │   • single implementation of AnimeRepositoryPort           │
    │   • translates Anime <-> AnimeEntity via from_legacy_anime │
    └────────────────────────────────┬───────────────────────────┘
                                     │
                                     ▼
    ┌────────────────────────────────────────────────────────────┐
    │ DatabaseManager (components/)                              │
    │   • get_connection context manager                         │
    │   • query builder gateway (build_anime_list_query)         │
    │   • upsert_anime_batch / enqueue_anime / save_torrent      │
    │   • optional PersistenceQueue (batched async writes)       │
    └────────────────────────────────┬───────────────────────────┘
                                     │ delegates SQL/IO
                                     ▼
    ┌────────────────────────────────────────────────────────────┐
    │ BaseDB subclasses (db_managers/)                           │
    │   • SQLite      (thread_safe_db wrapping db_instance)      │
    │   • MySQL       (server-managed)                           │
    │   • EmbeddedMariaDB (in-process)                           │
    └────────────────────────────────────────────────────────────┘

The hexagonal application layer only knows about
:class:`backend.ports.interfaces.AnimeRepositoryPort`. The bridge
between that port and the legacy concrete code lives in
:class:`backend.adapters.legacy_runtime.LegacyAnimeRepositoryAdapter`.
Everything below it is infrastructure and will be replaced
incrementally without touching the application layer.

Backends under :mod:`db_managers`
---------------------------------

:mod:`db_managers` is a small registry of :class:`db_managers.base.BaseDB`
subclasses. The package's ``__init__`` exposes the mapping that
:class:`getters.Getters` uses to pick a backend from
:file:`settings.json`::

    databases = {
        "EmbeddedMariaDB": EmbeddedMariaDB,
        "MySQL": MySQL,
        "SQLite": thread_safe_db,
    }

* :class:`db_managers.base.BaseDB` is the common contract. It tracks
  whether the backend is thread-safe (``THREAD_SAFE``), whether
  pooled connections should be used (``USE_CONNECTION_POOL``), and
  owns the small SELECT result cache shared by every subclass. The
  module also ships a connection pool implementation
  (:class:`db_managers.base.ConnectionPool`) for backends that opt in.
* :class:`db_managers.dbManager.thread_safe_db` is the SQLite backend.
  It wraps the unsynchronised :class:`db_managers.dbManager.db_instance`
  in a dedicated background thread fed by a LIFO task queue: every
  ``db.sql(...)`` / ``db.save(...)`` / ``db.procedure(...)`` call is
  marshalled onto that single thread and the result is returned via
  a per-call :class:`queue.Queue`. The shim makes a synchronous,
  in-process SQLite database safe to share across the rest of the
  application without changing the call sites. It also keeps a
  :class:`db_managers.dbManager.QueryCache` of SELECT results with a
  5-minute TTL that the wrapper invalidates whenever an
  INSERT/UPDATE/DELETE statement targets a known table.
* :class:`db_managers.mySql.MySQL` is the client-managed MySQL
  backend. The user provides connection details through the
  ``database_managers.MySQL`` block in :file:`settings.json`, the
  backend connects through ``mysql-connector-python``, and the
  schema is created from :file:`db_managers/db_model.sql` and
  :file:`db_managers/procedures.sql` on first connect. Suitable for
  multi-user deployments where the database lives on a separate host.
* :class:`db_managers.embeddedMariaDB.EmbeddedMariaDB` is the
  in-process MariaDB backend used as the default in the embedded
  desktop runtime. It bootstraps a per-user MariaDB instance under
  the AppData directory (``mariadb/server`` and ``mariadb/data``),
  unpacks the bundled ``lib/mariadb-winx64.zip`` archive when no
  server binaries are present, spawns ``mysqld.exe`` as a child
  process, and exposes the same ``BaseDB`` surface as the other
  backends. It opts into connection pooling
  (``USE_CONNECTION_POOL = True``).

All three backends accept their settings as the single ``settings``
constructor argument. The shape of that dictionary is the matching
sub-block under ``database_managers`` in :file:`settings.json`; see
:doc:`configuration` for the field-by-field reference.

The :class:`components.database_manager.DatabaseManager`
---------------------------------------------------------

:class:`components.database_manager.DatabaseManager` is the gateway
the rest of the codebase consumes. It is intentionally narrow: every
write goes through one of its methods, every read is guarded by
:meth:`DatabaseManager.get_connection`, and every dynamic query goes
through the centralised query builder rather than ad-hoc string
formatting.

Responsibilities
~~~~~~~~~~~~~~~~

* **Connection lifecycle.** :meth:`DatabaseManager.get_connection`
  yields the underlying :class:`db_managers.base.BaseDB` either
  directly (for pooled backends) or under the backend's
  :meth:`get_lock` (for the non-thread-safe path), translates any
  exception into a logged ``DB_ERROR`` event, and lets the caller
  reuse the existing telemetry instrumentation.
* **Search and listing.** :meth:`DatabaseManager.search_anime`
  cleans the user-supplied terms, runs the
  ``search_anime_fast`` stored procedure, materialises the result
  rows into :class:`classes.Anime` instances, and bulk-loads the
  per-anime metadata via :meth:`BaseDB.get_all_metadata_bulk`.
  :meth:`DatabaseManager.get_anime_list` builds its query arguments
  by delegating to
  :func:`core.query_builder.build_anime_list_query` -- which is a
  whitelist-only criterion-to-SQL translator -- and exposes a
  cursor-style ``get_next`` callable for pagination.
* **Single-row writes.** :meth:`DatabaseManager.update_anime`
  delegates to the backend's ``db.save(anime)`` helper inside the
  shared connection context manager so callers never need to know
  about the backend-specific upsert dialect.
* **Batched writes.** :meth:`DatabaseManager.upsert_anime_batch`
  loops over a list of :class:`classes.Anime` instances, calls
  ``db.save`` for each, and emits a ``db.upsert_anime_batch_ms``
  timing plus a ``db.upserts_committed`` counter through
  :func:`core.telemetry.get_telemetry`. This is the persistence sink
  used by :class:`components.api_coordinator.APICoordinator` so all
  search results land through a single boundary.
* **Async batched writes.**
  :meth:`DatabaseManager.enable_batched_writes` spins up an internal
  :class:`core.persistence_queue.PersistenceQueue` that buffers
  records up to ``batch_size`` (or ``max_latency_ms``) and flushes
  them through :meth:`upsert_anime_batch`. Disabled by default to
  preserve legacy synchronous semantics during the migration; opt-in
  via :meth:`enable_batched_writes` once a caller is ready.
  :meth:`enqueue_anime` falls back to a synchronous upsert when the
  queue is disabled so callers never silently lose data.
* **Torrent indexing.** :meth:`DatabaseManager.save_torrent` keeps
  the ``torrentsIndex`` and ``torrents`` tables consistent through
  idempotent existence checks, JSON-encodes the tracker list, and
  commits once per torrent. :meth:`DatabaseManager.get_torrent_data`
  is the matching read path used by
  :class:`components.download_manager.DownloadManager` when the
  caller only supplied a hash.
* **Metadata batches.**
  :meth:`DatabaseManager.upsert_metadata_batch` is the bulk
  equivalent for per-anime metadata maps and is used by the
  ingestion pipeline when secondary providers contribute additional
  fields after the primary upsert.

Threading
~~~~~~~~~

The manager holds a single :class:`threading.RLock` that is only used
when the backend itself is non-thread-safe; pooled backends rely on
the connection pool instead. The optional persistence queue runs on
its own background worker (``DBPersistQueue``) and the queue stops
draining when :meth:`DatabaseManager.close` is called.

Repository boundary
-------------------

The hexagonal core never imports
:class:`components.database_manager.DatabaseManager` directly. It
consumes the :class:`backend.ports.interfaces.AnimeRepositoryPort`
:class:`typing.Protocol`:

.. code-block:: python

   class AnimeRepositoryPort(Protocol):
       def search(self, query: str, limit: int = 50) -> list[AnimeEntity]: ...
       def list_anime(
           self,
           criteria: str,
           list_start: int,
           list_stop: int,
           hide_rated: Optional[bool],
           user_id: Optional[int],
       ) -> tuple[list[AnimeEntity], bool]: ...
       def get_anime(self, anime_id: int) -> Optional[AnimeEntity]: ...

The single implementation is
:class:`backend.adapters.legacy_runtime.LegacyAnimeRepositoryAdapter`.
It owns a private :class:`DatabaseManager` and a reference back to
the :class:`backend.adapters.legacy_runtime.LegacyRuntime`. Its
methods are intentionally thin:

* :meth:`LegacyAnimeRepositoryAdapter.search` calls
  :meth:`DatabaseManager.search_anime` and maps every legacy
  :class:`classes.Anime` row through
  :func:`backend.domain.entities.from_legacy_anime` so the
  application service only ever sees the immutable
  :class:`backend.domain.entities.AnimeEntity` dataclass.
* :meth:`LegacyAnimeRepositoryAdapter.list_anime` delegates to
  :meth:`DatabaseManager.get_anime_list` and surfaces a boolean
  "more results available" flag derived from the manager's
  cursor-style ``next_page`` callable.
* :meth:`LegacyAnimeRepositoryAdapter.get_anime` falls back to a
  direct ``database.get(anime_id, table="anime")`` lookup because
  there is no equivalent ``DatabaseManager`` method yet. Both
  :class:`classes.Anime` and dictionary returns are accepted.

The adapter pattern is what keeps the migration tractable: any one
of the three pieces -- port, adapter, manager -- can be replaced
in isolation. The composition root in
:class:`backend.adapters.legacy_runtime.LegacyRuntime` (built by
:func:`backend.composition.build_embedded_facade`) is the single
function that knows how to wire a real ``DatabaseManager`` to a
real :class:`db_managers.base.BaseDB` subclass and hand it to the
application service.

.. seealso::

   * ADR 0001 - embedded runtime model that motivates the local
     database and the embedded MariaDB bundle.
   * ADR 0002 - application contracts first, which is why the
     repository port lives in :mod:`backend.ports.interfaces`.
   * ADR 0003 - dependency direction rules.
   * :doc:`../developer/api_db_pipeline` for the full ingestion
     pipeline that uses :meth:`DatabaseManager.upsert_anime_batch`
     as its persistence sink.
