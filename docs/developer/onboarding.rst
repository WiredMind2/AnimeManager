Developer Onboarding Guide
==========================

Welcome to the AnimeManager development team! This guide will help you get started with contributing to the project.

Project Overview
----------------

AnimeManager is a comprehensive Python application for anime management with the following key features:

- Multi-API anime database integration (Kitsu, AniList, MyAnimeList, Jikan)
- Torrent search and download with multiple client support
- Built-in media players with custom keybindings
- Component-based architecture with dependency injection
- Extensible plugin system for APIs, databases, and media players

Architecture Overview
---------------------

The application uses a modern component-based architecture:

**Core Framework**
- ``BaseComponent``: Lifecycle management for all components
- ``EventBus``: Decoupled communication between components
- ``DependencyContainer``: Service registration and resolution

**Component Layer**
- ``ApplicationController``: Main application lifecycle
- ``APICoordinator``: Anime API management
- ``DatabaseManager``: Database operations
- ``UIManager``: User interface management
- ``DownloadManager``: Torrent download coordination
- ``MediaManager``: Media playback management
- ``SettingsManager``: Configuration management

**Plugin Systems**
- Anime APIs (``animeAPI/``)
- Database backends (``db_managers/``)
- File managers (``file_managers/``)
- Media players (``media_players/``)
- Torrent clients (``torrent_managers/``)
- Search engines (``search_engines/``)

Development Environment Setup
------------------------------

1. **Prerequisites**
   - Python 3.10+
   - Git
   - Virtual environment (recommended)

2. **Clone and Setup**
   .. code-block:: bash

      git clone <repository-url>
      cd animemanager
      python -m venv venv
      source venv/bin/activate  # On Windows: venv\Scripts\activate
      pip install -r requirements.txt
      pip install -r requirements-dev.txt

3. **Verify Setup**
   .. code-block:: bash

      python -c "import animeManager; print('Setup successful!')"

4. **Run Tests**
   .. code-block:: bash

      pytest tests/

5. **Build Documentation**
   .. code-block:: bash

      cd docs
      make html

Code Style and Standards
------------------------

**Python Style**
- Follow PEP 8 with some exceptions for readability
- Use type hints for all public APIs
- Maximum line length: 100 characters
- Use Google-style docstrings

**Naming Conventions**
- Classes: ``CamelCase``
- Functions/methods: ``snake_case``
- Constants: ``UPPER_CASE``
- Private members: ``_leading_underscore``

**Import Organization**
.. code-block:: python

   # Standard library imports
   import os
   import sys

   # Third-party imports
   import requests

   # Local imports
   from .base_component import BaseComponent
   from ..core import get_event_bus

Development Workflow
-------------------

1. **Create Feature Branch**
   .. code-block:: bash

      git checkout -b feature/your-feature-name

2. **Make Changes**
   - Write tests first (TDD approach)
   - Follow code style guidelines
   - Add docstrings to all public APIs
   - Update documentation as needed

3. **Run Quality Checks**
   .. code-block:: bash

      # Run tests
      pytest

      # Check code quality
      flake8 .
      mypy .

      # Check security
      bandit -r .

4. **Commit Changes**
   .. code-block:: bash

      git add .
      git commit -m "feat: add your feature description"

5. **Create Pull Request**
   - Push your branch
   - Create PR with detailed description
   - Ensure CI checks pass

Key Development Concepts
------------------------

**Component Lifecycle**
All components inherit from ``BaseComponent`` and follow this lifecycle:

1. **Initialization**: ``initialize()`` → ``_initialize()``
2. **Startup**: ``start()`` → ``_start()``
3. **Runtime**: Component is active
4. **Shutdown**: ``stop()`` → ``_stop()``

**Event-Driven Communication**
Components communicate via the event bus:

.. code-block:: python

   # Publishing events
   self.publish_event("component.data_updated", data)

   # Subscribing to events
   self.subscribe_event("other.component_ready", self.handle_ready)

**Dependency Injection**
Services are resolved through the dependency container:

.. code-block:: python

   # Register service
   container.register(IDatabaseManager, SQLiteManager())

   # Resolve service
   db_manager = self.get_dependency(IDatabaseManager)

**Plugin Architecture**
New plugins follow the base class pattern:

.. code-block:: python

   class MyAnimeAPI(BaseAnimeAPI):
       def search_anime(self, query: str) -> List[Anime]:
           # Implementation
           pass

Testing Guidelines
------------------

**Test Structure**
- Unit tests in ``tests/unit/``
- Integration tests in ``tests/integration/``
- Performance tests in ``tests/performance/``
- GUI tests in ``tests/gui/``

**Test Naming**
- Test files: ``test_*.py``
- Test classes: ``Test*``
- Test methods: ``test_*``

**Example Test**
.. code-block:: python

   import pytest
   from classes import Anime

   class TestAnime:
       def test_anime_creation(self):
           anime = Anime(title="Test Anime", id=1)
           assert anime.title == "Test Anime"
           assert anime.id == 1

Common Tasks
------------

**Adding a New Anime API**
1. Create new file in ``animeAPI/``
2. Inherit from ``BaseAnimeAPI``
3. Implement required methods
4. Register in ``animeAPI/__init__.py``
5. Add configuration options
6. Write comprehensive tests

**Adding a New Component**
1. Create component class inheriting from ``BaseComponent``
2. Implement ``_initialize()``, ``_start()``, ``_stop()``
3. Register in ``ApplicationController``
4. Add to dependency container if needed
5. Write tests and documentation

**Modifying Configuration**
1. Update ``settings.json`` structure
2. Update ``SettingsManager`` if needed
3. Add validation rules
4. Update documentation
5. Write migration guide if breaking

Getting Help
------------

- **Documentation**: Check ``docs/`` directory
- **Code Examples**: Look at existing implementations
- **Tests**: Comprehensive test suite shows usage patterns
- **Issues**: Check GitHub issues for similar problems
- **Discussions**: Use GitHub discussions for questions

Next Steps
----------

1. Explore the codebase starting with ``core/`` and ``components/``
2. Run the test suite and fix any failures
3. Try adding a small feature or fixing a bug
4. Review the contribution guidelines
5. Join our development discussions

Welcome aboard! 🎉