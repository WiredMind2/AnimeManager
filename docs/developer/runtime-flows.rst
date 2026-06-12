Runtime Flows
=============

AnimeManager has exactly one startup script — ``run.py`` — and one
in-package dispatcher — :mod:`bootstrap` — per ADR 0006. Both client
adapters (the embedded Tk desktop client and the FastAPI HTTP
client) share the same composition root and the same embedded
backend; only the last hop differs.

This document walks through the full call chain from process start
up to a serving client, so that anyone debugging a startup issue can
map a log line to a specific layer.

.. seealso::

   * `ADR 0001 — Embedded Runtime Model <../../docs/adr/0001-embedded-runtime-model.md>`_
   * `ADR 0006 — Package Layout and Single Entrypoint <../../docs/adr/0006-package-layout-and-single-entrypoint.md>`_

Shared bootstrap chain
----------------------

Every supported mode (``gui``, ``api``, future ``cli`` tasks)
follows the same pipeline up to the point where the mode-specific
handler takes over:

.. code-block:: text

   $ python run.py [mode] [--host HOST] [--port PORT]

       run.py
         |
         |  argparse.ArgumentParser parses sys.argv
         |  multiprocessing.freeze_support()
         |  _ensure_package_path()  (adds repo root to sys.path)
         |
         v
       bootstrap.main(mode=..., **kwargs)
         |
         |  validates mode against bootstrap._MODES
         |  guards against re-entry in spawned subprocesses
         |  os.environ["ANIMEMANAGER_BOOTSTRAP"] = mode
         |
         v
       bootstrap._MODES[mode](**kwargs)
         |
         v
       (mode-specific handler: _run_gui / _run_api / ...)

The dispatcher in :mod:`bootstrap` is intentionally tiny: it parses
arguments only via ``run.py``, then forwards to a callable that
lives in the same module. New runtime modes register by appending
to the ``_MODES`` dictionary; no new entrypoint is needed.

GUI flow (``mode=gui``)
-----------------------

The default mode launches the embedded Tk desktop client. The
backend is composed in-process and the client talks to it through
the shared SDK; there is no socket and no separate server process.

.. code-block:: text

   python run.py            (or `python run.py gui`)
       |
       v
   run.main(argv=None)
       |  args.mode == "gui"
       v
   bootstrap.main(mode="gui")
       |
       v
   bootstrap._run_gui()
       |  from clients.tk import run
       |  multiprocessing.freeze_support()
       |  proc = multiprocessing.current_process()
       |  if proc.name == "MainProcess":
       v
   clients.tk.run()                            (clients/tk/__init__.py)
       |
       v
   clients.tk.app.run()                        (clients/tk/app.py)
       |  sdk = ClientSDK()
       |
       v
   ClientSDK.__init__()                        (clients/sdk.py)
       |  self._facade = _facade()
       v
   _facade()  -> build_embedded_facade()       (cached, lru_cache size=1)
       |
       v
   composition.root.build_embedded_facade()    (composition/root.py)
       |
       v
   backend.composition.build_embedded_facade() (backend/composition.py)
       |
       |  runtime      = LegacyRuntime()
       |  repository   = LegacyAnimeRepositoryAdapter(runtime)
       |  metadata     = LegacyMetadataProviderAdapter(runtime, repository)
       |  download     = LegacyDownloadAdapter(runtime, repository)
       |  user_actions = LegacyUserActionsAdapter(runtime)
       |  service      = AnimeApplicationService(
       |                     anime_repository=repository,
       |                     metadata_provider=metadata,
       |                     download_port=download,
       |                     user_actions_port=user_actions,
       |                 )
       |  facade       = EmbeddedClientFacade(service)
       v
   AnimeManagerTkClient(sdk).run()
       |
       v
   clients.tk.views.AnimeBrowserView
       |
       v
   clients.tk.presenters.AnimeBrowserPresenter
       |
       v
   tkinter mainloop (blocking)

While the Tk mainloop runs, every user gesture (search, list, torrent
search/start/cancel, settings write, tag/like/seen, search-term edits)
becomes an :class:`clients.sdk.ClientSDK` call, which
calls the :class:`backend.interfaces.embedded.facade.EmbeddedClientFacade`,
which routes through the
:class:`backend.application.service.AnimeApplicationService` and the
port protocols defined in :mod:`backend.ports.interfaces`. The
legacy adapters under :mod:`backend.adapters.legacy_runtime`
translate each call into the existing
:class:`components.database_manager.DatabaseManager`,
:class:`components.api_coordinator.APICoordinator`, and
:class:`components.download_manager.DownloadManager` infrastructure.

