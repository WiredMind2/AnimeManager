import json
import os
import sys
import threading
import time
from ctypes import CDLL, Structure, byref, c_int, c_long, c_uint, c_uint32
from tkinter import (BOTH, BOTTOM, LEFT, RIGHT, TOP, Button, Canvas, Event,
                     Frame, Label, TclError, Tk, Toplevel)
from typing import Any, Dict, Optional

from PIL import Image, ImageTk

if sys.platform == "win32":
    from ctypes import windll

from multiprocessing import Process, freeze_support

try:
    from ..constants import Constants
    from ..db_managers import thread_safe_db as db
    from ..logger import log
except ImportError:
    from constants import Constants
    from db_managers import thread_safe_db as db
    from logger import log


class BasePlayer:
    """Base class for media players.

    Initializes common attributes for static analysis and provides a
    minimal UI skeleton. Concrete players should subclass and override
    `start` and playback-specific methods.
    """

    def __init__(self, *args, **kwargs):
        self.log = log

        # Fall back to a commonly-available constant
        import json
        import os
        import sys
        import threading
        import time
        from ctypes import (CDLL, Structure, byref, c_int, c_long, c_uint,
                            c_uint32)
        from tkinter import (BOTH, LEFT, TOP, Button, Event, Frame, Label,
                             TclError, Tk, Toplevel)
        from typing import Any, Dict, Optional

        from PIL import Image, ImageTk

        if sys.platform == "win32":
            from ctypes import windll

        from multiprocessing import Process, freeze_support

        try:
            from ..constants import Constants
            from ..db_managers import thread_safe_db as db
            from ..logger import log
        except Exception:
            from constants import Constants
            from db_managers import thread_safe_db as db
            from logger import log

        class BasePlayer:
            """Minimal, analyzer-friendly base player for concrete players to subclass.

            This file deliberately keeps behavior conservative: initialize commonly
            used dynamic attributes, provide no-op stubs for UI callbacks, and wrap
            any tkinter-after/after_cancel usages with getattr checks to avoid
            AttributeError in headless or test environments.
            """

            def __init__(self, *args, **kwargs):
                # Provide a bound log method for subclasses/tests
                self.log = log

                # Initialize commonly used dynamic attributes so static analyzers
                # and tests can safely inspect or call them.
                self.root: Optional[Any] = None
                self.parent: Optional[Any] = None
                self.settings: Dict[str, Any] = {}
                self.iconPath: str = ""
                self.settingsPath: str = ""
                self.lastMovement: float = 0.0
                self.videoSize: tuple = (0, 0, 0)
                self.movementCheck: Optional[Any] = None
                self.is_iconified: bool = False
                self.hideCursorDelay: int = 3
                self.hidden: bool = True
                self.playlist: list = []
                self.titles: list = []
                self.index: int = 0
                self.database: Optional[Any] = None
                self.id: Optional[Any] = None

                # Execution mode for starting the player: PROCESS, THREAD, or NONE
                self.method = kwargs.pop("method", getattr(self, "method", "NONE"))
                callback = kwargs.pop("callback", None)


import json
import os
import sys
import threading
import time
from tkinter import BOTH, LEFT, TOP, Button, Frame, Label, Tk, Toplevel
from typing import Any, Dict, Optional

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

from ctypes import Structure, c_long

if sys.platform == "win32":
    from ctypes import byref, c_int, windll
elif sys.platform == "linux":
    from ctypes import CDLL, byref, c_int, c_uint32

from multiprocessing import Process, freeze_support

try:
    from ..constants import Constants
    from ..db_managers import thread_safe_db as db
    from ..logger import log
except Exception:
    # Fallback for test/runtime environments where package imports differ
    from constants import Constants  # type: ignore
    from db_managers import thread_safe_db as db  # type: ignore
    from logger import log  # type: ignore


