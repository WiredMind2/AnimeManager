Monolith Decomposition Status
=============================

The decomposition effort tracked by ADR 0005 is complete.

Policy outcome
--------------

Runtime classes must inherit from at most one non-`Protocol`,
non-`Exception` base. Cross-cutting concerns are provided through
explicit collaborators.

Current hotspot status
----------------------

`adapters.api.AnimeAPI`
~~~~~~~~~~~~~~~~~~~~~~~

Completed. Uses composed `Getters` and `Logger` collaborators; no legacy
multi-inheritance remains.

`adapters.api.APIUtils`
~~~~~~~~~~~~~~~~~~~~~~~

Completed. Uses composed `Getters` and `Logger` collaborators; no legacy
multi-inheritance remains.

`adapters.legacy.runtime.LegacyRuntime`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Completed. Runtime path is composition-only. Legacy bridge inheritance
classes were removed from canonical runtime wiring.

Architecture enforcement
------------------------

`tests/architecture/test_no_new_multi_inheritance.py` enforces the
rule with an empty runtime allowlist for legacy exceptions.

Verification expectation
------------------------

Any reintroduction of runtime multi-inheritance now fails architecture
tests and must be refactored before merge.
Monolith Decomposition Status
=============================

This page is the running status of the multi-inheritance hotspots
identified in ADR 0005 (Composition Over Inheritance). Each hotspot
is a runtime class that historically combined cross-cutting
capabilities through multiple inheritance; the architecture suite
allowlists each one explicitly, and this page records the current
bases, the target shape, the work that is still blocking the
retirement, and the retirement plan.

The complementary :doc:`refactor_phases` document covers the broader
phase progression of the refactor; this page is the per-hotspot view.

How the allowlist works
-----------------------

The rule from ADR 0005 is that runtime classes inherit from at most
one non-``Protocol``, non-``Exception`` base. Cross-cutting concerns
(configuration, logging, persistence, IO, networking) must be
supplied as constructor parameters typed by a narrow interface.

The architecture test
``tests/architecture/test_no_new_multi_inheritance.py`` enforces this
rule and ships an explicit allowlist for the historical hotspots
named below. Each allowlisted class is paired with a characterization
test under ``tests/unit/monolith_decomp/`` that pins its externally
visible contract. Adding a class to the allowlist requires explicit
sign-off; removing a class from the allowlist is the goal of the
decomposition work tracked here.

Hotspots
--------

.. contents::
   :local:
   :depth: 1

``adapters.api.AnimeAPI``
~~~~~~~~~~~~~~~~~~~~~~~~~

Current bases
^^^^^^^^^^^^^

``class AnimeAPI`` — single inheritance from :class:`object` as of
the Technical Debt Burn-Down. The Phase 2 historical shape was
``AnimeAPI(Getters, Logger)``; both mixins have been retired in
favour of composition.

Target shape (achieved)
^^^^^^^^^^^^^^^^^^^^^^^

* Constructor accepts optional ``getters`` and ``logger``
  collaborators (``Getters`` and ``Logger`` instances) and stores
  them as private attributes ``self._getters`` / ``self._logger``.
* ``self.log(...)`` and ``self.getDatabase(...)`` are explicit
  forwarder methods so the legacy mixin call idioms keep working.
* ``__getattr__`` first delegates to ``self._getters`` (covering the
  long tail of helpers — ``setSettings``, ``saveAnime``, etc.) and
  falls back to the provider fan-out
  ``self.wrapper(name, *args, **kwargs)`` for unknown attributes.
* Allowlist entry removed from
  ``tests/architecture/test_no_new_multi_inheritance.py``.
* Characterization tests under
  ``tests/unit/monolith_decomp/test_anime_api_inheritance_surface.py``
  now assert the *absence* of ``Getters`` / ``Logger`` in the base
  classes, preventing a regression.

``adapters.api.APIUtils``
~~~~~~~~~~~~~~~~~~~~~~~~~

Current bases
^^^^^^^^^^^^^

``class APIUtils`` — single inheritance from :class:`object` as of
the Technical Debt Burn-Down. The Phase 2 historical shape was
``APIUtils(Logger, Getters)``.

Target shape (achieved)
^^^^^^^^^^^^^^^^^^^^^^^

* Constructor accepts optional ``getters`` and ``logger``
  collaborators (defaults to ``Getters()`` / ``Logger(logs="ALL")``
  so legacy zero-arg construction keeps working).
* ``self.database`` is initialised via ``self.getDatabase()`` (a
  method that forwards to ``self._getters``) so the existing
  ``monkeypatch.setattr('APIUtils.getDatabase', ...)`` test idiom
  still works.
* ``self.log(...)`` and ``self.getDatabase(...)`` are explicit
  forwarder methods.
* All other inherited helpers are routed through ``__getattr__`` to
  the composed collaborators.
