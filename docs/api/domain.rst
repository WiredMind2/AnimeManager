Domain Layer
============

The :mod:`domain` package is the pure-business-logic layer. It owns
the entities, the DTO request/response types, the unified error
hierarchy, and the small pure policies that govern catalogue
behavior. Per ADR 0003 it has zero dependencies on infrastructure
modules; per ADRs 0005 and 0006 it is the canonical destination for
business types that today still live under :mod:`backend.domain`.

During Phase 3 of the refactor (see
:doc:`/migration/refactor_phases`) the canonical implementation
still lives under :mod:`backend.domain`. The :mod:`domain` package
re-exports those symbols so that both ``from domain import ...`` and
``from backend.domain import ...`` resolve to the same objects.

Package overview
----------------

.. automodule:: domain
   :members:
   :undoc-members:
   :show-inheritance:

Entities
--------

The entity submodule re-exports the immutable dataclasses
(:class:`backend.domain.entities.AnimeEntity`,
:class:`backend.domain.entities.TorrentEntity`) together with the
:func:`backend.domain.entities.from_legacy_anime` helper that
adapters use to translate the legacy :class:`classes.Anime` records
into domain entities.

.. automodule:: domain.entities
   :members:
   :undoc-members:
   :show-inheritance:

Policies
--------

The policy submodule hosts the small pure functions that the
application service calls before delegating to a port — typically
input normalisation (:func:`backend.domain.policies.normalize_search_query`)
or state derivation (:func:`backend.domain.policies.derive_status`).

.. automodule:: domain.policies
   :members:
   :undoc-members:
   :show-inheritance:

Errors
------

The domain error hierarchy is the single error model that every layer
above the infrastructure plug-ins is expected to use, per ADR 0004.
Adapters translate vendor-specific exceptions into one of the
subclasses below; the HTTP client maps each subclass to an HTTP
status code; the Tk client maps them to dialog signals.

.. automodule:: domain.errors
   :members:
   :undoc-members:
   :show-inheritance:
