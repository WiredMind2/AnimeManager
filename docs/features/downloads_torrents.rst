Downloads and Torrent Orchestration
===================================

The download feature stitches three independent collaborators — the
torrent client, the filesystem backend, and the database — into one
narrow public API. The orchestration code lives in
:class:`application.services.download_manager.DownloadManager`; the
concrete torrent backends live in :mod:`adapters.torrent`; the storage
backends live in :mod:`adapters.file`. The legacy event-bus path that
used to publish ``download.start`` / ``download.cancel`` topics has been
removed: callers now invoke the manager through
:class:`adapters.torrent.download_adapter.DownloadAdapter`, which is
wired in :func:`composition.root.build_embedded_facade`.

Lifecycle
---------

::

    ┌─────────────────────────────────────────────────────────────┐
    │ Client SDK (Tk / HTTP / Next.js) -> ClientSDK.download_*  │
    └──────────────────────────────┬──────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────┐
    │ EmbeddedClientFacade -> AnimeApplicationService -> port     │
    │   DownloadPort (ports.interfaces)                         │
    └──────────────────────────────┬──────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────┐
    │ DownloadAdapter                                             │
    │   • holds DownloadManager + torrent + file + DB collabs     │
    │   • translates port exceptions into AnimeManagerError       │
    └──────────────────────────────┬──────────────────────────────┘
                                   │ download_file(anime_id, url=...)
                                   ▼
    ┌─────────────────────────────────────────────────────────────┐
    │ DownloadManager.download_file()                             │
    │   1. enqueue DownloadTask                                   │
    │   2. return status_queue to caller                          │
    └──────────────────────────────┬──────────────────────────────┘
                                   │ processor thread
                                   ▼
    ┌─────────────────────────────────────────────────────────────┐
    │ ThreadPoolExecutor (max_concurrent_downloads)               │
    │   _execute_download(task):                                  │
    │     prepare_torrent -> save_torrent -> start_download       │
    └──────────────────────────────┬──────────────────────────────┘
                                   │
                  ┌────────────────┼────────────────┐
                  ▼                ▼                ▼
       ┌────────────────┐ ┌────────────────┐ ┌──────────────┐
       │ BaseTorrent    │ │ BaseFile       │ │ Database     │
       │ Manager        │ │ Manager        │ │ Manager      │
       │ (qB / Trans /  │ │ (Local / FTP)  │ │ .save_torrent│
       │ LibTorrent)    │ │                │ │ .get_torrent │
       └────────────────┘ └────────────────┘ └──────────────┘

The :class:`application.services.download_manager.DownloadTask` value
object captures everything the executor needs to drive one download:
anime id, URL (HTTP or magnet) or pre-existing torrent hash, optional
user id for tagging, a status queue used to signal progress, a
``cancelled`` flag, and a wall-clock start timestamp. The status queue
is returned to the caller synchronously by
:meth:`DownloadManager.download_file` so the client can react to
``True`` (started successfully) or ``False`` (preparation or
scheduling failed).

The manager keeps its own processor thread that drains the
``_download_queue`` and submits each task to the bounded executor.
``close()`` flips the stopping event, cancels every active
:class:`DownloadTask`, and waits for the executor to drain so embedded
runtimes can shut down cleanly.

Torrent manager abstraction
---------------------------

Every torrent client backend implements the
:class:`adapters.torrent.base.BaseTorrentManager` interface:

.. code-block:: python

   class BaseTorrentManager(Logger):
       name = ""

       def connect(self): ...
       def login_dialog(self): ...
       def add(self, hashes_or_magnets, path=None): ...
       def list(self, filter=None): ...
       def move(self, hashes, path): ...
       def delete(self, hashes): ...
       def pause(self, hashes): ...
       def resume(self, hashes): ...

The base class wires the settings dict into ``self.settings``,
optionally opens a Tk login dialog when ``update=True``, and calls
``initialize()`` so concrete subclasses can build their HTTP client or
native handle.

Registered backends (see :data:`adapters.torrent.managers`):

* :mod:`adapters.torrent.qbittorrent`
  (:class:`adapters.torrent.qbittorrent.qBittorrent`) — production
  default. Uses ``qbittorrentapi`` against a running qBittorrent Web
  UI. ``connect()`` runs in a background thread so the UI does not
  block on slow Web UI handshakes.
* :mod:`adapters.torrent.transmission`
  (:class:`adapters.torrent.transmission.Transmission`) — RPC client
  for Transmission. Torrent objects are translated into the project's
  :class:`adapters.persistence.models.Torrent` representation.
* :mod:`adapters.torrent.libtorrent`
  (:class:`adapters.torrent.libtorrent.LibTorrent`) — in-process
  libtorrent session. Loaded only when the libtorrent binary is
  available; :mod:`adapters.torrent` swallows ``ImportError`` and sets
  ``LIBTORRENT_AVAILABLE = False`` so the rest of the application
  continues to load. When ``LIBTORRENT_DAEMON_URL`` is set, the
  optional :class:`adapters.torrent.libtorrent_remote.LibTorrentRemote`
  daemon client may be selected instead.

A Deluge adapter exists under :mod:`adapters.torrent.deluge` but is
**not** registered in :data:`adapters.torrent.managers` and therefore
cannot be selected at runtime.

