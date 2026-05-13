Inheritance to Composition Playbook
===================================

ADR 0005 forbids new runtime classes from inheriting more than one
non-allowlisted base. It does not pretend the existing god classes
are gone; it freezes them on a short allowlist and obliges us to
retire them one at a time. This document is the practical recipe
for doing so without breaking callers.

.. seealso::

   * `ADR 0003 — Dependency Direction Rules <../../docs/adr/0003-dependency-rules.md>`_
   * `ADR 0005 — Composition Over Inheritance <../../docs/adr/0005-composition-over-inheritance.md>`_

The rule, restated
------------------

A runtime class may inherit from at most one non-allowlisted base.
Cross-cutting capabilities (configuration, logging, telemetry,
filesystem access, HTTP, database handles) must be **injected** via
explicit constructor parameters that are typed by a narrow
``Protocol`` or interface living in :mod:`ports` or :mod:`shared`.

In practice this means:

* No more ``class Foo(Constants, Getters, Logger)``.
* No new "mixin" classes whose only job is to grant ambient access
  to a database handle, logger, or settings dictionary.
* ``abc.ABC`` and ``typing.Protocol`` do not count as inheritance;
  they declare contracts rather than behavior.

The architecture test
``tests/architecture/test_no_new_multi_inheritance.py`` enforces
this and ships with a frozen allowlist for the few classes that
have not been migrated yet.

The 5-step migration recipe
---------------------------

Decomposing a multi-inheritance god class is mechanical once you
follow the five steps below in order. Skipping a step is how you
end up with another god class.

1. **Responsibility Inventory**
   Read the class top to bottom and write down every responsibility
   it holds. Group the responsibilities by *kind*: configuration,
   logging, database I/O, HTTP I/O, settings persistence, business
   policy. Do not start refactoring until the inventory is complete.

2. **Stable Contracts**
   For each group of responsibilities, decide where it belongs in
   the target architecture: a ``Protocol`` in :mod:`ports`, a small
   service class in :mod:`shared`, or a use-case in
   :mod:`application`. Write the interface first, with full type
   hints and docstrings. Treat the interface as the migration's
   load-bearing artifact.

3. **Composed Services**
   Implement the new contracts as small, single-responsibility
   classes that take their collaborators through ``__init__``. Each
   service must be constructible from a fake or in-memory
   collaborator so it is trivially unit-testable. Add the new
   binding to ``backend/composition.py`` (or ``composition/root.py``)
   so the graph keeps building.

4. **Strangler Call Sites**
   Migrate call sites one at a time to depend on the new contracts
   instead of the old class. Lean on the
   ``tests/unit/monolith_decomp/`` characterization tests at every
   step: they pin the externally visible behavior of the legacy
   class so a regression in delegation fails the build immediately.
   Keep the old class working through delegation while call sites
   migrate.

5. **Remove Legacy Inheritance**
   Once no call site depends on the legacy class for behavior it
   does not strictly need, delete the multi-inheritance class (or
   reduce it to a no-op shim with a ``DeprecationWarning``). Remove
   the corresponding entry from ``LEGACY_CLASS_ALLOWLIST`` in
   ``tests/architecture/test_no_new_multi_inheritance.py``; the
   sibling ``test_allowlisted_legacy_hotspots_still_exist`` will
   nag you if you forget.

The order matters. Doing the contract design (step 2) before the
implementation (step 3) prevents the new code from inheriting the
old class's implicit assumptions. Doing the call-site migration
(step 4) before deletion (step 5) keeps every commit green.

Worked example: ``LegacyRuntime``
---------------------------------

The most recent application of the recipe is in
:mod:`backend.adapters.legacy_runtime`. Before Phase 2 the class
looked like this:

.. code-block:: python

   class LegacyRuntime(Constants, Getters):
       """God-class composition root for the legacy backend."""

       def __init__(self) -> None:
           Constants.__init__(self)
           self.database = self.getDatabase()
           self.api = AnimeAPI(apis="all")
           self.getFileManager()
           self.getTorrentManager()

That single line — ``class LegacyRuntime(Constants, Getters):`` —
pulled in the entire settings handling surface of ``Constants``
*and* the database/filesystem/torrent helper surface of
``Getters``. Callers reached into ``runtime.dbPath``,
``runtime.settings``, ``runtime.log``, ``runtime.getDatabase``, and
dozens of other inherited helpers that the class never declared.

Applying the recipe gave the following decomposition:

* **Inventory** revealed four families of responsibilities:
  legacy backbone (database, file manager, torrent manager),
  configuration / settings, logging, and the public attribute
  surface (``database``, ``api``, ``fm``, ``tm``, ``settings``,
  ``settingsPath``).
