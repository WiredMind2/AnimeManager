Tk Desktop UI
=============

The Tk client was rebuilt into a modular structure while preserving the
historical workflow surface from the deleted monolithic UI **and** the
original dark, borderless look-and-feel.

Module layout
-------------

The client is now split by responsibility:

* ``clients/tk/app.py``: shell/bootstrap (hidden ``Tk()`` root +
  borderless dark ``Toplevel`` + presenter wiring).
* ``clients/tk/theme.py``: dark palette (sourced from ``settings.json``
  ``UI`` block), fonts, ``ttk`` style registration (``AnimeManager.*``
  styles), menu/filter option metadata, asset path helpers.
* ``clients/tk/presenters/``: SDK orchestration and threaded execution.
* ``clients/tk/views/``: windows/dialogs (browser, details, torrent,
  settings, search terms, season selector, relations, logs). All
  dialogs call :func:`clients.tk.theme.apply_dark_theme` at startup.
* ``clients/tk/widgets/``: reusable controls — anime poster grid,
  scrollable canvas, placeholder search entry, icon dropdown menu,
  animated loading canvas, icon loader, status bar, and the legacy
  ``AnimeTable`` retained for compatibility.

Visual parity
-------------

The browser window recreates the legacy header bar exactly:

* Menu icon button (``icons/menu.png``) on the left, opening a colored
  popup menu (entries match legacy: Liked characters, Disk manager,
  Log panel, Clear logs, Clear cache, Settings, Reload, Exit).
* Search entry with the original "Search..." placeholder, expanding to
  fill the bar.
* Animated GIF loading canvas (``icons/loading.gif``) that spins while
  asynchronous SDK calls are in flight.
* Filter icon button (``icons/filter.png``) with the full legacy
  filter list (Liked / Seen / Watching / Watchlist / Finished / Airing
  / Upcoming / Rated / By season / Random / No tags / No filter).
* Close button (``icons/close.png``).

Below the header is a four-column scrollable poster grid (225×310
posters with colored title labels). Posters load asynchronously via
the presenter's runner and cache to the OS temp dir. Tag colors are
read from ``settings.json`` (``UI.tagcolors``), and liked entries
receive the legacy ❤ suffix. The bottom of the window shows the
Previous / Reload / Next pager, current filter label, and the status
bar.

When ``ANIMEMANAGER_BORDERLESS=1`` (default on Windows) the main
``Toplevel`` is borderless (``overrideredirect``); the user can drag
the window by grabbing the header bar.

Boundary rule
-------------

Tk code talks to ``clients.sdk.ClientSDK`` only. No Tk view imports
``adapters.*`` internals or historical ``windows/*`` modules.

Legacy parity checklist
-----------------------

The following checklist maps historical modules (from git history:
``animeManager.py``, ``anime_list_frame.py``, ``windows/*``,
``dialog_components.py``) to the rebuilt Tk client.

.. list-table::
   :header-rows: 1
   :widths: 24 14 32 30

   * - Legacy feature/module
     - Status
     - New implementation
     - Notes / gap rationale
   * - Main browser list/search/filter/pagination
     - PASS
     - ``views/anime_browser.py`` + ``presenters/anime_browser.py``
     - Includes search bar, list filter, page navigation, hide-rated toggle.
   * - Anime details window (tag/like/seen + synopsis)
     - PASS
     - ``views/anime_details.py``
     - Includes tag/like/seen semantics through SDK calls.
   * - Torrent search and pick/start/cancel/progress
     - PASS
     - ``views/torrent_download.py``
     - Uses new SDK torrent-search orchestration and download controls.
   * - Search terms manager
     - PASS
     - ``views/seasons_search_terms.py`` (``SearchTermsDialog``)
     - Add/remove/list search terms via SDK contract.
   * - Season selector flow
     - PASS
     - ``views/seasons_search_terms.py`` (``SeasonSelectorDialog``)
     - Triggers season query search through main browser flow.
   * - Settings editor/persistence
     - PASS
     - ``views/settings.py``
     - JSON editor backed by ``get_settings`` / ``update_settings`` SDK API.
   * - Relations window
     - PASS
     - ``views/characters_disks.py`` (``RelationsDialog``)
     - Pulls relation rows through SDK.
   * - Logs window
     - PASS
     - ``views/logs.py``
     - In-app log panel parity with clear append surface.
   * - Characters/disks secondary windows
     - PARTIAL
     - ``views/characters_disks.py`` (``CharactersDisksDialog``)
     - Full legacy character/disk data flows depended on removed direct internals.
       Replaced with explicit boundary-safe window and relation-focused flow.

Verification evidence
---------------------

See CI/local validation commands:

* ``python -m pytest tests/gui --no-cov`` (theme, widgets, view smoke)
* ``python -m pytest -m "not slow"``
* ``python -m pytest -m architecture``
* ``python -m sphinx -b html docs docs/_build/html``
* ``python run.py --help``
