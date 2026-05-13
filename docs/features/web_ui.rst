Web UI
======

The HTTP client adapter exposes a complete server-rendered web UI in
addition to its JSON API. The two surfaces share the same FastAPI
application (``clients.http.app:app``) and the same
:class:`clients.sdk.ClientSDK` accessor, so every action a user can
perform in the browser goes through the embedded backend exactly like
the Tk client.

.. seealso::

   * `ADR 0001 - Embedded Runtime Model <../../docs/adr/0001-embedded-runtime-model.md>`_
   * `clients/README.md <../../clients/README.md>`_

Surfaces
--------

The single FastAPI app serves three peers:

* ``/`` - service probe. Returns JSON for HTTP tooling; ``Accept:
  text/html`` requests are bounced to ``/ui/library`` so a browser
  landing on the bare host gets the UI.
* ``/anime/*``, ``/animelist``, ``/search``, ... - the historical JSON
  API consumed by mobile, integrations, and tests.
* ``/ui/*`` - the server-rendered web UI. Static assets are mounted at
  ``/ui/static``.

Running it
----------

::

   python run.py api --host 0.0.0.0 --port 8081

Then open ``http://localhost:8081/`` in a browser. From the desktop
client this is intentionally the same process: both UIs share the
embedded facade.

Layout
------

The UI follows a sidebar + topbar + content shell pattern:

* **Rail (left)** - primary navigation (Browser, Watching, Watchlist,
  Seen, Liked, Torrent search, Downloads, Settings) and a link to the
  auto-generated API docs at ``/docs``.
* **Topbar** - persistent global search (debounced, posts to
  ``/ui/library``), in-flight indicator for HTMX requests, and
  context-appropriate action buttons.
* **Content** - per-route grid or detail view. Every page has explicit
  empty / loading / error states.

Routes
------

.. list-table::
   :header-rows: 1
   :widths: 24 14 62

   * - Route
     - Method
     - SDK calls
   * - ``/ui/library``
     - GET
     - ``get_anime_list`` (no query) or ``search_anime`` (when ``q`` set)
   * - ``/ui/anime/{id}``
     - GET
     - ``get_anime`` + ``get_user_state`` + ``get_search_terms`` +
       ``get_relations``
   * - ``/ui/anime/{id}/like``
     - POST
     - ``set_like``
   * - ``/ui/anime/{id}/tag``
     - POST
     - ``set_tag``
   * - ``/ui/anime/{id}/seen``
     - POST
     - ``mark_seen``
   * - ``/ui/anime/{id}/terms``
     - POST / DELETE
     - ``add_search_term`` / ``remove_search_term``
   * - ``/ui/anime/{id}/download``
     - POST
     - ``start_download``
   * - ``/ui/anime/{id}/cancel``
     - POST
     - ``cancel_download``
   * - ``/ui/downloads``
     - GET
     - ``get_active_downloads``
   * - ``/ui/downloads/panel``
     - GET
     - ``get_active_downloads`` (HTMX partial, polled every 4s)
   * - ``/ui/torrents``
     - GET
     - ``search_torrents`` (when ``term`` set)
   * - ``/ui/settings``
     - GET / POST
     - ``get_settings`` / ``update_settings``

Progressive enhancement
-----------------------

Every page is fully functional without JavaScript:

* Forms submit conventionally (303 redirect, server-rendered response).
* HTMX (loaded from a CDN) layers partial swaps onto interactions that
  benefit from them: search-term add/remove returns an updated chip
  list, the downloads page polls ``/ui/downloads/panel`` every four
  seconds, etc.
* A small ``clients/http/static/js/app.js`` adds debouncing for the
  search bar, ``data-autosubmit`` for the tag ``<select>`` and a
  ``data-confirm`` guard for destructive actions.

If JS is disabled the user simply submits the matching form by hand;
no state is hidden behind a script.

Design system
-------------

The CSS lives in a single file at
``clients/http/static/css/app.css`` and is structured around explicit
design tokens (see the web-design skill ``design-tokens.md`` for the
methodology):

* **Palette** anchored on the existing settings ``UI.colors`` block:
  cyan ``#56D8EF`` accent, green / orange / red as semantic
  success / warning / danger.
* **Typography** pairs Inter for body text with Instrument Serif for
  display titles (page headers, detail titles).
* **Spacing scale** on a 4-px base (4, 8, 12, 16, 20, 24, 32, 40, 48,
  64).
* **Radii** intentionally vary by component density (cards 10 px,
  buttons 6 px, badges full-pill).
* **Dark mode** is hand-designed - not an inverted light theme.

Architecture boundary
---------------------

The web UI sits inside ``clients/http/`` and may only depend on
:class:`clients.sdk.ClientSDK` plus the domain error classes. It
never imports ``adapters/*`` or any legacy integration module - this
is enforced by ``tests/architecture/test_layer_boundaries.py`` and
verified by the existing CI suite.

Testing
-------

Run the focused suite::

   pytest tests/unit/clients/test_http_web_ui.py --no-cov

The tests reuse the JSON-API ``FakeSDK`` pattern and exercise every
route (library grid, filter chip, search, detail, like, tag, term
add/remove, downloads polling partial, torrent search, settings save,
static assets) with ``fastapi.testclient.TestClient``.
