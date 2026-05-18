AnimeManager Documentation
==========================

AnimeManager is a Python application for managing an anime
collection. It searches multiple metadata providers, drives torrent
downloads across several torrent clients, and exposes the same
business logic to multiple front-ends through a ports-and-adapters
architecture.

This documentation tree is the long-form complement to the
top-level ``README.md`` and to the
`ADR series <https://github.com/WiredMind2/AnimeManager/tree/main/docs/adr>`_
that captures the architectural rationale (ADRs 0001 through 0006).

Quickstart::

    python run.py            # launch the desktop Tk client
    python run.py api        # launch the FastAPI HTTP client
    pytest -m "not slow"     # fast test slice
    pytest -m architecture   # layer-boundary checks

.. toctree::
   :maxdepth: 2
   :caption: Developer Documentation:

   developer/architecture
   developer/layer-contracts
   developer/runtime-flows
   developer/decomposition-guide
   developer/testing
   developer/extension-points
   developer/api_db_pipeline
   developer/stability-slos
   developer/operations
   developer/contributing_pipeline
   developer/onboarding
   developer/nextjs_ui_inventory
   developer/nextjs_api_contracts

.. toctree::
   :maxdepth: 2
   :caption: Feature Guides:

   features/anime_data
   features/search_pipeline
   features/downloads_torrents
   features/media_playback
   features/persistence
   features/configuration
   features/tk_ui
   features/web_ui

.. toctree::
   :maxdepth: 2
   :caption: Runbooks:

   runbooks/local_dev
   runbooks/release_build

.. toctree::
   :maxdepth: 2
   :caption: Migration:

   migration/refactor_phases
   migration/monolith_decomposition_status

.. toctree::
   :maxdepth: 3
   :caption: API Reference:

   api/backend
   api/clients
   api/core
   api/classes
   api/domain
   api/application
   api/ports
   api/adapters
   api/shared
   api/composition

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