* **Contracts** added a :class:`shared.config.ConfigProvider`
  (settings path, settings dictionary, ``update_settings``) and a
  :class:`shared.telemetry.LoggerService` (``log`` plus a
  ``from_defaults`` factory). Both are small, narrow types.
* **Composed services** introduced an internal
  ``_LegacyBackbone(Constants, Getters)`` that still subclasses
  the legacy parents *internally* but is hidden from the public
  surface. The public class became:

  .. code-block:: python

     class LegacyRuntime:
         def __init__(
             self,
             *,
             config: Optional[ConfigProvider] = None,
             logger: Optional[LoggerService] = None,
             backbone: Optional[_LegacyBackbone] = None,
             api: Optional[Any] = None,
         ) -> None:
             self._backbone = backbone or _LegacyBackbone()
             self._config = config or ConfigProvider(constants=self._backbone)
             self._logger = logger or LoggerService.from_defaults()
             if api is not None:
                 self._backbone.api = api

  Every attribute legacy callers historically reached for is now an
  explicit ``@property`` (``database``, ``api``, ``fm``, ``tm``,
  ``settings``, ``settingsPath``) or is forwarded through
  ``__getattr__`` to ``_backbone``.

* **Strangler call sites** migrated to construct ``LegacyRuntime``
  directly. The old multi-inheritance form survives as
  :class:`backend.adapters.legacy_runtime.InheritingLegacyRuntime`,
  which emits a ``DeprecationWarning`` at construction and is the
  *only* class that retains the inheritance shape for callers that
  rely on ``isinstance(runtime, Constants)``.
* **Tests** under ``tests/unit/monolith_decomp/`` pin the visible
  behavior: ``test_legacy_runtime_composition.py`` asserts that
  ``LegacyRuntime`` is no longer an instance of ``Constants`` or
  ``Getters`` and that delegation continues to work; the architecture
  test allows ``_LegacyBackbone`` and ``InheritingLegacyRuntime`` on
  the legacy allowlist while ``LegacyRuntime`` itself is checked
  like any other new code.

The net result: the public type is single-inheritance, the
collaborators are explicit at the composition root, and the legacy
helpers remain reachable through clearly named, easily replaced
attributes.

Allowlisted hotspots: ``AnimeAPI`` and ``APIUtils``
---------------------------------------------------

Two multi-inheritance classes remain on the ADR 0005 allowlist:

* :class:`animeAPI.AnimeAPI` (declared
  ``class AnimeAPI(Getters, Logger)``)
* :class:`animeAPI.APIUtils.APIUtils` (declared
  ``class APIUtils(Logger, Getters)``)

They have not been decomposed yet for two intertwined reasons:

* **Fan-out.** ``AnimeAPI`` is the multiplexer for every metadata
  provider wrapper under :mod:`animeAPI` (``AnilistCoWrapper``,
  ``JikanMoeWrapper``, ``MyAnimeListNetWrapper``, ...). It owns a
  background thread that loads providers, a queue that batches SQL
  writes, and a ``__getattr__`` proxy that routes arbitrary method
  names through a thread pool. The inherited ``Getters`` parent is
  used implicitly by individual wrappers for ``self.dbPath`` and
  ``self.settings`` access; the inherited ``Logger`` parent powers
  the ``self.log(...)`` calls scattered across every wrapper.
* **Cost vs. benefit.** Each provider wrapper is a separate file
  with its own assumption set about what the parent classes provide.
  Migrating ``AnimeAPI`` and ``APIUtils`` to composition therefore
  forces a coordinated edit across every provider wrapper plus the
  parts of :mod:`components.api_coordinator` that consume the
  ``AnimeAPI`` instance. Without that coordinated edit, the
  decomposition either breaks providers or recreates the ambient
  ``self.dbPath`` / ``self.log`` access through a new mixin —
  exactly what ADR 0005 forbids.

What would unlock the full decomposition:

* A small ``MetadataProviderContext`` (or similar) in :mod:`shared`
  carrying the database path, settings, and logger that the
  wrappers actually need.
* A constructor change on every provider wrapper to accept that
  context instead of inheriting ``Getters``/``Logger``.
* Replacement of ``AnimeAPI.__getattr__`` with an explicit dispatch
  table so the public surface is enumerated and testable.
* Characterization tests in ``tests/unit/monolith_decomp/`` that
  pin the current behaviour of ``AnimeAPI`` (thread startup,
  provider load, search fan-out, SQL queue draining) before any
  structural change lands.

Until that work is funded, the architecture suite tolerates the two
classes via ``LEGACY_CLASS_ALLOWLIST``, and any *new* code that
tries to inherit from more than one base will still fail the build.
The allowlist is a temporary acknowledgement of debt, not a license
to grow it.