* Provider wrappers (``AnilistCoWrapper``, ``JikanMoeWrapper``,
  ``KitsuIoWrapper``, ``MyAnimeListNetWrapper``) keep inheriting
  from :class:`APIUtils` unchanged — the constructor compatibility
  defaults absorb the change.
* Allowlist entry removed from
  ``tests/architecture/test_no_new_multi_inheritance.py``.
* Characterization test
  ``test_api_utils_no_longer_uses_legacy_mixin_inheritance``
  asserts the new shape.

``adapters.legacy.runtime.LegacyRuntime``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Current bases
^^^^^^^^^^^^^

``class LegacyRuntime`` — single inheritance from :class:`object`.
The class no longer inherits from :class:`constants.Constants` or
:class:`getters.Getters`; the decomposition completed in Phase 2.
The internal helper :class:`_LegacyBackbone` retains the
``(Constants, Getters)`` inheritance because it has to *use* the
existing legacy helpers (database handle, file manager, torrent
manager, settings path); it lives inside an underscored class so the
public ``LegacyRuntime`` does not expose the multi-inheritance to
the architecture tests or to callers.

The deprecated multi-inheritance form survives as
:class:`adapters.legacy.runtime.InheritingLegacyRuntime`,
which is also a subclass of :class:`_LegacyBackbone`. It emits a
``DeprecationWarning`` on construction and exists only so that
external callers using ``isinstance(runtime, Constants)`` or
``isinstance(runtime, Getters)`` keep working during the migration.

Target shape
^^^^^^^^^^^^

The Phase 2 composition is the target shape:

* :class:`LegacyRuntime` holds a private ``_LegacyBackbone`` (the
  only allowed multi-inheritance, allowlisted in the architecture
  test).
* :class:`LegacyRuntime` accepts a :class:`shared.config.ConfigProvider`
  and a :class:`shared.telemetry.LoggerService` as explicit
  collaborators.
* Public access to the legacy attributes (``database``, ``api``,
  ``fm``, ``tm``, ``settings``, ``settingsPath``) is exposed via
  explicit properties; everything else is delegated through
  :meth:`__getattr__` for backward compatibility.

The long-term retirement is to delete :class:`_LegacyBackbone` once
:mod:`db_managers`, :mod:`file_managers` and :mod:`torrent_managers`
are reachable directly through clean adapters in :mod:`adapters.*`
(Phase 4). At that point :class:`LegacyRuntime` collapses into a
small composition root inside :mod:`composition.root`.

Blocking work
^^^^^^^^^^^^^

* Phase 4 has relocated the infrastructure adapters to
  :mod:`adapters.persistence`, :mod:`adapters.file`,
  :mod:`adapters.torrent`, etc. :class:`_LegacyBackbone` still has
  to bootstrap the legacy graph because the
  :class:`getters.Getters` collaborator continues to mediate
  database/file/torrent manager discovery.
* :class:`InheritingLegacyRuntime` cannot be removed until every
  external caller has migrated. Greppable call sites must show no
  ``isinstance(*, Constants)`` / ``isinstance(*, Getters)`` checks
  against the runtime object.

Retirement plan
^^^^^^^^^^^^^^^

1. Replace :class:`getters.Getters`-mediated adapter discovery with
   explicit composition wiring inside :mod:`composition.root`. Once
   the runtime no longer needs the legacy backbone to resolve
   adapters, :class:`_LegacyBackbone` can be deleted.
2. Replace each property on :class:`LegacyRuntime` with the new
   adapter, then drop :class:`_LegacyBackbone`.
3. Remove :class:`InheritingLegacyRuntime` once the
   ``DeprecationWarning`` has elapsed and no callers remain.
4. Move the composed runtime construction into :mod:`composition.root`,
   leaving :mod:`adapters.legacy.runtime` as an empty compatibility
   module (the file has already moved out of ``backend/`` during
   Phase 3 physical relocation).

Summary table
-------------

.. list-table::
   :header-rows: 1
   :widths: 28 22 30 20

   * - Hotspot
     - Current bases
     - Target shape
     - Status
   * - :class:`adapters.api.AnimeAPI`
     - Single ``object`` base (post-burn-down)
     - Composed ``Getters`` + ``Logger`` collaborators; provider
       fan-out preserved through ``__getattr__``
     - **Decomposed**; characterization tests in
       ``tests/unit/monolith_decomp/test_anime_api_inheritance_surface.py``
   * - :class:`adapters.api.APIUtils`
     - Single ``object`` base (post-burn-down)
     - Composed ``Getters`` + ``Logger`` collaborators with default
       construction so provider wrappers keep working unchanged
     - **Decomposed**; characterization tests in the same file
   * - :class:`adapters.legacy.runtime.LegacyRuntime`
     - Single ``object`` base (post Phase 2)
     - Composition root binding :class:`ports.interfaces` directly to
       clean adapters
     - Decomposed in Phase 2; :class:`_LegacyBackbone` retained
       internally; :class:`InheritingLegacyRuntime` kept as a
       deprecated shim