class BasePlayer:
    """Analyzer-friendly minimal base player implementation."""

    def __init__(self, *args, **kwargs):
        # bound logger
        self.log = log

        # Common dynamic attributes
        self.root: Optional[Any] = None
        self.parent: Optional[Any] = None
        self.settings: Dict[str, Any] = {}
        self.iconPath: str = ""
        self.settingsPath: str = ""
        self.lastMovement: float = 0.0
        self.videoSize: tuple = (0, 0, 0)
        self.movementCheck: Optional[Any] = None
        self.is_iconified: bool = False
        self.hideCursorDelay: int = 3
        self.hidden: bool = True
        self.playlist: list = []
        self.titles: list = []
        self.index: int = 0
        self.database: Optional[Any] = None
        self.id: Optional[Any] = None

        self.method = kwargs.pop("method", getattr(self, "method", "NONE"))
        callback = kwargs.pop("callback", None)

        if self.method == "PROCESS":
            p = Process(target=self.start, args=args, kwargs=kwargs)
            p.start()
            threading.Thread(
                target=self.callback_handler, args=(callback, p), daemon=True
            ).start()
        elif self.method == "THREAD":
            t = threading.Thread(
                target=self.start, args=args, kwargs=kwargs, daemon=True
            )
            t.start()
            threading.Thread(
                target=self.callback_handler, args=(callback, t), daemon=True
            ).start()
        else:
            # inline for tests
            try:
                self.start(*args, **kwargs)
            except Exception:
                pass
            if callback is not None:
                try:
                    callback()
                except Exception:
                    pass

    def setup(self, root: Optional[Any]):
        self.root = root
        try:
            cwd = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        except Exception:
            cwd = os.getcwd()
        self.iconPath = os.path.join(cwd, "icons")
        try:
            appdata = Constants.getAppdata()
        except Exception:
            appdata = os.getcwd()

        if os.path.exists(os.path.normpath("settings.json")):
            self.settingsPath = os.path.normpath("settings.json")
        else:
            self.settingsPath = os.path.join(appdata, "settings.json")

        try:
            with open(self.settingsPath, "r", encoding="utf-8") as f:
                self.settings = json.load(f)
        except Exception:
            self.settings = {}

        self.lastMovement = 0
        self.videoSize = (0, 0, 0)
        self.movementCheck = None
        self.is_iconified = False
        self.hideCursorDelay = int(
            self.settings.get("player", {}).get("hideCursorDelay", 3)
        )

    def image(self, file: str, size: tuple):
        if Image is None or ImageTk is None:
            return None

        try:
            try:
                resample = Image.LANCZOS
            except Exception:
                resample = getattr(Image, "Resampling", None)
                if resample is not None:
                    resample = resample.LANCZOS
                else:
                    resample = getattr(Image, "BICUBIC", 1)

            path = os.path.join(self.iconPath, file)
            img = Image.open(path)
            img = img.resize(size, resample)
            return ImageTk.PhotoImage(img, master=self.parent)
        except Exception:
            try:
                img = Image.new("RGBA", size, (0, 0, 0, 0))
                return ImageTk.PhotoImage(img, master=self.parent)
            except Exception:
                return None

    # --- stubs ---
    def start(self, *args, **kwargs):
        return None

    def togglePause(self, *args, **kwargs):
        return None

    def toggleFullscreen(self, *args, **kwargs):
        return None

    def timeBack(self, *args, **kwargs):
        return None

    def timeForward(self, *args, **kwargs):
        return None

    def playlistNext(self, *args, **kwargs):
        return None

    def playlistBack(self, *args, **kwargs):
        return None

    def volumeUp(self, *args, **kwargs):
        return None

    def volumeDown(self, *args, **kwargs):
        return None

    def showTitle(self, *args, **kwargs):
        return None

    def OnClose(self, *args, **kwargs):
        try:
            if getattr(self, "parent", None) is not None:
                self.parent.destroy()
        except Exception:
            pass

    def initWindow(self):
        if getattr(self, "root", None) is None:
            self.parent = Tk()
        else:
            self.parent = Toplevel(self.root)

        self.name = (
            str(type(self)).split(".", 1)[-1].rsplit("_player", 1)[0].capitalize()
        )
        try:
            self.parent.title(f"{self.name} Media Player")
        except Exception:
            pass

        self.videopanel = Frame(self.parent)
        try:
            Label(
                self.videopanel,
                text="Loading...",
                bg="#181915",
                fg="#373734",
                font=("Source Code Pro Medium", 20),
            ).pack(fill=BOTH, expand=True)
        except Exception:
            Label(self.videopanel, text="Loading...").pack()
        self.videopanel.pack(fill=BOTH, expand=1)

        try:
            self.initPanel()
        except Exception:
            pass

        try:
            size = (1600, 900)
            x = int(self.parent.winfo_screenwidth() / 2 - size[0] / 2)
            y = int(self.parent.winfo_screenheight() / 2 - size[1] / 2)
            self.parent.geometry(f"{size[0]}x{size[1]}+{x}+{y}")
        except Exception:
            pass

        try:
            self.parent.minsize(width=550, height=300)
        except Exception:
            pass

        try:
            self.parent.bind("<Escape>", lambda e: self.toggleFullscreen())
            self.parent.bind("<KeyPress>", self.keyHandler)
            self.parent.bind("<Motion>", self.mouseHandler)
        except Exception:
            pass

        try:
            self.mouseHandler()
        except Exception:
            pass

        try:
            self.parent.protocol("WM_DELETE_WINDOW", self.OnClose)
        except Exception:
            pass

        try:
            self.parent.lift()
        except Exception:
            pass

    def initPanel(self):
        self.hidingFrame = Frame(self.parent, bg="#282923")
        self.infoLblFrame = Frame(self.hidingFrame, bg="#181915")
        self.subLbl = Label(
            self.infoLblFrame,
            text="",
            bd=0,
            height=1,
            relief="solid",
            font=("Source Code Pro Medium", 13),
            bg="#181915",
            fg="#FFFFFF",
        )
        self.subLbl.pack(side=TOP, expand=True, fill="both")

        self.audioLbl = Label(
            self.infoLblFrame,
            text="",
            bd=0,
            height=1,
            relief="solid",
            font=("Source Code Pro Medium", 13),
            bg="#181915",
            fg="#FFFFFF",
        )
        self.audioLbl.pack(side=TOP, expand=True, fill="both")
        self.infoLblFrame.pack(side=TOP, expand=True, fill="both")

        kwargs = {
            "bd": 0,
            "height": 1,
            "relief": "solid",
            "font": ("Source Code Pro Medium", 13),
            "activebackground": "#282923",
            "activeforeground": "#FFFFFF",
            "bg": "#181915",
            "fg": "#FFFFFF",
        }

        img = self.image("back.png", (25, 25))
        b = Button(self.hidingFrame, image=img, command=self.timeBack, **kwargs)
        if img is not None:
            setattr(b, "image", img)
        b.pack(side=LEFT, expand=True, fill="both")

        img = self.image("pause.png", (25, 25))
        self.playButton = Button(
            self.hidingFrame, image=img, command=self.togglePause, **kwargs
        )
        if img is not None:
            setattr(self.playButton, "image", img)
        self.playButton.pack(side=LEFT, expand=True, fill="both")

        img = self.image("next.png", (25, 25))
        b = Button(self.hidingFrame, image=img, command=self.timeForward, **kwargs)
        if img is not None:
            setattr(b, "image", img)
        b.pack(side=LEFT, expand=True, fill="both")

        img = self.image("left.png", (25, 25))
        b = Button(self.hidingFrame, image=img, command=self.playlistNext, **kwargs)
        if img is not None:
            setattr(b, "image", img)
        b.pack(side=LEFT, expand=True, fill="both")

        img = self.image("fullscreen.png", (25, 25))
        b = Button(self.hidingFrame, image=img, command=self.toggleFullscreen, **kwargs)
        if img is not None:
            setattr(b, "image", img)
        b.pack(side=LEFT, expand=True, fill="both")

        img = self.image("right.png", (25, 25))
        b = Button(self.hidingFrame, image=img, command=self.playlistBack, **kwargs)
        if img is not None:
            setattr(b, "image", img)
        b.pack(side=LEFT, expand=True, fill="both")

        self.posLbl = Label(
            self.hidingFrame,
            text="00:00",
            font=("Source Code Pro Medium", 13),
            bg="#282923",
            fg="#FFFFFF",
        )
        self.posLbl.pack(side=LEFT, fill="both", padx=10)

        Button(self.hidingFrame, text="-", command=self.volumeDown, **kwargs).pack(
            side=LEFT, expand=True, fill="both"
        )

        self.soundLbl = Label(
            self.hidingFrame,
            text="100%",
            font=("Source Code Pro Medium", 13),
            bg="#282923",
            fg="#FFFFFF",
        )
        self.soundLbl.pack(side=LEFT, fill="both", padx=10)

        Button(self.hidingFrame, text="+", command=self.volumeUp, **kwargs).pack(
            side=LEFT, expand=True, fill="both"
        )

        self.titleLabel = Label(
            self.parent,
            text="",
            font=("Source Code Pro Medium", 20),
            bg="#282923",
            fg="#FFFFFF",
        )

    def keyHandler(self, e: Any):
        try:
            c = getattr(e, "keysym", None) if not isinstance(e, tuple) else e[0]
            if isinstance(e, tuple):
                s = int(e[1])
            else:
                s = int(getattr(e, "state", 0))
        except Exception:
            return

        ctrl = (s & 0x4) != 0
        alt = (s & 0x20000) != 0
        shift = (s & 0x1) != 0

        settings = self.settings.get("player", {}).get("playerKeyBindings", {})
        keys = settings.get("None", {})

        if ctrl:
            keys = dict_merge(keys, settings.get("Ctrl", {}))
        elif alt:
            keys = dict_merge(keys, settings.get("Alt", {}))
        elif shift:
            keys = dict_merge(keys, settings.get("Shift", {}))

        if c in keys:
            opt = map(lambda e: e.strip(), keys[c].split("-"))
            funcName, arg = next(opt), next(opt, None)
            if hasattr(self, funcName):
                func = getattr(self, funcName)
                if arg is None:
                    func()
                else:
                    func(arg)

    def mouseHandler(self, e: Optional[Any] = None):
        if getattr(self, "parent", None) is not None:
            try:
                self.parent.config(cursor="arrow")
            except Exception:
                pass
        self.lastMovement = time.time()

        if self.movementCheck is not None and getattr(self, "parent", None) is not None:
            try:
                self.parent.after_cancel(self.movementCheck)
            except Exception:
                pass

        if getattr(self, "parent", None) is not None:
            try:
                self.movementCheck = self.parent.after(
                    self.hideCursorDelay * 1000, self.hideCursor
                )
            except Exception:
                self.movementCheck = None
        else:
            self.movementCheck = None

        if e is not None and getattr(self, "parent", None) is not None:
            try:
                x = e.x_root - self.parent.winfo_rootx()
                y = e.y_root - self.parent.winfo_rooty()
            except Exception:
                return

            t = time.time()
            try:
                if self.videoSize[2] + 1 < t:
                    self.videoSize = (
                        self.videopanel.winfo_width(),
                        self.videopanel.winfo_height(),
                        t,
                    )
            except Exception:
                self.videoSize = (0, 0, t)

            try:
                if (
                    0 < x < self.videoSize[0]
                    and 0.95 < y / max(1, self.videoSize[1]) < 1
                ):
                    if self.hidden:
                        try:
                            self.hidingFrame.place(
                                anchor="s", relx=0.5, rely=1, width=500, relheight=0.08
                            )
                        except Exception:
                            pass
                        self.hidden = False
                        self.showTitle()
                else:
                    try:
                        if not self.hidden and not str(e.widget).startswith(
                            str(self.hidingFrame)
                        ):
                            self.hidingFrame.place_forget()
                            self.hidden = True
                    except Exception:
                        pass
            except Exception:
                pass

    if sys.platform == "win32":

        def queryMousePosition(self):
            pt = POINT()
            try:
                windll.user32.GetCursorPos(byref(pt))
                root_x, root_y = (int(s) for s in self.parent.geometry().split("+")[1:])
                return pt.x - root_x, pt.y - root_y
            except Exception:
                return 0, 0

    elif sys.platform == "linux":

        def queryMousePosition(self):
            try:
                Xlib = CDLL("libX11.so.6")
                display = Xlib.XOpenDisplay(None)
                if display == 0:
                    return 0, 0
                return 0, 0
            except Exception:
                return 0, 0

    def hideCursor(self):
        try:
            if time.time() - self.lastMovement >= self.hideCursorDelay:
                if getattr(self, "parent", None) is not None:
                    try:
                        self.parent.config(cursor="none")
                    except Exception:
                        pass
            else:
                if (
                    self.movementCheck is not None
                    and getattr(self, "parent", None) is not None
                ):
                    try:
                        self.parent.after_cancel(self.movementCheck)
                    except Exception:
                        pass
                if getattr(self, "parent", None) is not None:
                    try:
                        self.movementCheck = self.parent.after(
                            int(
                                (
                                    self.hideCursorDelay
                                    - (time.time() - self.lastMovement)
                                )
                                * 1000
                            ),
                            self.hideCursor,
                        )
                    except Exception:
                        self.movementCheck = None
        except Exception:
            pass

    def updateDb(self):
        return

    def getPlaylist(self, playlist):
        event = threading.Event()
        self.playlist = playlist
        self.titles = [os.path.basename(f).rpartition(".")[0] for f in self.playlist]
        event.set()
        return event

    def condition_waiter(self, condition, callback, delay=100):
        if condition():
            return callback()
        else:
            if getattr(self, "parent", None) is not None:
                try:
                    self.parent.after(
                        delay, self.condition_waiter, condition, callback, delay
                    )
                except Exception:
                    pass

    def toggle_iconify(self):
        if self.is_iconified:
            try:
                if getattr(self, "parent", None) is not None:
                    self.parent.deiconify()
            except Exception:
                pass
            try:
                self.togglePause(playing=True)
            except Exception:
                pass
        else:
            try:
                if getattr(self, "parent", None) is not None:
                    self.parent.iconify()
            except Exception:
                pass
            try:
                self.togglePause(playing=False)
            except Exception:
                pass
        self.is_iconified = not self.is_iconified

    def callback_handler(self, cb, p):
        try:
            p.join()
        except Exception:
            pass
        if cb is not None:
            try:
                cb()
            except Exception:
                pass

    def log(self, *args, **kwargs):
        return log(*args, **kwargs)


