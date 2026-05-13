Ports Layer
===========

The :mod:`ports` package contains the ``Protocol`` interfaces that
the application layer consumes. Ports declare *capabilities*, not
implementations: they depend on :mod:`domain` and nothing else, and
they never import concrete adapters, frameworks or IO libraries.

The canonical interfaces still live under :mod:`backend.ports.interfaces`
during Phase 3 of the refactor (see :doc:`/migration/refactor_phases`);
:mod:`ports` and :mod:`ports.outbound` re-export them so the new
import paths work today.

Package overview
----------------

.. automodule:: ports
   :members:
   :undoc-members:
   :show-inheritance:

Outbound ports
--------------

Outbound (driven) ports describe what the application *needs* from
infrastructure. Adapters under :mod:`adapters.*` implement these
protocols; the composition root binds one implementation to each
port.

* :class:`backend.ports.interfaces.AnimeRepositoryPort` — local
  catalogue search and listing.
* :class:`backend.ports.interfaces.MetadataProviderPort` — remote
  multi-provider search (Kitsu, AniList, MyAnimeList, Jikan).
* :class:`backend.ports.interfaces.DownloadPort` — torrent
  orchestration.
* :class:`backend.ports.interfaces.UserActionsPort` — user tagging
  and like/seen state.

.. automodule:: ports.outbound
   :members:
   :undoc-members:
   :show-inheritance:
