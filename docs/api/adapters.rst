Adapters Layer
==============

The :mod:`adapters` package hosts concrete IO, framework and vendor
integrations. It is the only layer allowed to depend on the legacy
infrastructure modules (:mod:`animeAPI`, :mod:`db_managers`,
:mod:`file_managers`, :mod:`media_players`, :mod:`torrent_managers`,
:mod:`search_engines`). The composition root binds each adapter
into the matching port.

Phase 4 of the refactor (see :doc:`/migration/refactor_phases`)
relocates these integrations physically under :mod:`adapters`. The
relocation has been deferred-by-design: each subpackage currently
re-exports from the legacy infrastructure module so the new
``adapters.*`` import paths already work without rewriting the
existing call graph.

Package overview
----------------

.. automodule:: adapters
   :members:
   :undoc-members:
   :show-inheritance:

Metadata API adapters
---------------------

Re-exports the :mod:`animeAPI` surface. The composition root binds
:class:`backend.ports.interfaces.MetadataProviderPort` to the
:class:`adapters.legacy.LegacyMetadataProviderAdapter` adapter,
which in turn drives the per-provider clients exposed by
:mod:`animeAPI`.

.. automodule:: adapters.api
   :members:
   :undoc-members:
   :show-inheritance:

Persistence adapters
--------------------

Re-exports the :mod:`db_managers` package (SQLite, MySQL, embedded
MariaDB). Used by :class:`adapters.legacy.LegacyAnimeRepositoryAdapter`
to implement :class:`backend.ports.interfaces.AnimeRepositoryPort`.

.. automodule:: adapters.persistence
   :members:
   :undoc-members:
   :show-inheritance:

Search adapters
---------------

Forwards the orchestration entrypoints from :mod:`search_engines`
(facade and planner). The vendored ``nova3`` plug-in subtree stays
untouched.

.. automodule:: adapters.search
   :members:
   :undoc-members:
   :show-inheritance:

Media adapters
--------------

Re-exports :mod:`media_players` when present. Media playback is
optional in headless builds; this subpackage tolerates the missing
dependency gracefully.

.. automodule:: adapters.media
   :members:
   :undoc-members:
   :show-inheritance:

Torrent adapters
----------------

Re-exports :mod:`torrent_managers` (qBittorrent, Transmission,
Deluge, libtorrent). Used by
:class:`adapters.legacy.LegacyDownloadAdapter` to implement
:class:`backend.ports.interfaces.DownloadPort`.

.. automodule:: adapters.torrent
   :members:
   :undoc-members:
   :show-inheritance:

File-system adapters
--------------------

Re-exports :mod:`file_managers` (local-disk and FTP filesystem
abstractions).

.. automodule:: adapters.file
   :members:
   :undoc-members:
   :show-inheritance:

Legacy bridge adapters
----------------------

The :mod:`adapters.legacy` subpackage hosts the bridge classes that
keep the embedded backend working while Phase 4 relocations are still
in progress. Each class implements one of the ports declared in
:mod:`backend.ports.interfaces` by delegating to the legacy
infrastructure modules.

* :class:`adapters.legacy.LegacyRuntime` — composed runtime context
  (see :doc:`/migration/monolith_decomposition_status`).
* :class:`adapters.legacy.LegacyAnimeRepositoryAdapter` —
  implements :class:`backend.ports.interfaces.AnimeRepositoryPort`
  via :class:`components.database_manager.DatabaseManager`.
* :class:`adapters.legacy.LegacyMetadataProviderAdapter` —
  implements :class:`backend.ports.interfaces.MetadataProviderPort`
  via :class:`components.api_coordinator.APICoordinator`.
* :class:`adapters.legacy.LegacyDownloadAdapter` — implements
  :class:`backend.ports.interfaces.DownloadPort` via
  :class:`components.download_manager.DownloadManager` plus the
  legacy file and torrent managers.
* :class:`adapters.legacy.LegacyUserActionsAdapter` — implements
  :class:`backend.ports.interfaces.UserActionsPort` by writing
  user-tag rows directly through the configured database.

.. automodule:: adapters.legacy
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:
