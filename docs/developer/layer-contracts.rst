Layer Contracts
===============

AnimeManager is laid out as a strict, one-directional stack of layers.
Every layer knows about the layers beneath it and nothing above. The
rules captured in this document are the operational form of three
Architecture Decision Records (ADRs 0003, 0005, 0006) and are
enforced mechanically by the tests under ``tests/architecture/``.

This page is the cheat sheet you should consult whenever you add a
new module, move a file, or write an ``import`` statement.

.. seealso::

   * `ADR 0003 — Dependency Direction Rules <../../docs/adr/0003-dependency-rules.md>`_
   * `ADR 0005 — Composition Over Inheritance <../../docs/adr/0005-composition-over-inheritance.md>`_
   * `ADR 0006 — Package Layout and Single Entrypoint <../../docs/adr/0006-package-layout-and-single-entrypoint.md>`_

The layers
----------

The runtime is split into the following layers, listed from the
purest at the top to the most concrete at the bottom:

``domain``
    Pure entities, value objects, policies, and the unified
    ``AnimeManagerError`` hierarchy. No I/O, no framework imports,
    no awareness of anything outside the Python standard library.

``ports``
    ``typing.Protocol`` interfaces that describe what infrastructure
    the application needs. Ports name capabilities; they never own
    them.

``application``
    Use-cases, DTOs, commands, queries, and the
    ``AnimeApplicationService`` orchestrator. It depends on the
    domain and on port protocols only.

``adapters``
    Concrete bindings of port protocols to real infrastructure
    (databases, HTTP APIs, torrent clients, the legacy runtime).
    Adapters are the *only* place where vendor-specific code is
    allowed to live alongside backend code.

``clients``
    Transport / presentation adapters (Tk, FastAPI, future Qt or
    CLI). Clients talk to the backend through
    :class:`clients.sdk.ClientSDK` and never reach for low-level
    integration modules.

``shared``
    Cross-cutting technical helpers (configuration provider,
    logging service, security helpers). Anyone may import it; it
    must not import from layers above it.

``composition``
    The single wiring point. ``composition/root.py`` and
    ``backend/composition.py`` build the dependency graph and
    return a ready-to-use facade. Nothing else is allowed to know
    how the graph is constructed.

Allowed and forbidden imports
-----------------------------

The matrix below reads *from row to column*. A check (``yes``) means
the row layer may import from the column layer; a dash (``no``)
means the import is forbidden by ADR 0003 and will fail the
architecture suite.

.. table:: Allowed import directions

   ============  =======  =====  ===========  ========  =======  ======  ===========
   from \\ to    domain   ports  application  adapters  clients  shared  composition
   ============  =======  =====  ===========  ========  =======  ======  ===========
   domain        yes      no     no           no        no       no      no
   ports         yes      yes    no           no        no       no      no
   application   yes      yes    yes          no        no       yes     no
   adapters      yes      yes    yes          yes       no       yes     no
   clients       yes      no     yes          no        yes      yes     yes
   shared        yes      no     no           no        no       yes     no
   composition   yes      yes    yes          yes       no       yes     yes
   ============  =======  =====  ===========  ========  =======  ======  ===========

The same rules expressed as forbidden edges:

.. code-block:: text

   domain        ->  must NOT import: adapters, clients, composition,
                                       application, shared, ports,
                                       db_managers, animeAPI,
                                       torrent_managers, file_managers,
                                       media_players, search_engines,
                                       components, core,
                                       fastapi, tkinter, requests, ...
   ports         ->  must NOT import: adapters, application, clients,
                                       composition, shared, db_managers,
                                       animeAPI, torrent_managers,
                                       file_managers, media_players,
                                       search_engines, components
   application   ->  must NOT import: adapters, clients, composition,
                                       db_managers, animeAPI,
                                       torrent_managers, file_managers,
                                       media_players
   clients       ->  must NOT import: db_managers, animeAPI,
                                       torrent_managers, file_managers,
                                       media_players, search_engines

The forbidden-for-domain set is deliberately the strictest: the
domain layer must remain side-effect free so it can be unit-tested
without I/O.

Why this shape
--------------

Each forbidden edge encodes a concrete past failure:

* Clients importing :mod:`db_managers` directly is exactly how the
  legacy ``Manager`` god-class came to exist. Forbidding it forces
  new behavior through :class:`clients.sdk.ClientSDK` and the
  :class:`backend.application.service.AnimeApplicationService`.
* :mod:`backend.ports` modules importing concrete adapters would
  create a dependency cycle and re-couple application code to
  vendors. Ports must stay protocol-only.
* Domain imports of :mod:`requests`, :mod:`sqlite3`, :mod:`tkinter`
  or any provider package would defeat the entire point of having a
  pure domain layer. They are blocklisted explicitly.

Inheritance contract (ADR 0005)
-------------------------------

The dependency matrix above governs imports; ADR 0005 governs class
shape. Inside any runtime layer a class **must** inherit from at
most one non-allowlisted base. Cross-cutting capabilities are
supplied through constructor arguments typed by a narrow
``Protocol`` or interface.

The allowlist for pre-existing hotspots is small and frozen:

.. code-block:: text

   animeAPI.__init__:AnimeAPI
   animeAPI.APIUtils:APIUtils
   backend.adapters.legacy_runtime:_LegacyBackbone
   backend.adapters.legacy_runtime:InheritingLegacyRuntime

Adding to the allowlist requires an ADR amendment. The intended
direction of travel is to remove entries as the corresponding
classes are decomposed; see ``docs/developer/decomposition-guide.rst``
for the migration recipe.

Where the rules are enforced
----------------------------

Both contracts are enforced by automated tests. They run by default
under the ``architecture`` pytest marker, so the build fails
whenever a new import or a new class violates them.

* ``tests/architecture/test_layer_boundaries.py`` walks every
  ``.py`` file under ``domain``, ``application``, ``ports`` and
  ``clients`` and asserts that no import touches a forbidden
  module. The forbidden sets in that file are the canonical source
  of truth; the matrix in this document mirrors them.
* ``tests/architecture/test_no_new_multi_inheritance.py`` parses
  every runtime module and fails the build if any class declares
  more than one non-allowlisted base. ``Protocol`` / ``ABC`` /
  exception bases are explicitly excluded so abstract contracts
  remain easy to express.

To run the architecture slice locally:

.. code-block:: bash

   pytest -m architecture

When you need to add a deliberate exception (a new ADR-blessed
hotspot, a new framework allowed in a layer) update the
corresponding constant in the test file and the matching ADR in
``docs/adr/`` in the same pull request. The architecture tests are
the contract; this page is its narrative.
