
# AnimeManager

[![Documentation Status](https://readthedocs.org/projects/animemanager/badge/?version=latest)](https://animemanager.readthedocs.io/en/latest/?badge=latest)

AnimeManager is a comprehensive Python application for anime management featuring torrent downloading, media playback, and multi-API anime database integration. Built with a modern component-based architecture using dependency injection and event-driven communication.

## Features

- **Multi-API Anime Database Integration**: Search through thousands of anime across multiple APIs (Kitsu, AniList, MyAnimeList, Jikan)
- **Torrent Search & Download**: Integrated torrent search with support for multiple torrent clients (qBittorrent, Transmission, LibTorrent)
- **Media Playback**: Built-in media players (VLC, MPV, FFmpeg) with custom keybindings
- **Component-Based Architecture**: Modular design with dependency injection and event bus communication
- **Database Support**: Multiple database backends (SQLite, MySQL, Embedded MariaDB)
- **File Management**: Local and FTP file management with automatic organization
- **Search Engines**: Extensible search engine framework with Nova3 integration

## Architecture

AnimeManager uses a modern component-based architecture:

- **Core Framework**: Event bus, dependency injection container, and base component system
- **Components**: Focused, single-responsibility components for different application concerns
- **Plugin System**: Extensible APIs, database managers, media players, and search engines
- **Thread Safety**: Comprehensive threading support with proper synchronization

## Installation

### From Source

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/animemanager.git
   cd animemanager
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python animeManager.py
   ```

### Building Executable

Run the PyInstaller build script:
```bash
./build_pyinstaller.bat
```

The executable will be created in the `/dist` folder.

## Configuration

AnimeManager uses a comprehensive JSON configuration file (`settings.json`) with the following main sections:

- **UI**: Colors, date states, file markers, tag colors, torrent states
- **Anime**: API settings, timeouts, trending limits, top publishers
- **Database**: Connection settings for SQLite, MySQL, or Embedded MariaDB
- **File Managers**: Local and FTP configuration
- **Torrent Managers**: qBittorrent and Transmission settings
- **Media Players**: Player order and keybindings
- **Phone Sync**: Mobile server configuration

See the [Configuration Documentation](docs/user/configuration.rst) for detailed options.

## Usage

1. **Search Anime**: Search for anime by title across multiple APIs
2. **Download Torrents**: Click "Download torrents" and select your preferred file
3. **Watch Content**: Use the "Watch" button to play downloaded content
4. **Manage Library**: Organize and track your anime collection

## Documentation

- [User Documentation](docs/user/)
- [Developer Documentation](docs/developer/)
- [API Reference](docs/api/)

## Development

### Setting up Development Environment

1. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

2. Run tests:
   ```bash
   pytest
   ```

3. Build documentation:
   ```bash
   cd docs
   make html
   ```

### Module Structure and Responsibilities

AnimeManager follows a modular architecture with clear separation of concerns. Each module encapsulates specific functionality and communicates through the event bus and dependency injection system.

#### Core Framework (`core/`)

The foundation layer providing essential services for component lifecycle management, communication, and dependency resolution.

- **`base_component.py`**: [`BaseComponent`](core/base_component.py:16)
  - Abstract base class for all application components
  - Implements lifecycle methods: `initialize()`, `start()`, `stop()`, `restart()`
  - Provides dependency injection via `get_dependency()`
  - Handles event publishing/subscribing with `publish_event()`, `subscribe_event()`

- **`event_bus.py`**: [`EventBus`](core/event_bus.py:12)
  - Centralized event-driven communication system
  - Supports synchronous and asynchronous event publishing
  - Thread-safe with proper synchronization
  - Manages event subscriptions and listener cleanup

- **`dependency_container.py`**: [`DependencyContainer`](core/dependency_container.py:13)
  - Service locator pattern implementation
  - Supports singleton and factory registrations
  - Thread-safe dependency resolution
  - Enables loose coupling between components

#### Application Components (`components/`)

High-level business logic components that orchestrate application functionality.

- **`application_controller.py`**: [`ApplicationController`](components/application_controller.py:16)
  - Manages the lifecycle of all application components
  - Coordinates component initialization, starting, and stopping
  - Handles remote and late startup scenarios
  - Provides centralized component registration

- **`api_coordinator.py`**: [`APICoordinator`](components/api_coordinator.py:15)
  - Coordinates anime data retrieval across multiple APIs
  - Implements rate limiting to prevent API abuse
  - Handles search deduplication and result aggregation
  - Manages API switching and error handling

- **`database_manager.py`**: [`DatabaseManager`](components/database_manager.py:15)
  - Provides high-level database operations
  - Manages anime search, metadata retrieval, and torrent storage
  - Handles database connection pooling and transactions
  - Supports multiple database backends through abstraction

- **`download_manager.py`**: [`DownloadManager`](components/download_manager.py:16)
  - Orchestrates torrent download operations
  - Manages download queue and status tracking
  - Coordinates with torrent and file managers
  - Handles download cancellation and error recovery

- **`media_manager.py`**: [`MediaManager`](components/media_manager.py:13)
  - Manages media playback across different players
  - Provides unified interface for play/pause/seek operations
  - Handles player selection and initialization
  - Supports multiple media formats and codecs

- **`settings_manager.py`**: [`SettingsManager`](components/settings_manager.py:15)
  - Centralized configuration management
  - Supports nested settings with validation
  - Provides change notifications and callbacks
  - Handles settings persistence and reloading

- **`ui_manager.py`**: [`UIManager`](components/ui_manager.py:12)
  - Manages user interface windows and dialogs
  - Provides factory pattern for window creation
  - Handles loading screens and error dialogs
  - Coordinates UI event handling

#### Anime API Integrations (`animeAPI/`)

External API wrappers for anime data sources.

- **`__init__.py`**: [`AnimeAPI`](animeAPI/__init__.py:38)
  - Main API aggregator class
  - Dynamically loads and manages API wrappers
  - Provides unified interface for all anime operations
  - Handles threading and queue management for API calls

- **`AnilistCo.py`**: [`AnilistCoWrapper`](animeAPI/AnilistCo.py:66)
  - Integration with AniList GraphQL API
  - Handles anime search, character data, and metadata
  - Implements GraphQL query building and pagination

- **`JikanMoe.py`**: [`JikanMoeWrapper`](animeAPI/JikanMoe.py:13)
  - MyAnimeList API integration via Jikan
  - Provides anime, character, and schedule data
  - Handles rate limiting and error recovery

- **`KitsuIo.py`**: [`KitsuIoWrapper`](animeAPI/KitsuIo.py:40)
  - Kitsu.io API client
  - Supports anime search and detailed metadata
  - Includes character and episode information

- **`MyAnimeListNet.py`**: [`MyAnimeListNetWrapper`](animeAPI/MyAnimeListNet.py:19)
  - Direct MyAnimeList API integration
  - Handles OAuth authentication flow
  - Provides user-specific data and recommendations

- **`APIUtils.py`**: [`APIUtils`](animeAPI/APIUtils.py:136)
  - Shared utilities for API operations
  - Implements caching system with TTL
  - Provides database integration for API data storage
  - Handles request retry logic and error handling

#### Database Managers (`db_managers/`)

Database abstraction layer supporting multiple backends.

- **`base.py`**: [`BaseDB`](db_managers/base.py:199)
  - Abstract base class for database operations
  - Implements connection pooling and caching
  - Provides common CRUD operations and metadata handling

- **`dbManager.py`**: [`db_instance`](db_managers/dbManager.py:122)
  - SQLite database implementation
  - Thread-safe operations with query caching
  - Supports stored procedures and complex queries

- **`embeddedMariaDB.py`**: [`EmbeddedMariaDB`](db_managers/embeddedMariaDB.py:238)
  - Embedded MariaDB server management
  - Automatic server startup and configuration
  - Handles database initialization and security setup

- **`mySql.py`**: [`MySQL`](db_managers/mySql.py:34)
  - MySQL database connector
  - Connection pooling and error handling
  - Supports stored procedures and advanced queries

#### File Managers (`file_managers/`)

File system abstraction for local and remote storage.

- **`base.py`**: [`BaseFileManager`](file_managers/base.py:11)
  - Abstract base class for file operations
  - Common interface for file existence, reading, writing

- **`FTP.py`**: [`FTPFileManager`](file_managers/FTP.py:11)
  - FTP/SFTP client implementation
  - Supports secure file transfers
  - Handles connection pooling and error recovery

- **`local_disk.py`**: [`LocalFileManager`](file_managers/local_disk.py:18)
  - Local file system operations
  - Asynchronous file I/O with chunking
  - Optimized directory listing and caching

#### Media Players (`media_players/`)

Media playback integrations.

- **`__init__.py`**: [`MediaPlayers`](media_players/__init__.py:31)
  - Player discovery and management
  - Dynamic loading of available players

- **`base_player.py`**: [`BasePlayer`](media_players/base_player.py:28)
  - Abstract base class for media players
  - Common interface for playback controls
  - Window management and UI integration

- **`vlc_player.py`**: [`VlcPlayer`](media_players/vlc_player.py:41)
  - VLC media player integration
  - Supports all major video formats
  - Advanced playback controls and subtitles

- **`mpv_player.py`**: [`MpvPlayer`](media_players/mpv_player.py:41)
  - MPV player wrapper
  - High-performance video playback
  - Customizable video filters and shaders

- **`ff_player.py`**: [`FfPlayer`](media_players/ff_player.py:22)
  - FFmpeg-based player implementation
  - Lightweight and cross-platform
  - Direct frame rendering capabilities

#### Search Engines (`search_engines/`)

Torrent search engine integrations.

- **`__init__.py`**: Search coordination function
  - Unified search interface across engines
  - Result aggregation and filtering

- **`parserUtils.py`**: [`ParserUtils`](search_engines/parserUtils.py:16)
  - Base class for search parsers
  - Common utilities for web scraping and parsing

- **`nyaasi.py`**: Nyaa.si parser
  - RSS-based torrent search
  - High-quality anime torrent indexing

- **`anirena.py`**: Anirena parser
  - Specialized anime torrent search
  - Multiple quality and format support

- **`tokyotosho.py`**: TokyoTosho parser
  - Comprehensive anime torrent database
  - Advanced filtering and search options

#### Torrent Managers (`torrent_managers/`)

Torrent client integrations.

- **`base.py`**: [`BaseTorrentManager`](torrent_managers/base.py:13)
  - Abstract base class for torrent operations
  - Common interface for add, list, move, delete operations

- **`qbittorrent.py`**: [`qBittorrent`](torrent_managers/qbittorrent.py:25)
  - qBittorrent Web API integration
  - Full torrent management capabilities
  - Category and tag support

- **`transmission.py`**: [`Transmission`](torrent_managers/transmission.py:22)
  - Transmission daemon client
  - Lightweight and efficient
  - RPC API communication

- **`deluge.py`**: [`Deluge`](torrent_managers/deluge.py:22)
  - Deluge torrent client integration
  - Advanced torrent features
  - Multi-host support

- **`libtorrent.py`**: [`LibTorrent`](torrent_managers/libtorrent.py:37)
  - Direct libtorrent library integration
  - High-performance torrenting
  - Embedded torrent functionality

### Architecture Relationships

The modules interact through a layered architecture:

1. **Core Framework** provides the foundation for all other modules
2. **Components** orchestrate business logic using services from specialized modules
3. **Specialized Modules** (APIs, DB, Files, Media, Search, Torrent) provide domain-specific functionality
4. **Event Bus** enables decoupled communication between all layers
5. **Dependency Injection** allows flexible service composition and testing

This architecture ensures:
- **Modularity**: Each module has clear responsibilities
- **Testability**: Components can be tested in isolation
- **Extensibility**: New implementations can be added without modifying existing code
- **Maintainability**: Changes are localized to specific modules

## Contributing

We welcome contributions! Please see our [Contributing Guide](docs/developer/contributing.rst) for details on:

- Code style and standards
- Testing procedures
- Pull request process
- Development workflow

## License

This project is open source. See LICENSE file for details.

## Disclaimer

This application is for educational and personal use only. Please respect copyright laws and terms of service of the APIs and services used.
