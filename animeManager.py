import json
import multiprocessing
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import traceback
import urllib.parse
import webbrowser
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from tkinter import ALL, TclError

try:
    import sys

    import bencoding
    import requests
    from PIL import Image, ImageTk
    from pypresence import Presence

    # from thefuzz import fuzz
    if getattr(sys, "frozen", None):
        basedir = sys._MEIPASS  # type: ignore
        os.environ["REQUESTS_CA_BUNDLE"] = os.path.join(
            basedir, "certifi", "cacert.pem"
        )  # Required for requests and certifi
except ModuleNotFoundError as e:
    import sys

    # Set requests to None to handle the unbound issue
    requests = None

    if getattr(sys, "frozen", None):
        print(f"Module missing: {e}")
    else:
        print(f"Installing modules! {e}")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
        )
        # os.execv(sys.executable, ['python'] + sys.argv) # Restart the app
    time.sleep(20)
    # sys.exit()

# globals()['auto_launch_initialized'] = True

try:
    # Try package-relative imports first (when run as package)
    from . import animeAPI, search_engines, torrent_managers, windows
    from .classes import (Anime, AnimeList, Character, DefaultDict, Magnet,
                          SortedDict, SortedList, Torrent, TorrentList)
    from .constants import Constants
    from .db_managers import databases
    from .discord_presence import DiscordPresence
    from .file_managers import FTPFileManager, LocalFileManager
    from .getters import Getters
    from .logger import Logger
    from .media_players import MediaPlayers
    from .update_utils import UpdateUtils
    # New component architecture
    from .core import get_dependency_container, get_event_bus
    from .components import (ApplicationController, DatabaseManager, APICoordinator,
                           UIManager, MediaManager, DownloadManager, SettingsManager)
except ImportError as e:
    # Fallback to absolute imports (when run standalone)
    try:
        import animeAPI
        import search_engines
        import torrent_managers
        import windows
        from classes import (Anime, AnimeList, Character, DefaultDict, Magnet,
                              SortedDict, SortedList, Torrent, TorrentList)
        from constants import Constants
        from db_managers import databases
        from discord_presence import DiscordPresence
        from file_managers import FTPFileManager, LocalFileManager
        from getters import Getters
        from logger import Logger
        from media_players import MediaPlayers
        from update_utils import UpdateUtils
        # New component architecture
        from core import get_dependency_container, get_event_bus
        from components import (ApplicationController, DatabaseManager, APICoordinator,
                               UIManager, MediaManager, DownloadManager, SettingsManager)
    except ImportError as fallback_error:
        print(f"Original import error: {e}")
        print(f"Fallback import error: {fallback_error}")
        print(
            "This script should be run as a module or with proper package installation!"
        )
        print("Try: pip install -e . (for development) or python -m AnimeManager")
        raise

# TodoList - Yeah I know there are better tools for that but I'm lazy
# TODO - Torrent path dependent of file manager / multiple file managers?
# TODO - Look for torrent client on file system + give installation link?
# TODO - Multiple torrent clients compatibility (module-like)
# TODO - App Installer
# TODO - Relations tree
# TODO - simkl.com API
# TODO - Logger panel
# TODO - characterWindow - fix 'Go to anime' button
# TODO - Hardcoded 'dual audio' in torrents search keys
# TODO - Fix multi word search -> just search
# TODO - Fix known torrent color match in getTorrentColor() -> compare file length?
# TODO - Tkinter event queue
# TODO - Recently finished anime should appear on top of the watching filter
# TODO - Fix characters API
# TODO - Use the db.get_lock() with API wrappers
# TODO - Factory functions for characters and anime mappings
# TODO - RPC animes storage size is incorrect
# TODO - What to do with the MAL API token registration? - Idk?
# TODO - Load new images on downloading error
# TODO - Implement the TableFrame class
# TODO - Add filter for torrent list (seeds / name)
# TODO - Play button on media player isn't centered
# TODO - Update the loading... text on media player
# TODO - Exception ignored in Var.__del__ on media player
# TODO - Put single files in directories
# TODO - Add search by studios ?
# TODO - Add pictures window
# TODO - Allow window resizing ?
# TODO - Auto associate latest torrents ?
# TODO - Add python-based torrent client -> uh oh complicated
# TODO - Add RSS option
# TODO - Automatic torrent downloading from RSS?
# TODO - Qt windows / themes -> nah
# TODO - Phone version -> Yup maybe not (Apple dev licence is too expensive)
# TODO - Web version
# TODO - Name idea: Nymera ?