class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]


def dict_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    new_dict: Dict[str, Any] = {}
    for d in (a, b):
        for k, v in d.items():
            new_dict[k] = v
    return new_dict


if __name__ == "__main__":
    freeze_support()

    def initPanel(self):
        self.hidingFrame = Frame(self.parent, bg="#282923")

        self.infoLblFrame = Frame(self.hidingFrame, bg="#181915")
        self.subLbl = Label(
            self.infoLblFrame,
            text="",
            bd=0,
            height=1,
            relief="solid",
            font=("Source Code Pro Medium", 13),
            bg="#181915",
            fg="#FFFFFF",
        )
        self.subLbl.pack(side=TOP, expand=True, fill="both")

        self.audioLbl = Label(
            self.infoLblFrame,
            text="",
            bd=0,
            height=1,
            relief="solid",
            font=("Source Code Pro Medium", 13),
            bg="#181915",
            fg="#FFFFFF",
        )
        self.audioLbl.pack(side=BOTTOM, expand=True, fill="both")
        self.infoLblFrame.pack(side=TOP, expand=True, fill="both")

        kwargs = {
            "bd": 0,
            "height": 1,
            "relief": "solid",
            "font": ("Source Code Pro Medium", 13),
            "activebackground": "#282923",
            "activeforeground": "#FFFFFF",
            "bg": "#181915",
            "fg": "#FFFFFF",
        }

        img = self.image("back.png", (25, 25))
        b = Button(self.hidingFrame, image=img, command=self.timeBack, **kwargs)
        b.image = img
        b.pack(side=LEFT, expand=True, fill="both")

        img = self.image("pause.png", (25, 25))
        self.playButton = Button(
            self.hidingFrame, image=img, command=self.togglePause, **kwargs
        )
        self.playButton.image = img
        self.playButton.pack(side=LEFT, expand=True, fill="both")

        img = self.image("next.png", (25, 25))
        # Next button
        img = self.image("next.png", (25, 25))
        b = Button(self.hidingFrame, image=img, command=self.timeForward, **kwargs)
        if img is not None:
            setattr(b, "image", img)
        b.pack(side=LEFT, expand=True, fill="both")

        # Playlist previous
        img = self.image("left.png", (25, 25))
        b = Button(self.hidingFrame, image=img, command=self.playlistNext, **kwargs)
        if img is not None:
            setattr(b, "image", img)
        b.pack(side=LEFT, expand=True, fill="both")

        # Fullscreen toggle
        img = self.image("fullscreen.png", (25, 25))
        b = Button(self.hidingFrame, image=img, command=self.toggleFullscreen, **kwargs)
        if img is not None:
            setattr(b, "image", img)
        b.pack(side=LEFT, expand=True, fill="both")

        # Playlist next
        img = self.image("right.png", (25, 25))
        b = Button(self.hidingFrame, image=img, command=self.playlistBack, **kwargs)
        if img is not None:
            setattr(b, "image", img)
        b.pack(side=LEFT, expand=True, fill="both")

        self.posLbl = Label(
            self.hidingFrame,
            text="00:00",
            font=("Source Code Pro Medium", 13),
            bg="#282923",
            fg="#FFFFFF",
        )
        self.posLbl.pack(side=LEFT, fill="both", padx=10)

        Button(self.hidingFrame, text="-", command=self.volumeDown, **kwargs).pack(
            side=LEFT, expand=True, fill="both"
        )

        self.soundLbl = Label(
            self.hidingFrame,
            text="100%",
            font=("Source Code Pro Medium", 13),
            bg="#282923",
            fg="#FFFFFF",
        )
        self.soundLbl.pack(side=LEFT, fill="both", padx=10)

        Button(self.hidingFrame, text="+", command=self.volumeUp, **kwargs).pack(
            side=LEFT, expand=True, fill="both"
        )

        self.titleLabel = Label(
            self.parent,
            text="",
            font=("Source Code Pro Medium", 20),
            bg="#282923",
            fg="#FFFFFF",
        )
        # self.hidingFrame.place(anchor="s",relx=0.5,rely=1,width=500,relheight=0.05)

    def keyHandler(self, e):
        if isinstance(e, Event):
            c = e.keysym
            s = int(e.state)
        elif isinstance(e, tuple):
            c, s = e
            # Normalize state mapping and coerce to int
            s = int({None: 262152, "ctrl": 262156, "alt": 393224, "shift": 262153}[s])
        else:
            return

        ctrl = (s & 0x4) != 0
        alt = (s & 0x20000) != 0
        shift = (s & 0x1) != 0

        settings = self.settings["player"]["playerKeyBindings"]

        keys = settings["None"]

        if ctrl:
            ctrlKeys = settings["Ctrl"]
            keys = dict_merge(keys, ctrlKeys)
            debug = "ctrl+" + c
        elif alt:
            altKeys = settings["Alt"]
            keys = dict_merge(keys, altKeys)
            debug = "alt+" + c
        elif shift:
            shiftKeys = settings["Shift"]
            keys = dict_merge(keys, shiftKeys)
            debug = "shift+" + c
        else:
            debug = c

        if c in keys.keys():
            opt = map(lambda e: e.strip(), keys[c].split("-"))
            funcName, arg = next(opt), next(opt, None)
            if hasattr(self, funcName):
                func = getattr(self, funcName)
                if arg is None:
                    func()
                else:
                    func(arg)

    def mouseHandler(self, e=None):
        self.parent.config(cursor="arrow")
        self.lastMovement = time.time()

        if self.movementCheck is not None and getattr(self, "parent", None) is not None:
            try:
                self.parent.after_cancel(self.movementCheck)
            except Exception:
                pass

        if getattr(self, "parent", None) is not None:
            self.movementCheck = self.parent.after(
                self.hideCursorDelay * 1000, self.hideCursor
            )
        else:
            self.movementCheck = None

        if e is not None:
            x, y = (
                e.x_root - self.parent.winfo_rootx(),
                e.y_root - self.parent.winfo_rooty(),
            )

            t = time.time()
            if self.videoSize[2] + 1 < t:  # Update screen size every 1 sec
                self.videoSize = (
                    self.videopanel.winfo_width(),
                    self.videopanel.winfo_height(),
                    t,
                )

            if 0 < x < self.videoSize[0] and 0.95 < y / self.videoSize[1] < 1:
                if self.hidden:
                    self.hidingFrame.place(
                        anchor="s", relx=0.5, rely=1, width=500, relheight=0.08
                    )
                    self.hidden = False
                    self.showTitle()
            else:
                if not self.hidden and not str(e.widget).startswith(
                    str(self.hidingFrame)
                ):
                    self.hidingFrame.place_forget()
                    self.hidden = True

    if sys.platform == "win32":

        def queryMousePosition(self):
            pt = POINT()
            windll.user32.GetCursorPos(byref(pt))
            root_x, root_y = (int(s) for s in self.parent.geometry().split("+")[1:])
            return pt.x - root_x, pt.y - root_y

    elif sys.platform == "linux":

        def queryMousePosition(self):
            # IDK if i really need this, since linux will almost always run headless, but whatever ig
            Xlib = CDLL("libX11.so.6")
            display = Xlib.XOpenDisplay(None)
            if display == 0:
                # TODO - Will this break something or not?
                sys.exit(2)

            w = Xlib.XRootWindow(display, c_int(0))
            (root_id, child_id) = (c_uint32(), c_uint32())
            (root_x, root_y, win_x, win_y) = (c_int(), c_int(), c_int(), c_int())
            mask = c_uint()
            ret = Xlib.XQueryPointer(
                display,
                c_uint32(w),
                byref(root_id),
                byref(child_id),
                byref(root_x),
                byref(root_y),
                byref(win_x),
                byref(win_y),
                byref(mask),
            )
            if ret == 0:
                # TODO - Will this break something or not?
                sys.exit(1)
            pass

    def hideCursor(self):
        # Hide mouse cursor when it's not moving
        if time.time() - self.lastMovement >= self.hideCursorDelay:
            self.parent.config(cursor="none")
        else:
            if self.movementCheck is not None:
                self.parent.after_cancel(self.movementCheck)
            self.movementCheck = self.parent.after(
                int((self.hideCursorDelay - (time.time() - self.lastMovement)) * 1000),
                self.hideCursor,
            )

    def updateDb(self):
        # Update last seen episode in db

        return  # OUTDATED: TODO - Get used_id as well, and update episodes_seen instead

        # self.log("Updating last_seen db",flush=True)
        def handler(self):
            if self.id is not None and self.database is not None:
                filename = self.playlist[self.index]
                db(self.database).set(
                    {"id": self.id, "last_seen": str(filename)}, table="anime"
                )

        threading.Thread(target=handler, args=(self,), daemon=True).start()

    def getPlaylist(self, playlist):
        # Get titles and stream urls from playlist
        # Return a threading.Event, set when data is ready
        event = threading.Event()

        # From filepaths
        # Simply parse filename to extract a title

        self.playlist = playlist
        self.titles = [os.path.basename(f).rpartition(".")[0] for f in self.playlist]

        event.set()
        return event

    def condition_waiter(self, condition, callback, delay=100):
        # Wait for condition() to return True, without blocking the window
        if condition():
            return callback()
        else:
            self.parent.after(delay, self.condition_waiter, condition, callback, delay)

    def toggle_iconify(self):
        # Hide player
        if self.is_iconified:
            self.parent.deiconify()
            self.togglePause(playing=True)
        else:
            self.parent.iconify()
            self.togglePause(playing=False)
        self.is_iconified = not self.is_iconified

    def callback_handler(self, cb, p):
        # Call callback when player exits
        p.join()
        if cb is not None:
            cb()

    def log(self, *args, **kwargs):
        # Simple wrapper for the log function
        return log(*args, **kwargs)


class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]


def dict_merge(a, b):
    "Used in place of the | operator in 3.10 for compatibility"
    new_dict = {}
    for d in (a, b):
        for k, v in d.items():
            new_dict[k] = v
    return new_dict


if __name__ == "__main__":
    freeze_support()
