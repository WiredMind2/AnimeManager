import tkinter as tk
from tkinter import (ALL, BOTH, BOTTOM, END, FLAT, GROOVE, HORIZONTAL, LEFT,
                      NE, NW, RAISED, RIDGE, RIGHT, SE, SOLID, SUNKEN, SW, TOP,
                      VERTICAL, Button, Canvas, Checkbutton, E, Entry, Frame,
                      Label, N, OptionMenu, S, Scrollbar, Toplevel, W, X, Y,
                      font, ttk)

from PIL import Image, ImageDraw, ImageTk

try:
    from .general_utils import parse_args
except ImportError:
    from general_utils import parse_args

try:
    from .scrollbars import CustomScrollbar
except ImportError:
    from scrollbars import CustomScrollbar

try:
    from .logger import log
except ImportError:
    from logger import log

# DropDownMenu imported lazily in getChild to avoid circular import

class RoundTopLevel(Frame):
    def __init__(
        self,
        parent,
        minsize=None,
        title="Title",
        radius=25,
        bd=2,
        fg="#FFFFFF",
        bg="#000000",
        **kwargs,
    ):
        self.parent = parent
        self.minFensize = minsize or (radius * 3, radius * 3)
        self.titleText = title
        self.radius = radius
        self.bd = bd
        self.fg = fg
        self.bg = bg
        self.windowX, self.windowY = None, None

        self.window = Toplevel(self.parent)
        self.window.overrideredirect(True)
        self.window.wm_attributes("-transparentcolor", "pink")
        self.window.geometry(
            "+{}+{}".format(50 + self.parent.winfo_x(), 50 + self.parent.winfo_y())
        )
        self.window.minsize(*self.minFensize)
        self.window.grid_columnconfigure(0, weight=1)

        container = self.getCorners(self.window)
        container_row = int(self.titleText is not None)

        super().__init__(container, bg=self.bg)
        # self.mainFrame = Frame(container,bg=self.bg)
        self.mainFrame = self
        # Store reference to top level for focus management
        self.window.topLevel = self  # type: ignore
        self.mainFrame.grid(row=container_row, column=0, sticky="nsew")
        self.mainFrame.grid_columnconfigure(0, weight=1)

        if self.titleText is not None:
            self.titleFrame = Frame(container, bg=self.bg)
            self.titleFrame.grid(row=0, column=0, pady=(0, self.radius))
            self.titleFrame.grid_columnconfigure(0, weight=1)

            self.titleLbl = Label(
                self.titleFrame,
                text=self.titleText,
                bg=self.bg,
                fg=self.fg,
                font=("Source Code Pro Medium", 18),
            )
            self.titleLbl.grid(row=0, column=0)

            self.titleLbl.bind("<ButtonPress-1>", self.start_move)
            self.titleLbl.bind("<B1-Motion>", self.do_move)
        else:
            self.titleLbl = None

        self.handles = [self.titleLbl]

        container.grid_rowconfigure(container_row, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.update_events()

    def get(self):
        return self.mainFrame.get()

    def getCorners(self, parent):
        corners = Frame(parent, bg=self.fg)
        mainFrame = None  # Initialize to avoid unbound variable
        for x in range(3):
            for y in range(3):
                if x == 1 or y == 1:
                    frame = Frame(corners, bg=self.bg)

                    padx = (self.bd if x == 0 else 0, self.bd if x == 2 else 0)
                    pady = (self.bd if y == 0 else 0, self.bd if y == 2 else 0)
                    frame.grid(column=x, row=y, sticky="nsew", padx=padx, pady=pady)
                    if x == y == 1:
                        mainFrame = frame
                else:
                    can = Canvas(
                        corners,
                        width=self.radius,
                        height=self.radius,
                        bg="pink",
                        highlightthickness=0,
                    )
                    can.grid(column=x, row=y, sticky="nsew")
                    width = self.radius * 2
                    posx = 0 if x == 0 else -self.radius
                    posy = 0 if y == 0 else -self.radius
                    can.create_oval(
                        posx, posy, posx + width, posy + width, fill=self.fg, outline=""
                    )
                    can.create_oval(
                        posx + self.bd,
                        posy + self.bd,
                        posx + width - self.bd,
                        posy + width - self.bd,
                        fill=self.bg,
                        outline="",
                    )
        corners.grid_rowconfigure(1, weight=1)
        corners.grid_columnconfigure(1, weight=1)
        corners.pack(expand=True, fill="both")

        assert mainFrame is not None  # Ensure mainFrame was set
        return mainFrame

    def getChild(self, w):
        # Lazy import to avoid circular import
        try:
            from menu_components import DropDownMenu
        except ImportError:
            DropDownMenu = None

        excluded_types = (Button, Checkbutton, Toplevel, OptionMenu, CustomScrollbar)
        if DropDownMenu is not None:
            excluded_types += (DropDownMenu,)

        out = []
        # ScrollableFrame
        if not isinstance(w, excluded_types):
            out.append(w)

        # RoundTopLevel, ScrollableFrame
        if isinstance(w, (Toplevel, Canvas, Frame)):
            try:
                for sub_w in w.winfo_children():
                    out += self.getChild(sub_w)
            except Exception:
                pass
        return out

    def clear(self):
        try:
            for w in self.mainFrame.winfo_children():
                if not isinstance(w, RoundTopLevel):
                    w.destroy()
        except Exception:
            pass

    def focus_force(self):
        self.window.lift()
        for c in self.mainFrame.winfo_children():
            if isinstance(c, Toplevel):
                if hasattr(c, "topLevel"):
                    c.topLevel.focus_force()  # type: ignore
                else:
                    c.focus_force()

    def exit(self, e=None):
        for c in self.mainFrame.winfo_children():
            if isinstance(c, Toplevel):
                if hasattr(c, "topLevel"):
                    c.topLevel.focus_force()  # type: ignore
                else:
                    c.focus_force()
                return
        self.window.destroy()
        self.parent.focus_force()

    def start_move(self, event):
        self.windowX = event.x
        self.windowY = event.y

    def do_move(self, event):
        if self.windowX is None or self.windowY is None:
            self.windowX = event.x
            self.windowY = event.y
        try:
            deltax = event.x - self.windowX
            deltay = event.y - self.windowY
            x = self.window.winfo_x() + deltax
            y = self.window.winfo_y() + deltay
            self.window.geometry(f"+{x}+{y}")
            for c in self.mainFrame.winfo_children():
                if isinstance(c, Toplevel):
                    if hasattr(c, "topLevel"):
                        c.topLevel.focus_force()  # type: ignore
                    else:
                        c.focus_force()
        except Exception as e:
            log("Error while moving window", e)

    def update_events(self):
        for handle in self.handles:
            try:
                if handle is not None:
                    handle.bind("<ButtonPress-1>", self.start_move)
                    handle.bind("<B1-Motion>", self.do_move)
            except Exception:
                pass

        children = self.getChild(self.window)
        for wid in children:
            if wid not in self.handles:
                wid.bind("<Button-1>", self.exit)


class ScrollableFrame(Frame):
    def __init__(self, root, axis="V", scrollbar=False, **kwargs):
        self.root = Frame(root)
        if axis not in ("H", "V"):
            raise TypeError("Axis must be either 'H' or 'V'")
        self.axis = axis  # Either "H" or "V"

        self.ARROW_SCROLL_SPEED = 1  # TODO - Put in constants?

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.canvas = Canvas(self.root, highlightthickness=0)
        self.canvas.configure(**parse_args(self.canvas, kwargs))
        self.canvas.grid(row=0, column=0, sticky="nsew")

        super().__init__(self.canvas)
        self.config(**parse_args(self, kwargs))
        frame_id = self.canvas.create_window((0, 0), window=self, anchor="nw")

        self.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        if axis == "V":
            self.canvas.bind(
                "<Configure>", lambda e: self.canvas.itemconfig(frame_id, width=e.width)
            )
        else:
            self.canvas.bind(
                "<Configure>",
                lambda e: self.canvas.itemconfig(frame_id, height=e.height),
            )

        if scrollbar:
            self.scrollbar = CustomScrollbar(self.root, **kwargs)
            if axis == "V":
                self.scrollbar.config(command=self.canvas.yview, orient="vertical")
                self.canvas.configure(yscrollcommand=self.scrollbar.set)
                self.scrollbar.grid(row=0, column=1, sticky="ns")
            else:
                self.scrollbar.config(command=self.canvas.xview, orient="horizontal")
                self.canvas.configure(xscrollcommand=self.scrollbar.set)
                self.scrollbar.grid(row=1, column=0, sticky="ew")
            self.root.grid_columnconfigure(0, weight=1)
            self.root.grid_rowconfigure(0, weight=1)

        self.update_scrollzone()

    def scroll(self, delta):
        if self.axis == "V":
            if self.winfo_height() > self.canvas.winfo_height():
                self.canvas.yview_scroll(int(-1 * (delta / 120)), "units")
        else:
            if self.winfo_width() > self.canvas.winfo_width():
                self.canvas.xview_scroll(int(-1 * (delta / 120)), "units")

    def pack(self, *args, **kwargs):
        # Placeholder
        self.root.pack(*args, **kwargs)

    def grid(self, *args, **kwargs):
        # Placeholder
        self.root.grid(*args, **kwargs)

    def place(self, *args, **kwargs):
        # Placeholder
        self.root.place(*args, **kwargs)

    def getChild(self, parent):
        out = []
        try:
            for w in parent.winfo_children():
                out.append(w)
                out += self.getChild(w)
        except Exception:
            pass
        return out

    def bbox(self, *args, **kwargs):
        return self.canvas.bbox(*args, **kwargs)

    def update_scrollzone(self, childs=None):
        if childs is None:
            childs = self.getChild(self.canvas)

        for w in childs:
            w.bind("<MouseWheel>", lambda e: self.scroll(e.delta))