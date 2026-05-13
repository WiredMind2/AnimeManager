Configuration
=============

AnimeManager is configured through a single JSON file -- :file:`settings.json`
-- with paths and constants derived from a small Python module. Two
collaborators read that file at runtime: the legacy
:class:`constants.Constants` class (loads everything into a Python
object on construction) and the new :class:`shared.config.ConfigProvider`
(a narrow composable accessor that wraps :class:`Constants` so new
code does not inherit from it). This page is the reference for the
shape of :file:`settings.json`, the responsibilities of the legacy
helpers, and the composition rules introduced by ADR 0005 and 0006.

On-disk layout
--------------

A first launch copies the project-tree :file:`settings.json` template
into the user's AppData directory (``%APPDATA%/Anime Manager`` on
Windows, ``/srv/Anime Manager`` on Linux). The template is the only
source of truth for the *default* values; the in-AppData copy is the
mutable user configuration.

The file is a single JSON object grouped by feature area:

.. code-block:: json

   {
     "database": { "type": "sqlite", "path": "./data/anime.db" },
     "ui": { "theme": "default", "language": "en", "window_size": [1200, 800] },
     "media": { "players_order": ["mpv", "vlc", "ffplay"], "default_player": "mpv" },
     "downloads": { "max_concurrent": 3, "default_folder": "./downloads" },
     "api": { "timeout": 30, "rate_limit": 60 },
     "feature_flags": { ... },
     "api_credentials": { "myanimelist": { "client_id": "", "client_secret": "" } },
     "file_managers": { "last_fm_used": "Local", "Local": {...}, "FTP": {...} },
     "torrent_managers": { "last_tm_used": "qBittorrent", "qBittorrent": {...}, "Transmission": {...} },
     "database_managers": { "last_db_used": "EmbeddedMariaDB", "EmbeddedMariaDB": {...}, "MySQL": {...}, "SQLite": {...} },
     "UI": { "colors": {...}, "dateStates": {...}, "fileMarkers": {...}, "tagcolors": {...}, "torrentsStateColors": {...} },
     "anime": { "animePerRow": 4, "animePerPage": 50, "apiHost": "kitsu.io", "hideRated": true, "maxTimeout": 30, "topPublishers": [...] },
     "logs": { "logBracketWidth": 13, "logs": [...], "maxLogsSize": 50000 },
     "paths": { "cache": "", "iconPath": "", "logsPath": "" },
     "phoneSyncServer": { "enableServer": false, "hostName": "0.0.0.0", "serverPort": 8081 },
     "player": { "playerKeyBindings": {...}, "playerOrder": ["mpv_player", "vlc_player", "ff_player"] },
     "windows": { ... }
   }

The blocks fall into four logical groups.

Feature toggles and budgets
~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``database`` -- legacy summary of the active backend; in practice
  the authoritative selection is the ``database_managers.last_db_used``
  pointer inside the dedicated managers block below.
* ``api`` -- network defaults shared across provider wrappers
  (``timeout``, ``rate_limit``).
* ``downloads`` -- ``max_concurrent`` is consumed by
  :class:`components.download_manager.DownloadManager` (via its
  constructor parameter) and ``default_folder`` is the fallback for
  the file manager.
* ``feature_flags`` -- canonical rollout switches:

  * ``new_ingestion_pipeline`` (toggles the path in
    :class:`components.api_coordinator.APICoordinator`; see
    :doc:`anime_data`),
  * ``db_gateway_writes_only`` (forces all writes through
    :class:`DatabaseManager`),
  * ``strict_download_url_validation`` (consumed by
    :func:`core.security.validate_url`),
  * ``secure_db_bootstrap`` (gates secret loading for the embedded
    MariaDB backend).
* ``api_credentials`` -- the only secret-bearing block. Currently
  hosts the OAuth2 credentials for :mod:`animeAPI.MyAnimeListNet`.
  Empty credentials make the wrapper raise ``NotImplementedError``
  during construction so it is silently skipped by
  :meth:`animeAPI.AnimeAPI.load_apis`.

Plug-in selection
~~~~~~~~~~~~~~~~~

The three "manager" blocks use a uniform pattern: a ``last_*_used``
pointer that names the active backend, plus one sub-block per backend
with the constructor arguments. The active backend is resolved by
:class:`getters.Getters` (``getDatabase``, ``getFileManager``,
``getTorrentManager``) and looked up in the matching registry
dictionary (:data:`db_managers.databases`,
:data:`file_managers.managers`, :data:`torrent_managers.managers`).

