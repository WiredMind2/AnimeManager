Architecture Documentation
==========================

This document provides a comprehensive overview of the AnimeManager architecture, design patterns, and component interactions.

System Overview
---------------

AnimeManager is built using a component-based architecture with dependency injection and event-driven communication. The system is designed for modularity, testability, and extensibility.

.. figure:: ../_static/architecture_diagram.png
   :alt: System Architecture Diagram
   :align: center

   High-level system architecture

Core Principles
---------------

**Component-Based Design**
- Each component has a single responsibility
- Components are loosely coupled through events
- Dependencies are injected rather than imported
- Components follow a consistent lifecycle

**Event-Driven Communication**
- Components communicate via a centralized event bus
- Events are asynchronous by default
- Event types follow a hierarchical naming convention
- Weak references prevent memory leaks

**Plugin Architecture**
- APIs, databases, media players, etc. are plugins
- Base classes define interfaces
- Configuration determines which plugins to use
- Easy to add new implementations

**Thread Safety**
- All shared resources are properly synchronized
- Components can be accessed from multiple threads
- Database operations are thread-safe
- Event handling is thread-safe

Core Framework
--------------

BaseComponent
~~~~~~~~~~~~~

All components inherit from ``BaseComponent``, which provides:

- **Lifecycle Management**: ``initialize()``, ``start()``, ``stop()``, ``restart()``
- **Event Integration**: ``publish_event()``, ``subscribe_event()``
- **Dependency Resolution**: ``get_dependency()``
- **Logging**: Integrated logging support

.. code-block:: python

   class MyComponent(BaseComponent):
       def _initialize(self):
           # Component-specific initialization
           pass

       def _start(self):
           # Component startup logic
           pass

       def _stop(self):
           # Component cleanup
           pass

EventBus
~~~~~~~~

The event bus enables decoupled communication:

- **Publish/Subscribe Pattern**: Components publish events, others subscribe
- **Weak References**: Automatic cleanup when subscribers are destroyed
- **Thread Safety**: Safe for concurrent access
- **Async Support**: Events can be published synchronously or asynchronously

.. code-block:: python

   # Publishing an event
   self.publish_event("database.anime_updated", anime_data)

   # Subscribing to events
   self.subscribe_event("api.search_completed", self.handle_search_results)

Dependency Container
~~~~~~~~~~~~~~~~~~~

Manages service registration and resolution:

- **Service Registration**: Register implementations for interfaces
- **Factory Support**: Create instances on demand
- **Singleton Management**: Cache singleton instances
- **Type Safety**: Type hints ensure correct usage

.. code-block:: python

   # Register a service
   container.register(IDatabaseManager, SQLiteManager())

   # Resolve a service
   db = self.get_dependency(IDatabaseManager)

Component Architecture
----------------------

ApplicationController
~~~~~~~~~~~~~~~~~~~~~

The main orchestrator that manages the application lifecycle:

- **Component Registration**: Registers all application components
- **Lifecycle Coordination**: Starts/stops components in correct order
- **Error Handling**: Manages component failures gracefully
- **Shutdown Handling**: Ensures clean application shutdown

APICoordinator
~~~~~~~~~~~~~~

Manages anime API integrations:

- **Multi-API Support**: Coordinates multiple anime APIs
- **Load Balancing**: Distributes requests across APIs
- **Caching**: Caches API responses
- **Rate Limiting**: Respects API rate limits
- **Fallback Handling**: Graceful degradation when APIs fail

DatabaseManager
~~~~~~~~~~~~~~~

Handles all database operations:

- **Multiple Backends**: Supports SQLite, MySQL, Embedded MariaDB
- **Connection Pooling**: Efficient connection management
- **Query Optimization**: Optimized database queries
- **Migration Support**: Handles schema migrations
- **Backup/Restore**: Database maintenance operations

UIManager
~~~~~~~~~

Manages the user interface:

- **Window Management**: Creates and manages application windows
- **Event Handling**: Processes user interactions
- **Data Binding**: Connects UI to data models
- **Theme Support**: Customizable UI themes
- **Accessibility**: Screen reader and keyboard navigation support

DownloadManager
~~~~~~~~~~~~~~~

Coordinates torrent downloads:

- **Client Integration**: Supports multiple torrent clients
- **Queue Management**: Manages download queues
- **Progress Tracking**: Real-time download progress
- **Error Recovery**: Handles download failures
- **Bandwidth Management**: Controls download speeds

MediaManager
~~~~~~~~~~~~

Handles media playback:

- **Player Integration**: Supports VLC, MPV, FFmpeg
- **Playlist Management**: Creates and manages playlists
- **Subtitle Support**: Handles subtitle files
- **Audio/Video Sync**: Maintains A/V synchronization
- **Hardware Acceleration**: Uses GPU acceleration when available

SettingsManager
~~~~~~~~~~~~~~~

Manages application configuration:

- **Configuration Loading**: Loads settings from JSON files
- **Validation**: Validates configuration values
- **Runtime Updates**: Allows configuration changes at runtime
- **Migration**: Handles configuration format changes
- **Security**: Protects sensitive configuration data

Plugin Systems
--------------

Anime APIs
~~~~~~~~~~

Extensible anime database integration:

.. code-block:: python

   class BaseAnimeAPI(ABC):
       @abstractmethod
       def search_anime(self, query: str) -> List[Anime]:
           pass

       @abstractmethod
       def get_anime_details(self, anime_id: int) -> Anime:
           pass

