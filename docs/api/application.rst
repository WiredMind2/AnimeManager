Application Layer
=================

The :mod:`application` package hosts the use-case orchestration. It
depends on :mod:`domain` (entities, DTOs, policies, errors) and on
the abstract :mod:`ports` package; it never depends on concrete
adapter modules — those are injected by the composition root.

During Phase 3 of the refactor (see
:doc:`/migration/refactor_phases`) the canonical implementation of
:class:`AnimeApplicationService` still lives under
:mod:`backend.application.service`. The :mod:`application` package
re-exports the public surface so callers can already import from
``application.*``.

Package overview
----------------

.. automodule:: application
   :members:
   :undoc-members:
   :show-inheritance:

Services
--------

The service submodule exposes :class:`AnimeApplicationService`, the
single object client adapters interact with through the SDK facade.
Every method validates input via a policy, delegates IO to a port,
translates port-side exceptions into :class:`domain.errors.AnimeManagerError`
subclasses, and returns a DTO.

.. automodule:: application.services
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:

DTOs
----

The DTO submodule re-exports the request/response dataclasses that
flow across the application boundary
(:class:`backend.domain.dto.SearchRequest`,
:class:`backend.domain.dto.AnimeListRequest`,
:class:`backend.domain.dto.DownloadRequest`,
:class:`backend.domain.dto.AnimeListResponse`). They live in the
``backend.domain.dto`` module for historical reasons; the
:mod:`application.dto` namespace is the long-term home and is wired
up to forward the same symbols.

.. automodule:: application.dto
   :members:
   :undoc-members:
   :show-inheritance:
