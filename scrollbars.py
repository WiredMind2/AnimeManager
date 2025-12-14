import tkinter as tk
from tkinter import (ALL, BOTH, BOTTOM, END, FLAT, GROOVE, HORIZONTAL, LEFT,
                      NE, NW, RAISED, RIDGE, RIGHT, SE, SOLID, SUNKEN, SW, TOP,
                      VERTICAL, Button, Canvas, Checkbutton, E, Entry, Frame,
                      Label, N, OptionMenu, S, Scrollbar, Toplevel, W, X, Y,
                      font, ttk)

from PIL import Image, ImageDraw, ImageTk

try:
    from .general_utils import parse_args, dict_merge
except ImportError:
    from general_utils import parse_args, dict_merge


class CustomScrollbar(Frame):
    def __init__(self, parent, orient="V", **kwargs):
        self.root = parent
        if orient in {"V", "H", "v", "h", "vertical", "horizontal"}:
            self.orient = orient[0].upper()
        else:
            raise ValueError("Orient must be either 'V' or 'H'.")

        self.padding = 5
        self.thickness = 30
        self.fg = "#000000"
        self.bg = "#FFFFFF"
        self.command = None
        self._config = {}

        super().__init__(self.root, bg="#00FF00")

        if self.orient == "V":
            self.frame = Canvas(
                self, width=self.thickness, bg=self.bg, bd=0, highlightthickness=0
            )
        else:
            self.frame = Canvas(
                self, height=self.thickness, bg=self.bg, bd=0, highlightthickness=0
            )

        self.frame.bind("<B1-Motion>", self.move_thumb)

        self.configure(**kwargs)
        self.frame.pack(fill="y" if self.orient == "V" else "x", expand=True)

    def configure(self, **kwargs):  # type: ignore
        self._config = dict_merge(self._config, kwargs)
        if "orient" in kwargs:
            orient = kwargs.pop("orient")
            if orient in {"V", "H", "v", "h", "vertical", "horizontal"}:
                orient = orient[0].upper()
            else:
                raise ValueError("Orient must be either 'V' or 'H'.")
            if orient != self.orient:
                self.destroy()
                self.__init__(self.root, **self._config)
        if "command" in kwargs:
            self.command = kwargs.pop("command")
        if "thickness" in kwargs:
            self.thickness = kwargs.pop("thickness")
            kwargs["width" if self.orient == "V" else "height"] = self.thickness
        if "padding" in kwargs:
            self.padding = kwargs.pop("padding")
        if "sb_fg" in kwargs:
            self.fg = kwargs.pop("sb_fg")
        elif "fg" in kwargs:
            self.fg = kwargs.pop("fg")
        if "bg" in kwargs:
            self.bg = kwargs["bg"]

        for k in set(kwargs.keys()):
            frame_config = self.frame.config()
            if frame_config is not None and k not in frame_config.keys():
                kwargs.pop(k)

        self.frame.configure(**kwargs)

    def config(self, **kwargs):
        return self.configure(**kwargs)

    def get(self):
        return self.start, self.stop

    def set(self, a, b):
        self.start, self.stop = float(a), float(b)
        try:
            self.draw_thumb(self.start, self.stop)
        except Exception:
            pass

    def draw_thumb(self, start, stop):
        width = self.frame.winfo_width()
        height = self.frame.winfo_height()
        if self.orient == "H":
            width, height = height, width

        self.frame.delete(ALL)
        scale = 10
        img_size = (
            max(1, (width - self.padding * 2)) * scale,
            max(1, int(((stop - start) * height - self.padding * 2)) * scale),
        )
        img_width = img_size[0]
        img_height = img_size[1]

        if img_height <= img_width:
            image = Image.new("RGB", (img_width, img_width), self.bg)
            draw = ImageDraw.Draw(image)
            draw.ellipse((0, 0, img_width, img_width), fill=self.fg, outline=None)
        else:
            image = Image.new("RGB", img_size, self.bg)
            draw = ImageDraw.Draw(image)
            draw.ellipse((0, 0, img_width, img_width), fill=self.fg, outline=None)
            draw.rectangle(
                (0, img_width / 2, img_width, img_height - img_width / 2),
                fill=self.fg,
                outline=None,
            )
            draw.ellipse(
                (0, img_height - img_width - 1, img_width, img_height - 1),
                fill=self.fg,
                outline=None,
            )

        self.thumb = image.resize(
            (max(1, img_width // scale), max(1, max(img_height, img_width) // scale)),
            Image.Resampling.LANCZOS,
        )
        if self.orient == "H":
            self.thumb = self.thumb.rotate(90, expand=True)
        thumb_img = ImageTk.PhotoImage(self.thumb, master=self.frame)

        pos = start * (height - self.padding * 2) + self.padding
        pos = min(pos, height - self.padding * 2 - img_width // scale)
        if self.orient == "V":
            self.frame.create_image(self.padding, pos, image=thumb_img, anchor="nw")
        else:
            self.frame.create_image(pos, self.padding, image=thumb_img, anchor="nw")
        self.frame.image = thumb_img  # type: ignore  # Keep reference to prevent garbage collection

    def move_thumb(self, event):
        if self.orient == "V":
            fensize = self.frame.winfo_height()
            pos = event.y / fensize
        else:
            fensize = self.frame.winfo_width()
            pos = event.x / fensize

        if self.command is not None:
            self.command("moveto", str(pos))


class LoadingBar(Frame):
    def __init__(self, parent, valueGetter, radius, fg, bg, **kwargs):
        self.root = parent
        self.radius = radius
        self.fg = fg
        self.bg = bg
        self.valueGetter = valueGetter

        super().__init__(self.root, height=self.radius * 2, **kwargs)
        self.configure(bg=self.bg)
        self.grid_columnconfigure(0, weight=1)

        self.main = Frame(self, bg=bg, width=500, height=self.radius * 2)
        self.main.pack(fill="both", expand=True)
        self.wrapper = Frame(self.main, bg=bg)
        self.wrapper.place(anchor="nw", relheight=1, relwidth=valueGetter())
        self.wrapper.grid_columnconfigure(1, weight=1)

        left = Canvas(
            self.wrapper,
            highlightthickness=0,
            height=self.radius * 2,
            width=self.radius,
            bg=bg,
            **kwargs,
        )
        left.create_oval(
            0, 0, self.radius * 2, self.radius * 2, fill=self.fg, outline=""
        )
        left.grid(row=0, column=0, sticky="nsw")

        bar = Frame(self.wrapper, bg=fg)
        bar.grid(row=0, column=1, sticky="nsew")

        right = Canvas(
            self.wrapper,
            highlightthickness=0,
            height=self.radius * 2,
            width=self.radius,
            bg=bg,
            **kwargs,
        )
        right.create_oval(
            -self.radius, 0, self.radius, self.radius * 2, fill=self.fg, outline=""
        )
        right.grid(row=0, column=2, sticky="nse")

        self.updateSize()

    def updateSize(self, e=None):
        self.wrapper.place_forget()
        value = self.valueGetter()
        self.wrapper.place(anchor="nw", relheight=1, relwidth=value)
        self.after(500, self.updateSize)
        self.root.focus_force()