* ``database_managers`` -- ``EmbeddedMariaDB`` is the default. The
  sub-blocks carry the backend's own connection details (``port``,
  ``user``, ``password``, ``database`` for MariaDB and MySQL;
  ``dbPath`` for SQLite). See :doc:`persistence` for the per-backend
  reference.
* ``file_managers`` -- ``Local`` is the default; ``FTP`` is opt-in.
  Each block stores its own ``dataPath`` and, for FTP, the
  authentication tuple. The file manager calls
  :class:`shared.config.ConfigProvider.update_settings` (via
  :class:`backend.adapters.legacy_runtime.LegacyRuntime.setSettings`)
  to persist changes immediately whenever the user updates the path
  through the Tk dialog.
* ``torrent_managers`` -- ``qBittorrent`` is the default; the other
  registered backends are ``Transmission``, ``Deluge`` and
  ``libtorrent`` (only loaded when the native binary is available).
  The sub-blocks carry the backend's Web UI / RPC endpoint and
  credentials.

UI and presentation
~~~~~~~~~~~~~~~~~~~

* ``UI`` -- colour palette, per-status colour mapping
  (``dateStates``, ``tagcolors``, ``torrentsStateColors``), and
  regular expressions that classify torrent file names by colour
  (``fileMarkers``).
* ``ui`` -- general window size and language preferences.
* ``windows`` -- minimum sizes for each Tk window class.
* ``player`` -- keybinding map for the future embedded player and
  the ``_player``-suffixed ordering inherited from the deleted
  in-process players. See :doc:`media_playback` for the migration
  plan.
* ``media`` -- the post-migration ordering used to shell-launch
  external players (default ``["mpv", "vlc", "ffplay"]``).

Domain and runtime
~~~~~~~~~~~~~~~~~~

* ``anime`` -- domain-level defaults: page size, default API host,
  whether to hide rated content, schedule refresh cadence, and a
  curated list of trusted release groups (``topPublishers``) that the
  search and download pipelines use to nudge ranking.
* ``logs`` -- :class:`logger.Logger` filtering. ``logs`` is the
  active subset of :attr:`constants.Constants.allLogs`,
  ``logBracketWidth`` controls the column width of the log prefix,
  and ``maxLogsSize`` caps the in-memory log buffer.
* ``paths`` -- override directories for ``cache``, ``iconPath`` and
  ``logsPath``. Empty strings fall back to the
  AppData-derived defaults computed by :class:`constants.Constants`.
* ``phoneSyncServer`` -- toggles the optional HTTP server that
  exposes the catalogue to a companion device.

:class:`constants.Constants`
----------------------------

:class:`constants.Constants` is the legacy bootstrap. Its
``__init__`` does three things, in order:

1. Resolves the platform-specific AppData directory through the
   class-method :meth:`Constants.getAppdata` and records the four
   derived paths -- ``dbPath``, ``settingsPath``, ``cache`` and
   ``logsPath`` -- as instance attributes.
2. Populates a long list of *pure-Python* constants -- the
   ``websitesViewUrls`` template map, the ``seasons`` table, the
   ``filterOptions`` dictionary, the canonical ``status`` translation
   map, and the ``tag_options`` map. These are the values the UI and
   the application service treat as enumerations.
3. Calls :meth:`Constants.checkSettings`. The method copies the
   project-tree :file:`settings.json` into AppData if no user copy
   exists, loads it into ``self.settings``, walks every entry that
   names one of the ``pathSettings`` (``iconPath``, ``cache``,
   ``dbPath``, ``logsPath``) to ensure the directory exists, and
   writes the result back when anything had to be repaired.

Every attribute of ``Constants`` that callers historically depended
on -- ``settingsPath``, ``settings``, ``dbPath``, ``cache``,
``logsPath``, ``iconPath``, ``hideRated``, ``server`` -- continues
to exist for backward compatibility. New code, however, MUST go
through :class:`shared.config.ConfigProvider` (see below).

:class:`getters.Getters`
------------------------

:class:`getters.Getters` is the legacy plug-in loader mixin. It is
deliberately untyped (the class body declares attributes as
:class:`typing.Any`) because it predates the port-based architecture
and is shared between the Tk UI, the HTTP server and the embedded
runtime. Its surviving responsibilities are:

