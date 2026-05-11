import os
import threading
import time
import gc
import weakref
from functools import lru_cache
from tkinter import (BOTH, BOTTOM, END, HORIZONTAL, LEFT, NE, NW, RIGHT, SE,
                     SW, TOP, VERTICAL, Button, Canvas, E, Entry, Frame, Label,
                     N, OptionMenu, PhotoImage, S, Scrollbar, StringVar, Tk,
                     Toplevel, W, X, Y)

# Standardized import handling
try:
    # Try relative imports
    from .. import mobile_server
    from ..menu_components import EntryWithPlaceholder
    from ..anime_list_frame import AnimeListFrame
except ImportError:
    # Fallback to direct imports
    import mobile_server
    from menu_components import EntryWithPlaceholder
    from anime_list_frame import AnimeListFrame

from typing import Any, Callable, Dict, Optional
from PIL import Image, ImageTk


class ImageManager:
    """Optimized image manager with memory management and caching"""

    def __init__(self, max_pool_size=50):
        self.max_pool_size = max_pool_size
        self._image_cache = {}
        self._weak_refs = weakref.WeakSet()
        self._access_times = {}
        self._cache_stats = {'hits': 0, 'misses': 0, 'evictions': 0}

    @lru_cache(maxsize=100)
    def get_cached_image(self, path: str, size: Optional[tuple] = None) -> Optional[PhotoImage]:
        """Cache images with size-aware resizing"""
        key = (path, size)
        if key in self._image_cache:
            self._access_times[key] = time.time()
            self._cache_stats['hits'] += 1
            return self._image_cache[key]

        self._cache_stats['misses'] += 1
        try:
            if size:
                img = Image.open(path).resize(size, Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
            else:
                photo = ImageTk.PhotoImage(file=path)

            self._image_cache[key] = photo
            self._access_times[key] = time.time()
            self._cleanup_cache()
            return photo
        except Exception as e:
            print(f"Failed to load image {path}: {e}")
            return None

    def _cleanup_cache(self):
        """Remove oldest images when cache exceeds limit"""
        while len(self._image_cache) > self.max_pool_size:
            # Find oldest accessed image
            oldest_key = min(self._access_times.keys(), key=lambda k: self._access_times[k])
            del self._image_cache[oldest_key]
            del self._access_times[oldest_key]
            self._cache_stats['evictions'] += 1

    def cleanup_all(self):
        """Clear all cached images to prevent memory leaks"""
        self._image_cache.clear()
        self._access_times.clear()
        gc.collect()

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache performance statistics"""
        return self._cache_stats.copy()


class Main:
    # Type hints for attributes expected from Manager class
    menuOptions: Dict[str, Dict[str, Any]]
    filterOptions: Dict[str, Dict[str, Any]]
    colors: Dict[str, str]
    iconPath: str
    initWindow: Any
    searchTerms: Any
    root: Any
    mainWindowTitle: str
    mainWindowWidth: int
    mainWindowHeight: int
    loadCanvas: Any
    giflist: Any
    start: float
    image_manager: ImageManager

    # Methods expected from Manager class
    def getImage(self, path: str, size: Any = None) -> Any: ...
    def drawSeasonSelector(self) -> None: ...
    def quit(self) -> None: ...
    def log(self, category: str, message: str, *args: Any) -> None: ...
    def mainloop_error_handler(self, *args: Any) -> None: ...
    def search(self, event: Any = None) -> None: ...
    def late_startup(self) -> None: ...

    def _load_loading_gif_frames(self) -> list:
        """Load GIF frames with proper memory management"""
        gif_path = os.path.join(self.iconPath, "loading.gif")
        frames = []

        try:
            # Load GIF frames with proper cleanup management
            for i in range(30):  # Assuming 30 frames as in original code
                try:
                    frame = PhotoImage(file=gif_path, format=f"gif -index {i}")
                    frames.append(frame)
                except Exception as e:
                    print(f"Failed to load GIF frame {i}: {e}")
                    break
        except Exception as e:
            print(f"Failed to load loading GIF: {e}")
            return []

        return frames

    def _cleanup_gif_frame(self, weak_ref):
        """Cleanup callback for GIF frames"""
        # Remove from weak references when frame is garbage collected
        self.image_manager._weak_refs.discard(weak_ref)

    def _handle_quit(self):
        """Handle application quit with proper cleanup"""
        try:
            self.cleanup_resources()
        except Exception as e:
            self.log("ERROR", f"Error during cleanup: {e}")
        finally:
            self.quit()

    def drawInitWindow(self):
        # Initialize image manager for memory-efficient image handling
        if not hasattr(self, 'image_manager'):
            self.image_manager = ImageManager(max_pool_size=100)

        # Functions
        if True:

            def options(e):
                # Placeholder
                self.menuOptions[e]["command"]()

            def filter(e):
                self.searchTerms.set("")
                filter_name = self.filterOptions[e]["filter"]
                if filter_name == "SEASON":
                    self.drawSeasonSelector()
                else:
                    self.animeList.from_filter(filter_name)

            def reset_windows(e):
                for c in self.initWindow.winfo_children():
                    if isinstance(c, Toplevel):
                        c.destroy()

            def bringToTop(e):
                try:
                    self.initWindow.lift()
                    self.initWindow.focus_force()
                except Exception:
                    pass
                # self.initWindow.focus_force()
                self.root.iconify()

            def checkFocus(e):
                if e.widget.winfo_toplevel() == self.initWindow:
                    for c in self.initWindow.winfo_children():
                        if isinstance(c, Toplevel):
                            if hasattr(c, "topLevel"):
                                c.topLevel.focus_force()  # type: ignore
                            else:
                                c.focus_force()

            def start_move(event, window):
                window.x = event.x
                window.y = event.y

            def do_move(event, window):
                try:
                    deltax = event.x - window.x
                    deltay = event.y - window.y
                    x = window.winfo_x() + deltax
                    y = window.winfo_y() + deltay
                    window.geometry(f"+{x}+{y}")
                except AttributeError as e:
                    self.log("[ERROR]", "Error while moving main window")

        icon_path = os.path.join(self.iconPath, "app_icon", "icon.ico")

        if self.root is None:
            self.root = Tk()
            mainloop = True
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
            self.root.title(self.mainWindowTitle)
            # self.root.attributes('-alpha', 0.0)
            self.root.attributes("-topmost", 1)

            img_path = os.path.join(
                self.iconPath, "app_icon", "256x256", "icon_full.png"
            )
            img = self.getImage(img_path)
            can = Canvas(self.root, width=256, height=256)
            can.create_image((0, 0), image=img, anchor="nw")
            can.pack()

            self.root.protocol("WM_DELETE_WINDOW", self._handle_quit)
            self.root.focus_force()
            self.root.iconify()
            self.root.bind("<Map>", bringToTop)

            self.root.report_callback_exception = self.mainloop_error_handler
        else:
            mainloop = False

        if self.initWindow is None or not self.initWindow.winfo_exists():
            self.initWindow = Toplevel(self.root)
            self.initWindow.focus_force()
            self.initWindow.configure(bg=self.colors["Gray3"])
            self.initWindow.geometry(
                "{}x{}+100+100".format(self.mainWindowWidth, self.mainWindowHeight)
            )
            self.initWindow.overrideredirect(True)
            self.initWindow.title(self.mainWindowTitle)
            if os.path.exists(icon_path):
                self.initWindow.iconbitmap(icon_path)
            self.initWindow.bind("<FocusIn>", checkFocus)

            self.initWindow.resizable(False, True)
            dbFrame = Frame(self.initWindow, bg=self.colors["Gray2"], width=920)
            head = Frame(dbFrame, bg=self.colors["Gray2"])
            head.pack(fill="both")
            head.grid_columnconfigure(1, weight=1)

            # Top bar
            if True:
                droplistIcon = self.getImage(
                    os.path.join(self.iconPath, "menu.png"), (30, 30)
                )
                droplist = OptionMenu(
                    head, StringVar(), *self.menuOptions.keys(), command=options
                )
                droplist.configure(
                    indicatoron=False,
                    image=droplistIcon,
                    highlightthickness=0,
                    borderwidth=0,
                    activebackground=self.colors["Gray2"],
                    bg=self.colors["Gray2"],
                )
                droplist["menu"].configure(
                    bd=0,
                    borderwidth=0,
                    activeborderwidth=0,
                    font=("Source Code Pro Medium", 13),
                    activebackground=self.colors["Gray2"],
                    activeforeground=self.colors["White"],
                    bg=self.colors["Gray2"],
                    fg=self.colors["White"],
                )
                droplist.image = droplistIcon  # type: ignore
                droplist.grid(row=0, column=0, padx=15)

                for i, color in enumerate(
                    [c["color"] for c in self.menuOptions.values()]
                ):
                    droplist["menu"].entryconfig(i, foreground=self.colors[color])

                self.searchTerms = StringVar(self.initWindow, "")

                searchBar = EntryWithPlaceholder(
                    head,
                    placeholder="Search...",
                    textvariable=self.searchTerms,
                    highlightthickness=0,
                    borderwidth=0,
                    font=("Source Code Pro Medium", 13),
                    bg=self.colors["Gray2"],
                    fg=self.colors["White"],
                )
                searchBar.grid(row=0, column=1, sticky="nsew", pady=10)

                searchBar.bind(
                    "<ButtonPress-1>", lambda e: start_move(e, self.initWindow)
                )
                searchBar.bind("<B1-Motion>", lambda e: do_move(e, self.initWindow))
                # self.searchTerms.trace_add("write", self.search)
                searchBar.bind("<KeyRelease>", self.search)
                searchBar.bind("<Return>", self.search)
                # searchBar.bind("<Control-Return>", lambda e: self.search(force_search=True))

                # Use image manager for memory-efficient GIF loading
                self.giflist = self._load_loading_gif_frames()
                self.loadCanvas = Canvas(
                    head,
                    bg=self.colors["Gray2"],
                    highlightthickness=0,
                    width=56,
                    height=56,
                )
                self.loadCanvas.giflist = self.giflist  # type: ignore
                self.loadCanvas.grid(row=0, column=2)

                filterIcon = self.getImage(
                    os.path.join(self.iconPath, "filter.png"), (35, 35)
                )
                filter_menu = OptionMenu(
                    head, StringVar(), *self.filterOptions.keys(), command=filter
                )
                filter_menu.configure(
                    indicatoron=False,
                    image=filterIcon,
                    highlightthickness=0,
                    borderwidth=0,
                    activebackground=self.colors["Gray2"],
                    bg=self.colors["Gray2"],
                )
                filter_menu["menu"].configure(
                    bd=0,
                    borderwidth=0,
                    activeborderwidth=0,
                    font=("Source Code Pro Medium", 13),
                    activebackground=self.colors["Gray2"],
                    activeforeground=self.colors["White"],
                    bg=self.colors["Gray2"],
                    fg=self.colors["White"],
                )
                filter_menu.image = filterIcon  # type: ignore
                filter_menu.grid(row=0, column=3, padx=0)

                for i, color in enumerate(
                    [c["color"] for c in self.filterOptions.values()]
                ):
                    filter_menu["menu"].entryconfig(i, foreground=self.colors[color])

                closeIcon = self.getImage(
                    os.path.join(self.iconPath, "close.png"), (40, 40)
                )
                def close_button_handler():
                    self.log("UI_EVENT", "Close button clicked")
                    self.quit()

                closeButton = Button(
                    head,
                    image=closeIcon,
                    bd=0,
                    height=40,
                    relief="solid",
                    activebackground=self.colors["Gray2"],
                    bg=self.colors["Gray2"],
                    command=close_button_handler,
                )
                closeButton.closeIcon = closeIcon  # type: ignore
                closeButton.bind("<Button-3>", reset_windows)
                closeButton.grid(row=0, column=4, padx=10)

            self.animeList = AnimeListFrame(
                dbFrame,
                self,
                scrollbar=True,
                fg=self.colors["Gray3"],
                bg=self.colors["Gray2"],
                thickness=15,
                padding=4,
                width=900,
            )
            self.animeList.pack(fill="both", expand=True)

            Label(
                self.animeList,
                text="Loading...",
                bg=self.colors["Gray2"],
                fg=self.colors["Gray4"],
                font=("Source Code Pro Medium", 20),
            ).grid(row=0, column=0, columnspan=4, sticky="nsew")

            dbFrame.pack(fill="both", expand=True)
            for i in range(4):
                self.animeList.grid_columnconfigure(i, weight=1)

        self.log(
            "TIME",
            "Window created:".ljust(25),
            round(time.time() - self.start, 2),
            "sec",
        )

        self.root.after(1, self.late_startup)

        # Mainloop is now started by UIManager._handle_application_ui_ready

    def cleanup_resources(self):
        """Cleanup resources to prevent memory leaks"""
        try:
            # Cleanup image manager cache
            if hasattr(self, 'image_manager'):
                self.image_manager.cleanup_all()

            # Clear GIF frames
            if hasattr(self, 'giflist'):
                self.giflist.clear()

            # Force garbage collection
            gc.collect()

            self.log("CLEANUP", "Resources cleaned up successfully")
        except Exception as e:
            self.log("ERROR", f"Error during resource cleanup: {e}")