The registry :data:`adapters.torrent.managers` exposes each backend
keyed by its ``name`` attribute (``"qBittorrent"``, ``"Transmission"``,
``"LibTorrent"``). Selection happens through :file:`settings.json`
under ``torrent_managers.last_tm_used``, and the provider settings
live under the matching sub-dictionary.

Errors are funneled through
:func:`adapters.torrent.base.BaseTorrentManager.error_wrapper`, which
re-raises any exception as a
:class:`adapters.torrent.base.TorrentException`. This gives the
download manager a single exception type to catch when scheduling work.

File manager abstraction
------------------------

The torrent client writes the actual bytes, but AnimeManager owns the
folder layout. That responsibility lives in :mod:`adapters.file`.

:class:`adapters.file.base.BaseFileManager` defines the minimal
interface:

.. code-block:: python

   class BaseFileManager(Logger):
       name = ""

       def open(self, path, mode="r", **kwargs): ...
       def mkdir(self, path): ...
       def list(self, path): ...
       def exists(self, path): ...
       def isdir(self, path): ...
       def isfile(self, path): ...
       def delete(self, path): ...
       def change_path(self, root): ...

Two backends are shipped:

* :class:`adapters.file.local_disk.LocalFileManager` (``name="Local"``)
  — the default. Uses standard :func:`open`, ``os.path`` helpers and
  a small async layer built on :mod:`aiofiles` and a private
  :class:`concurrent.futures.ThreadPoolExecutor`. It also implements
  a short-lived file cache to keep repeated reads cheap.
* :class:`adapters.file.FTP.FTPFileManager` (``name="FTP"``) — remote
  storage backed by :mod:`ftplib`. Suitable for users whose anime
  library lives on a NAS.

The registry :data:`adapters.file.managers` mirrors the torrent
counterpart, with selection happening through :file:`settings.json`
under ``file_managers.last_fm_used``.

How :class:`DownloadManager` glues them together
------------------------------------------------

The manager is intentionally narrow:

1. **Validate inputs.** ``download_file(anime_id, url=None, hash_value=None, user_id=None)``
   rejects calls that provide neither a URL nor a hash and logs the
   reason. Any URL goes through :func:`shared.security.validate_url`
   before a request is issued; failures are recorded under
   ``DOWNLOAD_MANAGER`` with the rejection reason. Magnet URIs bypass
   the HTTP validation because they never produce network traffic
   directly.
2. **Prepare the torrent.** ``_prepare_torrent`` resolves the task's
   ``url``/``hash_value`` into a
   :class:`adapters.persistence.models.Torrent`. Magnet URIs are
   translated through :meth:`adapters.persistence.models.Torrent.from_magnet`.
   HTTP torrents are downloaded with explicit ``stream=True`` and a
   15 s timeout, ``Content-Length`` is checked before reading, and the
   payload is capped at 10 MiB to defend against abusive sources. For
   tasks that only carry a hash the manager pulls the cached torrent
   blob through :meth:`DatabaseManager.get_torrent_data`.
3. **Persist torrent metadata.** ``_save_torrent`` delegates to the
   injected :class:`application.services.database_manager.DatabaseManager`
   so the ``torrents`` and ``torrentsIndex`` tables stay behind a
   single gateway. The database manager handles the JSON-encoded
   tracker list and idempotent upserts.
4. **Start the torrent.** ``_start_download`` calls
   :meth:`BaseTorrentManager.add` with the magnet form of the torrent
   and the target folder resolved by ``_get_anime_folder`` (a hook
   that integrates the file manager). When the torrent client returns
   handles, ``_move_torrents_to_folder`` issues a follow-up
   :meth:`BaseTorrentManager.move` so the user's library layout
   remains consistent regardless of which backend processed the add.

Status and cancellation
-----------------------

The manager exposes observability primitives:

* :meth:`DownloadManager.get_download_status(anime_id)` returns the
  status dictionary for the active task, or ``None``.
* :meth:`DownloadManager.get_active_downloads` returns every currently
  running task in a list of dictionaries, suitable for an admin
  endpoint.
* The per-task status queue returned by ``download_file`` is the
  push-style equivalent: a ``True`` value lands on the queue when the
  worker starts processing the task, and a ``True`` / ``False`` value
  lands once the torrent has been handed off to the torrent client.

Cancellation is cooperative: :meth:`DownloadManager.cancel_download`
flips the task's ``cancelled`` flag and removes it from the active
map. Already running torrents stay alive in the torrent client unless
the caller also invokes torrent-manager removal APIs exposed through
:class:`DownloadAdapter`.

Composition rules
-----------------

The download feature is the canonical example of ADR 0005 in action:
:class:`DownloadManager` does **not** inherit from
``DatabaseManager``, ``BaseTorrentManager`` or ``BaseFileManager``.
Every collaborator is provided through a ``set_*`` method by
:class:`adapters.torrent.download_adapter.DownloadAdapter`, which is
constructed in :func:`composition.root.build_embedded_facade`. The
adapter is the only object that knows about all four collaborators,
which keeps the surface area of the manager intentionally small and
trivially mockable from tests.