class Manager(
    Constants,
    Logger,
    UpdateUtils,
    Getters,
    MediaPlayers,
    DiscordPresence,
    *windows.windows(),
):
    """
    Main application manager - now a facade coordinating specialized components.
    Maintains backward compatibility while using new component architecture internally.
    """

    def __init__(self, remote=False):
        # Initialize legacy attributes for backward compatibility
        self.start = time.time()
        Logger.__init__(self)
        Constants.__init__(self)

        self.remote = remote
        self.animeFolder = []
        self.searchQueue = []
        self.relationIds = []
        self.characterIds = []
        self.animeHashes = {}
        self.timer_id = None
        self.stopSearch = False
        self.closing = False
        self.maxLogsSize = 50000  # In bytes
        self.blank_image = None
        self.last_search = 0, ""

        # UI window references (maintained for backward compatibility)
        self.root = None
        self.initWindow = None
        self.logsWindow = None
        self.optionsWindow = None
        self.ddlWindow = None
        self.fileListWindow = None
        self.torrentFilesWindow = None
        self.loadingWindow = None
        self.characterListWindow = None
        self.characterWindow = None
        self.settingsWindow = None
        self.diskWindow = None
        self.textPopupWindow = None
        self.searchTermsWindow = None

        # Menu and action configurations
        self.menuOptions = {
            "Liked characters": {
                "color": "Green",
                "command": lambda: self.drawCharactersWindow("LIKED"),
            },
            "Disk manager": {"color": "Orange", "command": self.drawDiskWindow},
            "Log panel": {"color": "Blue", "command": self.drawLogsWindow},
            "Clear logs": {"color": "Green", "command": self.clearLogs},
            "Clear cache": {"color": "Blue", "command": self.clearCache},
            # 'Clear db': {'color': 'Red', 'command': self.clearDb},
            "Settings": {"color": "Gray", "command": self.drawSettingsWindow},
            "Reload": {"color": "Orange", "command": self.reloadAll},
            "Exit": {"color": "Red", "command": self.quit},
        }
        self.actionButtons = (
            {"text": "Copy title", "color": "Green", "command": self.copy_title},
            {"text": "Reload", "color": "Blue", "command": self.reload},
            {"text": "Redownload files", "color": "Green", "command": self.redownload},
            {
                "text": "Characters",
                "color": "Green",
                "command": self.drawCharactersWindow,
            },
            {
                "text": "Delete seen episodes",
                "color": "Blue",
                "command": self.deleteSeenEpisodes,
            },
            {"text": "Delete all files", "color": "Red", "command": self.deleteFiles},
            {"text": "Remove from db", "color": "Red", "command": self.delete},
        )

        # Initialize new component architecture
        self._initialize_components()

        # Start application through application controller
        self._application_controller.initialize()
        self._application_controller.start()

    def _initialize_components(self):
        """Initialize the new component architecture."""
        # Get dependency container and event bus
        self._dependency_container = get_dependency_container()
        self._event_bus = get_event_bus()

        # Create and register components
        self._application_controller = ApplicationController(remote=self.remote)
        self._database_manager = DatabaseManager()
        self._api_coordinator = APICoordinator()
        self._ui_manager = UIManager()
        self._media_manager = MediaManager()
        self._download_manager = DownloadManager()
        self._settings_manager = SettingsManager()

        # Register components with dependency container
        self._dependency_container.register(ApplicationController, self._application_controller)
        self._dependency_container.register(DatabaseManager, self._database_manager)
        self._dependency_container.register(APICoordinator, self._api_coordinator)
        self._dependency_container.register(UIManager, self._ui_manager)
        self._dependency_container.register(MediaManager, self._media_manager)
        self._dependency_container.register(DownloadManager, self._download_manager)
        self._dependency_container.register(SettingsManager, self._settings_manager)

        # Register components with application controller
        components = [
            self._database_manager,
            self._api_coordinator,
            self._ui_manager,
            self._media_manager,
            self._download_manager,
            self._settings_manager,
        ]

        for component in components:
            self._application_controller.register_component(component)

        # Set up component dependencies
        self._setup_component_dependencies()

        # Subscribe to component events for backward compatibility
        self._setup_event_handlers()

    def _setup_component_dependencies(self):
        """Set up dependencies between components."""
        # Set database for database manager
        database = self.getDatabase()
        self._database_manager.set_database(database)

        # Set API for API coordinator
        if hasattr(self, 'api'):
            self._api_coordinator.set_api(self.api)

        # Set media players for media manager
        if hasattr(self, 'media_players'):
            self._media_manager.set_media_players(self)

        # Set managers for download manager
        if hasattr(self, 'tm'):
            self._download_manager.set_torrent_manager(self.tm)
        if hasattr(self, 'fm'):
            self._download_manager.set_file_manager(self.fm)

        # Set root window for UI manager
        self._ui_manager.set_root(self.root)

    def _setup_event_handlers(self):
        """Set up event handlers for backward compatibility."""
        # Handle application events
        self._event_bus.subscribe("application.quit_requested", lambda e, d: self.quit())
        self._event_bus.subscribe("application.reload_requested", lambda e, d: self.reloadAll())
        self._event_bus.subscribe("application.ui_ready", lambda e, d: self.drawInitWindow())

        # Handle UI events
        self._event_bus.subscribe("ui.show_window", self._handle_ui_event)
        self._event_bus.subscribe("ui.hide_window", self._handle_ui_event)

    def _handle_ui_event(self, event_type, data):
        """Handle UI events for backward compatibility."""
        # This maintains compatibility with existing UI code
        pass

    def late_startup(self):
        """Perform late startup tasks after UI initialization."""
        self.log("MAIN_STATE", "Performing late startup")
        # Load the default anime list to populate the UI
        if hasattr(self, 'animeList'):
            self.animeList.from_filter("DEFAULT")

    # Backward compatibility properties
    @property
    def api(self):
        """Access to API through APICoordinator."""
        if hasattr(self, '_api_coordinator'):
            return self._api_coordinator._api
        return None

    @api.setter
    def api(self, value):
        """Set API instance."""
        if hasattr(self, '_api_coordinator'):
            self._api_coordinator.set_api(value)
        self._api_instance = value

    @property
    def player(self):
        """Access to media player through MediaManager."""
        if hasattr(self, '_media_manager'):
            return self._media_manager.get_current_player()
        return getattr(self, '_player', None)

    @player.setter
    def player(self, value):
        """Set player instance."""
        self._player = value

    # Additional backward compatibility methods
    def getFileManager(self, manager=None, update=False):
        """Get file manager - maintained for backward compatibility."""
        # This delegates to the existing implementation
        # The actual implementation is in Getters mixin
        return super().getFileManager(manager, update)

    def getTorrentManager(self, manager=None, update=False):
        """Get torrent manager - maintained for backward compatibility."""
        # This delegates to the existing implementation
        # The actual implementation is in Getters mixin
        return super().getTorrentManager(manager, update)

    # Legacy startup method - now delegates to application controller
    def startup(self):
        """Legacy startup method - maintained for backward compatibility."""
        # This method is now handled by the application controller
        # but we keep it for any external code that might call it
        pass

    # ___Search___
    def search(self, event=None, force_search=False):
        """Search for anime - now delegates to components."""
        if event:
            if event.state & 0x4 != 0:
                # Control modifier
                force_search = True

        terms = self.searchTerms.get()
        if len(terms) > 2 or force_search:
            if not force_search:
                # Try database search first
                anime_list = self._database_manager.search_anime(terms)
                if anime_list is not None:
                    self.animeList.set(anime_list)
                    return

            # Fall back to API search
            l_time, l_terms = self.last_search
            if l_terms == terms and not force_search:
                return

            now = time.time()
            if not force_search and now - l_time < 1:
                delay = int((1 - now + l_time) * 1000 + 1)
                if self.root is not None:
                    self.root.after(delay, self.search)
                return

            self.last_search = now, terms

            # Show message that we're switching to online search
            if not force_search:
                self.log(f"No results in database for '{terms}', searching online...")

            self.stopSearch = False
            self.loading()

            # Use API coordinator for search
            def search_callback():
                try:
                    results = self._api_coordinator.search_anime(terms, limit=self.animePerPage)
                    if self.root is not None and not self.closing:
                        self.root.after(0, lambda: self.animeList.set(results) if results else None)
                except Exception as e:
                    self.log("ANIME_SEARCH", f"Error during online search: {e}")
                    if self.root is not None:
                        self.root.after(0, lambda: setattr(self, "stopSearch", True))

            threading.Thread(target=search_callback, daemon=True, name="APISearchThread").start()
        else:
            self.animeList.from_filter("DEFAULT")

        if self.root is None:
            return

    def searchDb(self, terms):
        """
        Database search - now delegates to DatabaseManager component.
        Maintained for backward compatibility.
        """
        import warnings
        warnings.warn("Manager.searchDb() is deprecated. Use DatabaseManager.search_anime() instead.",
                     DeprecationWarning, stacklevel=2)

        return self._database_manager.search_anime(terms)

    def searchNgrams(self, terms):  # TODO
        def ngrams(string, n=3):
            string = [l for l in string.lower() if l.isalnum() or l == " "]
            ngrams = zip(*[string[i:] for i in range(n)])
            return ("".join(ngram) for ngram in ngrams)

        with self.database.get_lock():
            data = self.database.sql("SELECT id, value FROM title_synonyms")

            t_ngrams = set(ngrams(terms))
            matches = defaultdict(lambda: 0)
            for id, value in data:
                for ngram in ngrams(value):  # Removed comment
                    if ngram in t_ngrams:
                        matches[id] += 1

            # Return empty AnimeList if no matches found
            if not matches:
                return AnimeList([])

            sql = (
                "SELECT * FROM anime WHERE id IN(" + ",".join("?" * len(matches)) + ");"
            )
            return AnimeList(
                Anime(data)
                for data in SortedList([(lambda e: matches[e["id"]], True)]).extend(
                    self.database.sql(sql, matches.keys(), to_dict=True)
                )
            )

    def getAnimelist(self, criteria, listrange=(0, 50), hideRated=None, user_id=None):
        """
        Get anime list - now delegates to DatabaseManager component.
        Maintained for backward compatibility.
        """
        import warnings
        warnings.warn("Manager.getAnimelist() is deprecated. Use DatabaseManager.get_anime_list() instead.",
                     DeprecationWarning, stacklevel=2)

        if hideRated is None:
            hideRated = getattr(self, 'hideRated', True)

        return self._database_manager.get_anime_list(criteria, listrange, hideRated, user_id)

    # ___Clean up___

    def clearLogs(self):
        for f in os.listdir(self.logsPath):
            path = os.path.join(self.logsPath, f)
            if path != self.logFile:
                os.remove(path)

    def clearCache(self):  # TODO
        if self.cache is None or len(self.cache) == 0:
            self.log("MAIN_STATE", "[ERROR] - Cache path is invalid!")
        cmd = 'del /F /S /Q "{}"'.format(self.cache)
        try:
            subprocess.run(cmd)
            shutil.rmtree(self.cache)
        except Exception as e:
            self.log("MAIN_STATE", "[ERROR] - Cannot delete cache:", e, "-", cmd)

    def clearDb(self):
        # ONLY FOR TESTING!!! DO NOT USE WITH PROD DB!
        try:
            self.database.close()
        except Exception as e:
            self.log("DB_ERROR", "Database already closed?")
        try:
            os.remove(self.dbPath)
        except PermissionError as e:
            self.log("DB_ERROR", "File is already used", e)
        else:
            shutil.rmtree(self.cache)
            self.database = self.getDatabase()
            self.reloadAll()

    def quit(self):
        """
        Quit application - now delegates to ApplicationController.
        Maintained for backward compatibility.
        """
        # Set legacy flags for backward compatibility
        self.stopSearch = True
        self.closing = True

        # Delegate to application controller
        self._application_controller.stop()

    # ___Utils___
    def mainloop_error_handler(self, exc, val, tb):
        if isinstance(val, TclError) and "application has been destroyed" in str(val):
            self.log(
                "MAIN_STATE",
                "[ERROR] - In tkinter mainloop: Application has been destroyed",
            )
        else:
            self.log(
                "MAIN_STATE",
                "[ERROR] - In tkinter mainloop:\n",
                "".join(
                    map(
                        lambda t: t.replace("  ", "    "),
                        (
                            traceback.format_exception(type(exc), val, tb)
                            if exc is not None
                            else ["Unknown error"]
                        ),
                    )
                ),
            )

        if isinstance(
            val, sqlite3.ProgrammingError
        ) and "SQLite objects created in a thread can only be used in that same thread" in str(
            val
        ):
            self.quit()
            self.startup()

    def reloadAll(self):
        self.log("MAIN_STATE", "Reloading")
        self.stopSearch = True
        self.closing = True
        try:
            if self.initWindow is not None:
                self.initWindow.destroy()
        except Exception:
            pass
        self.initWindow = None

        self.drawLoadingWindow()
    
        self.database = self.getDatabase()
        if not self.database.is_initialized():
            self.checkSettings()
            self.reloadAll()
            return
    
        if self.fm is None:
            self.getFileManager()
    
        processes = self.updateAllProgression()
        try:
            length = next(processes)
            if not isinstance(length, int):
                length = 0  # Fallback if something went wrong
        except StopIteration:
            length = 0

        self.start = time.time()
        loadStart = 0
        for i, item in enumerate(processes):
            if isinstance(item, tuple) and len(item) == 2:
                thread, text = item
            else:
                # Skip invalid items
                continue
            try:
                if hasattr(self, "loadLabel"):
                    self.loadLabel["text"] = text
            except Exception:
                if (
                    self.loadingWindow is not None
                    and not self.loadingWindow.winfo_exists()
                ):
                    break
            if length > 0:
                loadStop = (i + 1) / length * 100
            else:
                loadStop = 100
            while thread.is_alive():
                time.sleep(1 / 60)
                loadStart += (loadStop - loadStart) / max(100 - loadStop, 2)
                try:
                    if hasattr(self, "loadProgress"):
                        self.loadProgress["value"] = loadStart
                except Exception:
                    if self.closing or (
                        self.loadingWindow is not None
                        and not self.loadingWindow.winfo_exists()
                    ):
                        break

        try:
            if self.loadingWindow is not None:
                self.loadingWindow.destroy()
            # self.quit()
        except Exception:
            pass
        try:
            self.log(
                "TIME",
                "Reload time:".ljust(25),
                round(time.time() - self.start, 2),
                "sec",
            )
        except AttributeError:
            pass
        # self.startup()
        self.closing = False
    
        # self.player = self.media_players[self.player_name]

        for player_name in self.players_order:
            if player_name in self.media_players:
                self.player = self.media_players[player_name]
                break
        else:
            # No player found
            self.player = None
            self.log("MAIN_STATE", "[ERROR] - No media player found!")

        # self.last_broadcasts = self.getBroadcast()

        # self.RPC_stop()
        DiscordPresence.__init__(self)
        self.RPC_menu()

        if not self.remote:
            self.drawInitWindow()

    def view(self, id):
        index = "indexList"
        # keys = self.database.keys(table="indexList")
        ids = self.database.sql(
            "SELECT * FROM indexList WHERE id=?", (id,), to_dict=True
        )[0]
        # ids = dict(zip(keys, ids))
        ids.pop("id")
        for api_key, id in ids.items():
            if id is not None and api_key in self.websitesViewUrls.keys():
                url = self.websitesViewUrls[api_key].format(id)
                threading.Thread(
                    target=webbrowser.open, args=(url,), daemon=True
                ).start()

    def loading(self, n=0, after=False):
        if self.stopSearch:
            if hasattr(self, "loadCanvas"):
                self.loadCanvas.delete(ALL)
            self.timer_id = None
            return
        elif self.timer_id is None or after:
            if hasattr(self, "giflist") and len(self.giflist) > 0:
                n = n % len(self.giflist)
                gif = self.giflist[n % len(self.giflist)]
                if hasattr(self, "loadCanvas"):
                    self.loadCanvas.delete(ALL)
                    self.loadCanvas.create_image(
                        gif.width() // 2, gif.height() // 2, image=gif
                    )
        if self.timer_id is not None and self.initWindow is not None:
            self.initWindow.after_cancel(self.timer_id)
        if self.initWindow is not None:
            self.timer_id = self.initWindow.after(
                30, self.loading, n + 1, True
            )  # TODO - Use a timer instead of n

    # ___Networking___
    def downloadFile(self, id, url=None, hash=None, download=True, user_id=None):
        """
        Download file - now delegates to DownloadManager component.
        Maintained for backward compatibility.
        """
        import warnings
        warnings.warn("Manager.downloadFile() is deprecated. Use DownloadManager.download_file() instead.",
                     DeprecationWarning, stacklevel=2)

        return self._download_manager.download_file(id, url, hash, user_id)

    def redownload(self, id):
        try:
            torrents = self.getTorrents(id)

            for torrent in torrents:
                self.downloadFile(id, url=torrent.to_magnet())

            if len(torrents) > 0:
                self.log("NETWORK", "Redownloaded {} torrents".format(len(torrents)))
            else:
                self.log("NETWORK", "No torrents to download!".format(len(torrents)))

        except torrent_managers.TorrentException as e:
            self.log("NETWORK", f"[ERROR] - {str(e)}")

    def search_torrent(self, id, parent=None):
        def callback(var, id):
            text = var.get()
            if self.textPopupWindow is not None:
                self.textPopupWindow.exit()

            web_reg = re.compile(
                r"^(http(s)?:\/\/.)?(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)$"
            )
            mag_reg = re.compile(r"^magnet:\?xt=urn:\S+$")
            if re.match(web_reg, text):
                # Web url
                self.downloadFile(id, url=text)
            elif re.match(mag_reg, text):
                # Magnet url
                self.downloadFile(id, url=text)
            else:
                # Torrent title
                self.addSearchTerms(id, text)
                fetcher = search_engines.search([text])
                self.drawDdlWindow(id, fetcher, parent=self.torrentFilesWindow)

        self.drawTextPopupWindow(
            parent or self.root,
            "Search torrents with name:",
            lambda var, id=id: callback(var, id),
            fentype="TEXT",
        )

    def bluetoothConnect(self):
        pass
        # TODO -> En fait c'est chiant

    def checkServer(self):
        if threading.main_thread() == threading.current_thread():
            threading.Thread(target=self.checkServer, daemon=True).start()
            return
        if self.enableServer:
            self.server = mobile_server.startServer(  # type: ignore
                self.hostName, self.serverPort, self
            )
        elif self.server is not None:
            mobile_server.stopServer(self.server, self)  # type: ignore
            self.server = None


# if __name__ == '__main__':
# 	multiprocessing.freeze_support()
# 	p = multiprocessing.current_process()
# 	if p.name == 'MainProcess':
# 		m = Manager()