Supported APIs:
- **Kitsu**: JSON:API based anime database
- **AniList**: GraphQL based anime tracking
- **MyAnimeList**: REST API for anime data
- **Jikan**: Unofficial MyAnimeList API

Database Managers
~~~~~~~~~~~~~~~~~

Multiple database backend support:

.. code-block:: python

   class BaseDB(ABC):
       THREAD_SAFE = False

       @abstractmethod
       def connect(self) -> None:
           pass

       @abstractmethod
       def execute_query(self, query: str, params: tuple = None) -> List[dict]:
           pass

Supported databases:
- **SQLite**: Embedded, file-based database
- **MySQL**: Full-featured relational database
- **Embedded MariaDB**: Embedded MySQL-compatible database

File Managers
~~~~~~~~~~~~~

File system abstraction:

.. code-block:: python

   class BaseFileManager(ABC):
       @abstractmethod
       def list_files(self, path: str) -> List[str]:
           pass

       @abstractmethod
       def upload_file(self, local_path: str, remote_path: str) -> None:
           pass

Supported file managers:
- **Local Disk**: Standard file system operations
- **FTP**: Remote FTP server integration

Media Players
~~~~~~~~~~~~~

Media playback abstraction:

.. code-block:: python

   class BasePlayer(ABC):
       @abstractmethod
       def play_file(self, file_path: str) -> None:
           pass

       @abstractmethod
       def pause(self) -> None:
           pass

Supported players:
- **VLC**: Cross-platform media player
- **MPV**: Lightweight, customizable player
- **FFmpeg**: Command-line media processing

Torrent Managers
~~~~~~~~~~~~~~~~

Torrent client integration:

.. code-block:: python

   class BaseTorrentManager(ABC):
       @abstractmethod
       def add_torrent(self, magnet_link: str) -> str:
           pass

       @abstractmethod
       def get_torrent_status(self, torrent_id: str) -> dict:
           pass

Supported clients:
- **qBittorrent**: Popular Qt-based client
- **Transmission**: Lightweight daemon client
- **LibTorrent**: Direct torrent library integration

Search Engines
~~~~~~~~~~~~~~

Torrent search integration:

.. code-block:: python

   class BaseSearchEngine(ABC):
       @abstractmethod
       def search(self, query: str) -> List[Torrent]:
           pass

       @abstractmethod
       def get_details(self, torrent_id: str) -> Torrent:
           pass

Supported engines:
- **Nova3**: Comprehensive torrent search framework
- Multiple torrent sites integrated through Nova3

Data Flow
---------

Typical data flow through the system:

1. **User Input** → UIManager → Event Bus
2. **Search Request** → APICoordinator → Anime APIs
3. **API Response** → Event Bus → UIManager (display results)
4. **Download Request** → DownloadManager → Torrent Manager
5. **Download Progress** → Event Bus → UIManager (update UI)
6. **Playback Request** → MediaManager → Media Player

Configuration Management
------------------------

Configuration is managed through a hierarchical JSON structure:

.. code-block:: json

   {
     "database": {
       "type": "sqlite",
       "path": "./data/anime.db"
     },
     "apis": {
       "enabled": ["kitsu", "anilist"],
       "rate_limits": {
         "requests_per_minute": 60
       }
     }
   }

The SettingsManager validates configuration and provides type-safe access.

Error Handling
--------------

Comprehensive error handling strategy:

- **Component Level**: Each component handles its own errors
- **Event Bus**: Errors in event handlers don't crash the system
- **Graceful Degradation**: System continues operating when components fail
- **User Feedback**: Errors are communicated to users appropriately
- **Logging**: All errors are logged with context

Performance Considerations
--------------------------

- **Lazy Loading**: Components initialize only when needed
- **Caching**: API responses and frequently accessed data are cached
- **Connection Pooling**: Database connections are pooled
- **Async Operations**: Long-running operations use async processing
- **Memory Management**: Proper cleanup prevents memory leaks

Security Measures
-----------------

- **Input Validation**: All user inputs are validated
- **SQL Injection Prevention**: Parameterized queries used throughout
- **Path Traversal Protection**: File paths are sanitized
- **API Key Management**: Sensitive credentials are encrypted
- **Network Security**: HTTPS used for all external communications

Testing Strategy
----------------

Comprehensive testing at multiple levels:

- **Unit Tests**: Individual component testing
- **Integration Tests**: Component interaction testing
- **End-to-End Tests**: Complete workflow testing
- **Performance Tests**: Load and stress testing
- **Security Tests**: Vulnerability assessment

Deployment
----------

The application supports multiple deployment scenarios:

- **Standalone Executable**: PyInstaller builds for Windows/Linux/Mac
- **Docker Container**: Containerized deployment
- **System Service**: Can run as a background service
- **Web Interface**: Optional web-based interface

Migration Path
--------------

For upgrading from older versions:

1. **Configuration Migration**: Automatic config format updates
2. **Database Migration**: Schema updates with data preservation
3. **Component Updates**: Backward-compatible component interfaces
4. **Deprecation Warnings**: Clear warnings for deprecated features

Future Extensions
-----------------

The architecture supports future enhancements:

- **Web Interface**: REST API for web-based access
- **Mobile App**: API-driven mobile application
- **Plugin Marketplace**: Third-party plugin distribution
- **Cloud Sync**: Cross-device synchronization
- **Machine Learning**: Recommendation engine integration

This architecture provides a solid foundation for continued development while maintaining code quality, testability, and user experience.