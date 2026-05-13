Extension Points
================

AnimeManager is built so that the most common extensions —
a new metadata provider, a new database backend, a new torrent
client, a new client adapter, or a new bootstrap mode — slot into
the existing architecture without touching the application core.
This document is the recipe for each of those five extensions.

Every recipe ends with the same reminder: ADR 0003 dependency
direction rules apply. New code may only import *down* the layer
stack, never *up*. ``docs/developer/layer-contracts.rst`` has the
authoritative matrix; the architecture suite under
``tests/architecture/`` is the mechanical enforcement.

.. seealso::

   * `ADR 0003 — Dependency Direction Rules <../../docs/adr/0003-dependency-rules.md>`_
   * `ADR 0005 — Composition Over Inheritance <../../docs/adr/0005-composition-over-inheritance.md>`_
   * `ADR 0006 — Package Layout and Single Entrypoint <../../docs/adr/0006-package-layout-and-single-entrypoint.md>`_

Adding a new metadata provider
------------------------------

Metadata providers (AniList, MAL, Jikan, Kitsu, ...) are loaded
dynamically by :class:`animeAPI.AnimeAPI`. The loader walks
``animeAPI/`` for ``.py`` files (skipping a small ignore list) and,
for each one, imports a class named ``<filename>Wrapper``. That is
the entire registration mechanism — there is no separate manifest.

Steps to add a new provider ``MyProvider``:

1. Create ``animeAPI/MyProvider.py``.
2. Implement a class ``MyProviderWrapper`` that exposes the methods
   :class:`components.api_coordinator.APICoordinator` expects
   (``search``, ``anime``, ``character``, ``season``, ``schedule``,
   etc., as appropriate). Use the existing wrappers
   (``AnilistCo.py``, ``JikanMoe.py``) as the reference.
3. Keep the wrapper inside the :mod:`animeAPI` package; do not
   import :mod:`adapters`, :mod:`application`, :mod:`clients`, or
   :mod:`composition`. Wrappers are infrastructure, not application
   code.
4. If your provider needs configuration, surface it through the
   existing settings file rather than reading environment variables
   ad hoc; the :class:`shared.config.ConfigProvider` is the canonical
   gateway.
5. Add unit tests under ``tests/unit/animeAPI/`` exercising the
   wrapper with HTTP responses faked out.

The :class:`backend.adapters.legacy_runtime.LegacyMetadataProviderAdapter`
already binds :class:`components.api_coordinator.APICoordinator` to
the :class:`backend.ports.interfaces.MetadataProviderPort`, so the
new provider is reachable from the application service the moment
``AnimeAPI`` picks it up. No backend, no client, and no composition
change is required.

Adding a new database backend
-----------------------------

Database backends live under :mod:`db_managers` and implement the
base contract in ``db_managers/base.py``. The currently shipped
backends are ``sqlite`` (``db_managers/dbManager.py``), ``mySql``
and ``embeddedMariaDB``.

Steps to add a backend ``mybackend``:

1. Create ``db_managers/mybackend.py``.
2. Implement the base interface from ``db_managers/base.py``.
   Re-use ``ConnectionPool`` for connection management; do not
   spin a new pool implementation.
3. Register the backend in ``db_managers/__init__.py`` so the
   :class:`getters.Getters` selector can construct it from
   ``settings.json``.
4. Keep all backend code inside :mod:`db_managers`. Never import
   :mod:`backend`, :mod:`application`, :mod:`clients`, or
   :mod:`composition` from a backend file. The backend is consumed
   *through* :class:`components.database_manager.DatabaseManager`
   and the :class:`backend.ports.interfaces.AnimeRepositoryPort`;
   it does not know about them.
5. Add tests under ``tests/unit/db_managers/`` modelled on
   ``test_db_sqlite_comprehensive.py``. Use
   ``db_base_tests.py`` for the shared contract.

The application service stays unchanged because the new backend is
selected at composition time through the existing legacy
``Getters.getDatabase`` indirection. When ``AnimeRepositoryPort``
eventually gets a non-legacy implementation, the same backend will
plug straight into the new adapter.

Adding a new torrent client
---------------------------

Torrent clients live under :mod:`torrent_managers`. Each backend
extends :class:`torrent_managers.base.BaseTorrentManager` and is
selected by name through the settings file.

Steps to add a client ``mytorrent``:

1. Create ``torrent_managers/mytorrent.py``.
2. Subclass :class:`torrent_managers.base.BaseTorrentManager`. Keep
   inheritance to that single base — ADR 0005 forbids piling on
   ``Logger`` / ``Getters`` mixins. Take collaborators through
   ``__init__`` instead.
3. Implement the methods exercised by
   :class:`components.download_manager.DownloadManager`
   (``add_torrent``, ``remove_torrent``, ``get_status`` and the
   peers/lifecycle helpers used by your transport).
4. Register the client name in ``torrent_managers/__init__.py`` so
   :class:`getters.Getters.getTorrentManager` can build it.