* :meth:`Getters.getDatabase` -- look up the active database backend
  from ``settings["database_managers"]["last_db_used"]`` and
  construct it with the matching settings block. Instances are
  cached in a private module-level dictionary so every consumer
  shares one underlying connection / lock graph.
* :meth:`Getters.getFileManager` -- the same pattern for
  ``file_managers``. Saves the chosen manager's effective settings
  back through :meth:`setSettings` so user-entered values land on
  disk immediately.
* :meth:`Getters.getTorrentManager` -- the same pattern for
  ``torrent_managers``.

The mixin is no longer attached to a god class; it is composed into
:class:`backend.adapters.legacy_runtime._LegacyBackbone`, which is
the private holder owned by
:class:`backend.adapters.legacy_runtime.LegacyRuntime`. Architecture
tests prevent any new class from inheriting from ``Getters``.

:class:`shared.config.ConfigProvider`
-------------------------------------

:class:`shared.config.ConfigProvider` is the post-ADR-0005 collaborator
intended to replace ``Constants`` for new code. It is deliberately
narrow:

.. code-block:: python

   class ConfigProvider:
       @classmethod
       def from_defaults(cls) -> "ConfigProvider": ...

       @property
       def appdata_path(self) -> str: ...
       @property
       def db_path(self) -> str: ...
       @property
       def settings_path(self) -> str: ...
       @property
       def logs_path(self) -> str: ...
       @property
       def cache_path(self) -> str: ...
       @property
       def icon_path(self) -> str: ...
       @property
       def settings(self) -> Mapping[str, Any]: ...

       def update_settings(self, updates: Mapping[str, Any]) -> MutableMapping[str, Any]: ...
       def ensure_appdata(self) -> str: ...

The provider wraps an already-constructed :class:`Constants` (or any
duck-typed object exposing the same attributes) and exposes only the
slice that runtime code actually needs: the on-disk paths, the loaded
settings dictionary, and a single mutator that merges updates back
into the file. It deliberately does **not** subclass ``Constants`` so
that new collaborators inherit nothing implicitly.

:meth:`ConfigProvider.update_settings` is the canonical replacement
for the legacy ``Manager.setSettings``. It opens the on-disk
:file:`settings.json`, merges the supplied updates section-by-section,
writes the result back atomically, and keeps the in-memory
``Constants.settings`` mapping in sync when one is available. This is
the method :class:`backend.adapters.legacy_runtime.LegacyRuntime`
forwards to from its own :meth:`LegacyRuntime.setSettings` shim, which
preserves the legacy API while routing the actual write through the
narrow collaborator.

A module-level :func:`shared.config.get_default_config_provider`
returns a process-wide singleton so background components (e.g. the
optional HTTP server) can share the same view of the settings file
without each one constructing its own :class:`Constants`.

Composition rules (ADR 0005 / 0006)
-----------------------------------

The composition rules that govern configuration access are:

* **Inherit nothing implicit.** New runtime classes MUST NOT inherit
  from :class:`Constants` or :class:`Getters`. The architecture test
  ``tests/architecture/test_no_new_multi_inheritance.py`` enforces
  the rule and only allowlists existing offenders
  (:class:`AnimeAPI`, :class:`APIUtils`, :class:`LegacyRuntime`).
* **Pass collaborators explicitly.** Modules that need configuration
  take a :class:`ConfigProvider` (or a narrower
  :class:`typing.Protocol` that exposes the subset they need) as a
  constructor parameter. The
  :class:`backend.adapters.legacy_runtime.LegacyRuntime` constructor
  is the reference example: it accepts ``config: ConfigProvider`` and
  ``logger: LoggerService`` and falls back to the process-wide
  defaults only when none is supplied.
* **One settings file, one entrypoint.** ADR 0006 keeps
  :file:`run.py` as the only Python startup script and forbids new
  ``.py`` files at the repository root. The settings file is
  therefore read in exactly one place during bootstrap and the
  composition root threads the :class:`ConfigProvider` down to
  whoever needs it.

The end result is that the *what* of configuration (the JSON
schema) is owned by :file:`settings.json`, the *how* of loading and
validating it is owned by :class:`Constants`, and the *narrow
interface used by new code* is owned by
:class:`shared.config.ConfigProvider`. The three layers can evolve
independently because every consumer in the application now talks to
the provider instead of reaching across the codebase for an
inherited attribute.