The lifecycle ends when the user closes the Tk window. Because the
embedded facade is a process-local object, no shutdown handshake is
required; Python garbage-collects the graph when the interpreter
exits.

HTTP flow (``mode=api``)
------------------------

The ``api`` mode launches the HTTP client adapter through Uvicorn.
The HTTP layer is **not** a privileged backend (ADR 0001): it is a
peer client that consumes the same SDK as the Tk client. The
embedded backend is composed lazily, inside the worker process, the
first time a request hits the SDK.

.. code-block:: text

   python run.py api --host 0.0.0.0 --port 8081
       |
       v
   run.main(argv=None)
       |  args.mode == "api"
       |  kwargs = {"host": args.host, "port": args.port}
       v
   bootstrap.main(mode="api", host="0.0.0.0", port=8081)
       |
       v
   bootstrap._run_api(host="0.0.0.0", port=8081)
       |
       |  import uvicorn                                   (hard requirement)
       |  from clients.http.app import app                 (import check)
       |
       v
   uvicorn.run("clients.http.app:app", host=host, port=port)
       |
       |  uvicorn spawns/serves the ASGI worker
       v
   clients.http.app:app   (FastAPI instance defined at module load time)
       |
       |  routes:
       |    GET  /                  -> liveness probe
       |    GET  /anime/{anime_id}  -> get_sdk().get_anime(...)
       |    GET  /animelist         -> get_sdk().get_anime_list(...)
       |    GET  /search            -> get_sdk().search_anime(...)
       |    POST /download/{id}     -> get_sdk().start_download(...)
       |    GET  /download/progress -> get_sdk().get_download_progress(...)
       |    POST /download/cancel/{id} -> get_sdk().cancel_download(...)
       |    GET  /download/active      -> get_sdk().get_active_downloads()
       |    GET  /torrents/search      -> get_sdk().search_torrents(...)
       |    POST /tag/{id}             -> get_sdk().set_tag(...)
       |    POST /like/{id}            -> get_sdk().set_like(...)
       |    POST /seen/{id}            -> get_sdk().mark_seen(...)
       |    GET  /state/{id}           -> get_sdk().get_user_state(...)
       |    GET/POST/DELETE /search-terms/{id}
       |                               -> get_sdk().get/add/remove_search_term(...)
       |    GET/PATCH /settings        -> get_sdk().get/update_settings(...)
       |
       v
   get_sdk()  -> ClientSDK()                           (cached, lru_cache size=1)
       |
       v
   (same composition chain as the GUI path)
       |
       v
   build_embedded_facade()
       |
       v
   EmbeddedClientFacade -> AnimeApplicationService -> ports -> legacy adapters

Domain errors raised by the application service surface as
``AnimeManagerError`` subclasses. The route handlers translate them
through ``_map_error`` into FastAPI ``HTTPException`` instances with
status codes consistent with ADR 0004 (``ValidationError`` -> 400,
``NotFoundError`` -> 404, everything else -> 500).

Why every flow ends at the same composition root
-------------------------------------------------

Both ``_run_gui`` and ``_run_api`` ultimately call
:func:`composition.root.build_embedded_facade`, which delegates to
:func:`backend.composition.build_embedded_facade`. That single
function owns the dependency graph. Tests, future clients (Qt,
CLI), and packaging scripts can all rebuild the same graph by
calling it — and *only* by calling it.

Whenever the legacy infrastructure is replaced (e.g. when an
``AnimeRepositoryPort`` gets a clean adapter), the only edit needed
is to swap the implementation bound in ``backend/composition.py``.
Neither :mod:`run`, nor :mod:`bootstrap`, nor any client adapter
needs to change.

Torrent persistence across restarts
-----------------------------------

* **qBittorrent / Transmission** — the external daemon owns session
  state. AnimeManager reconnects via API after restart; nothing is
  re-added from the database.
* **Embedded LibTorrent** — fast-resume files under
  ``<dataPath>/.libtorrent_resume/`` (one ``{info_hash}.resume`` per
  torrent). On startup, :mod:`adapters.torrent.libtorrent` loads these
  into a fresh session before serving downloads. The ``torrents``
  table also stores ``save_path`` so a magnet re-add can recover when a
  resume file is missing but files remain on disk. Graceful shutdown
  (HTTP lifespan / Tk close) calls :meth:`LegacyDownloadAdapter.close`
  to flush resume data before exit.