5. Add tests under ``tests/unit/torrent_managers/`` using
   ``base_torrent_manager_tests.py`` as the shared contract suite.

The legacy bridge stays untouched: the
:class:`backend.adapters.legacy_runtime.LegacyDownloadAdapter`
wraps :class:`components.download_manager.DownloadManager`, which
selects the configured torrent backend, which is now your new
class. As with database backends, no backend or client edits are
needed.

Adding a new client adapter
---------------------------

A client adapter (Tk, FastAPI, future Qt, CLI, RPC, ...) is a
*peer* to the existing ones. It lives under :mod:`clients` and may
talk to the embedded backend only through
:class:`clients.sdk.ClientSDK`. The architecture test
``tests/architecture/test_layer_boundaries.py`` enforces this:
client modules that import :mod:`db_managers`, :mod:`animeAPI`,
:mod:`torrent_managers`, :mod:`file_managers`, :mod:`media_players`
or :mod:`search_engines` fail the build.

Steps to add a client adapter ``myclient``:

1. Create the package skeleton ``clients/myclient/`` with an
   ``__init__.py``. Mirror the layout of ``clients/tk/`` and
   ``clients/http/``.
2. Instantiate the SDK at the boundary
   (``self._sdk = ClientSDK()``) and route every user action
   through it. Do not import :mod:`backend.application`,
   :mod:`backend.adapters`, or any infrastructure package.
3. Translate :class:`backend.domain.errors.AnimeManagerError`
   subclasses into the conventions of your transport: HTTP status
   codes for ``clients/http``, dialogs / status bar messages for
   ``clients/tk``, exit codes / stderr for a CLI, etc. ADR 0004
   pins the mapping rules.
4. Mirror the test layout of ``tests/unit/clients/`` — use a faked
   :class:`clients.sdk.ClientSDK` and assert on the transport
   behaviour, not on backend internals.
5. Wire the new client into :mod:`bootstrap` (see the next section)
   so that ``python run.py myclient`` launches it.

Because the embedded facade is process-local and cached
(``functools.lru_cache(maxsize=1)`` in
:mod:`clients.sdk`), there is no socket or coordination layer to
configure; the SDK is a function call.

Adding a new bootstrap mode
---------------------------

:mod:`bootstrap` is the single dispatcher (ADR 0006). The mode
table is a dictionary at module scope:

.. code-block:: python

   _MODES: Dict[str, Callable[..., int]] = {
       "gui": _run_gui,
       "api": _run_api,
   }

Steps to add a mode ``myclient``:

1. Implement a handler ``_run_myclient(**kwargs) -> int`` inside
   :mod:`bootstrap`. The handler imports the matching client
   adapter (e.g. ``from clients.myclient import run``) and
   delegates to it. Keep the handler tiny: argument validation
   plus one call into the client adapter.
2. Register the handler in ``_MODES``::

      _MODES = {
          "gui": _run_gui,
          "api": _run_api,
          "myclient": _run_myclient,
      }

3. Update ``run.py``'s ``argparse`` help text if the new mode takes
   additional CLI options (host, port, file path, ...). The
   dispatcher itself does not need new arguments because
   :func:`bootstrap.main` already accepts ``**kwargs`` and forwards
   them to the registered handler.
4. Add coverage that asserts ``bootstrap.list_modes()`` advertises
   the new mode and that ``bootstrap.main(mode="myclient")`` calls
   into your handler. Use a monkey-patched handler so the test is
   side-effect free.
5. Document the new mode in ``docs/developer/runtime-flows.rst``
   with a code-block flow diagram, the way the GUI and API flows
   are documented.

That is the complete checklist: a new mode is one handler, one
dictionary entry, one CLI doc update, and one test. The composition
root, the application service, and the existing client adapters do
not change.

Layer rules every extension must obey
-------------------------------------

Each of the recipes above relies on the same dependency direction
rules. Concretely:

* Infrastructure plug-ins (:mod:`animeAPI`, :mod:`db_managers`,
  :mod:`torrent_managers`, :mod:`file_managers`,
  :mod:`media_players`, :mod:`search_engines`) **must not** import
  from :mod:`backend`, :mod:`application`, :mod:`clients` or
  :mod:`composition`. They are leaves; they are consumed *through*
  the legacy adapters in :mod:`backend.adapters` and the ports in
  :mod:`backend.ports`.
* Client adapters under :mod:`clients` **must not** import from
  the infrastructure plug-ins listed above. The architecture test
  ``test_clients_layer_has_no_low_level_integration_imports``
  enforces this.
* Any new runtime class must keep to single inheritance per ADR
  0005. Cross-cutting capabilities go through constructor
  injection (a ``ConfigProvider``, a ``LoggerService``, a port
  Protocol), not through mixins.
* Settings, paths, and credentials flow through
  :class:`shared.config.ConfigProvider` and ``settings.json``, not
  through ad-hoc globals or environment-variable reads scattered
  across the codebase.

If you follow those rules the architecture suite (``pytest -m
architecture``) stays green and your extension lands without a
backend rewrite.
