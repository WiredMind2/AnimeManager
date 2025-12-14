# DO NOT REMOVE THIS WARNING, this file shouldn't be used anymore
raise DeprecationWarning("This module is deprecated, you should import the refactored version instead")

import bisect
import gc
import json
import os
import psutil
import queue
import re
import sys
import threading
import time
import tracemalloc
import weakref
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Union

try:
    from .classes import AnimeList, DefaultDict
except ImportError:
    from classes import AnimeList, DefaultDict

# from ctypes import windll, Structure, c_long, byref
try:
    from .logger import log
except ImportError:
    from logger import log

import tkinter as tk
from tkinter import (ALL, BOTH, BOTTOM, END, FLAT, GROOVE, HORIZONTAL, LEFT,
                     NE, NW, RAISED, RIDGE, RIGHT, SE, SOLID, SUNKEN, SW, TOP,
                     VERTICAL, Button, Canvas, Checkbutton, E, Entry, Frame,
                     Label, N, OptionMenu, S, Scrollbar, Toplevel, W, X, Y,
                     font, ttk)
from tkinter.messagebox import showwarning
from tkinter.simpledialog import Dialog

from PIL import Image, ImageDraw, ImageTk


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
        out = []
        # ScrollableFrame
        if not isinstance(
            w,
            (Button, Checkbutton, Toplevel, OptionMenu, DropDownMenu, CustomScrollbar),
        ):
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


class DropDownMenu(Button):
    def __init__(self, master, var, *values, **kwargs):
        super().__init__(master)
        self.menu = DropDown(self, var, *values, **kwargs)
        self.configure(**parse_args(self, kwargs))
        super().configure(text=var.get(), command=self.menu.show)

    def config(self, *args, **kwargs):
        return self.configure(*args, **kwargs)

    def configure(self, *args, **kwargs):
        if "command" in kwargs:
            cmd = kwargs.pop("command")
            self.menu.configure(command=cmd)

        if args:
            self.menu.configure(*args)

        return super().configure(**kwargs)


class DropDown(Toplevel):
    def __init__(
        self,
        master,
        var,
        *values,
        command=None,
        elem_per_row=20,
        scrollbar=False,
        **kwargs,
    ):
        self.master = master
        self.var = var
        self.values = list(values)
        self.command = command
        self.elem_per_row = elem_per_row
        self.scrollbar = scrollbar

        self.main_frame = None
        self.rows = []
        self.config_ = kwargs

        self.column_width = 100
        self.row_height = 35

        self.sep_bg = "#FFFFFF"
        self.fg = "#FFFFFF"
        self.bg = "#FF00FF"

        super().__init__(self.master)
        self.config(**parse_args(self, kwargs))
        self.overrideredirect(True)
        self.withdraw()
        self.bind("<FocusOut>", self.hide)

    def show(self):
        x, y = (
            self.master.winfo_rootx(),
            self.master.winfo_rooty() + self.master.winfo_height(),
        )
        sb_thickness = self.config_.get("thickness", 30)
        size_x, size_y = (
            self.master.winfo_width() * 2,
            min(20, len(self.values)) * self.row_height + sb_thickness,
        )
        if self.main_frame is not None:
            size_x = min(self.main_frame.winfo_width(), size_x)
        self.geometry("{}x{}+{}+{}".format(size_x, size_y, x, y))
        self.deiconify()
        self.focus_force()

    def hide(self, arg=None):
        self.withdraw()

    def config(self, *args, **kwargs):
        return self.configure(*args, **kwargs)

    def configure(self, *args, **kwargs):  # type: ignore
        if not args and not kwargs:
            return super().configure()

        if args:
            for val in args:
                if val not in self.values:
                    self.values.append(val)
            self.update_values()

        catch = ("command", "elem_per_row", "scrollbar")
        for key in catch:
            if key in kwargs:
                val = kwargs.pop(key)
                self.__dict__[key] = val

        self.config_ = dict_merge(self.config_, kwargs)

        return super().configure(**parse_args(self, self.config_))

    def root_configure(self, **kwargs):
        if "fg" in kwargs:
            self.fg = kwargs.pop("fg")
        if "bg" in kwargs:
            self.bg = kwargs.pop("bg")
        # kwargs['bg'] = self.fg
        super().configure(**kwargs)

    def entryconfig(self, i, **kwargs):
        self.rows[i].configure(**kwargs)

    def update_values(self):
        if self.main_frame is not None:
            self.main_frame.destroy()

        self.main_frame = ScrollableFrame(
            self, axis="H", scrollbar=self.scrollbar, **self.config_
        )
        self.main_frame.pack(expand=True, fill="both")

        columns = len(self.values) // self.elem_per_row + 1
        rows = min(self.elem_per_row, len(self.values))

        for i in range(columns):
            self.main_frame.grid_columnconfigure(i * 2, weight=1)
        for i in range(rows):
            self.main_frame.grid_rowconfigure(i, weight=1, minsize=self.row_height)

        self.rows = []  # TODO - Empty rows
        if len(self.values) == 0:
            row = Label(self.main_frame, text="No data!", anchor="w")
            row.config(**parse_args(row, self.config_))
            row.grid(row=0, column=0, sticky="new")
            self.rows.append(row)

        else:
            for i, val in enumerate(self.values):
                row = Button(
                    self.main_frame,
                    text=val,
                    command=self.handle_command(val),
                    anchor="w",
                )
                row.config(**parse_args(row, self.config_))
                row.grid(
                    row=i % self.elem_per_row,
                    column=i // self.elem_per_row * 2,
                    sticky="new",
                )
                self.rows.append(row)

            for i in range(columns - 1):
                sep = Frame(self.main_frame, bg=self.fg, width=2)
                sep.grid(
                    row=0,
                    column=i * 2 + 1,
                    rowspan=self.elem_per_row,
                    sticky="ns",
                    pady=10,
                )

        self.main_frame.update_scrollzone()

    def handle_command(self, val):
        def handler():
            self.var.set(val)
            if self.command is not None:
                self.command(val)

        return handler


class EntryWithPlaceholder(Entry):
    def __init__(self, master=None, placeholder="PLACEHOLDER", color="grey", **kwargs):
        super().__init__(master, **kwargs)

        self.placeholder = placeholder
        self.placeholder_color = kwargs.get("color", "gray")
        self.default_fg_color = self["fg"]

        self.bind("<FocusIn>", self.foc_in)
        self.bind("<FocusOut>", self.foc_out)

        self.put_placeholder()

    def put_placeholder(self):
        self.insert(0, self.placeholder)
        self["fg"] = self.placeholder_color

    def foc_in(self, *args):
        if self["fg"] == self.placeholder_color:
            self.delete("0", "end")
            self["fg"] = self.default_fg_color

    def foc_out(self, *args):
        if self.get() == "":
            self.put_placeholder()


class AnimeListFrame(ScrollableFrame):
    def __init__(self, root, parent, rows_per_page=50, **kwargs):
        self.root = root
        self.parent = parent
        self.animePerRow = self.parent.animePerRow
        self.animePerPage = self.parent.animePerPage
        self.log = self.parent.log

        self.list = []
        self.next_list = None
        self.blank_image = None
        self.list_id = 0

        # Virtual scrolling optimization
        self.virtual_scrolling = True
        self.visible_start = 0
        self.visible_end = rows_per_page
        self.item_height = 350  # Approximate height per anime item (image + text)
        self.visible_widgets = {}  # Cache for visible widgets
        self.widget_pool = []  # Pool of reusable widgets
        self.max_pool_size = 100

        super().__init__(self.root, **kwargs)

        # Bind scroll events for virtual scrolling
        if self.virtual_scrolling:
            self.canvas.bind("<MouseWheel>", self._on_scroll)
            self.canvas.bind("<Button-4>", self._on_scroll)  # Linux scroll up
            self.canvas.bind("<Button-5>", self._on_scroll)  # Linux scroll down

    def _get_list_length(self):
        """Safely get the length of the anime list"""
        try:
            if hasattr(self.list, 'list'):
                return len(self.list.list)
            elif hasattr(self.list, '__len__'):
                return len(self.list)
            else:
                # Convert to list to get length
                return len(list(self.list))
        except:
            return 0

    def _get_list_item(self, index):
        """Safely get an item from the anime list by index"""
        try:
            if hasattr(self.list, 'list'):
                # AnimeList has a .list attribute that's a deque
                list_items = list(self.list.list)
                return list_items[index] if index < len(list_items) else None
            elif hasattr(self.list, '__getitem__'):
                return self.list[index]
            else:
                # Convert to list and access
                list_items = list(self.list)
                return list_items[index] if index < len(list_items) else None
        except:
            return None

    def _on_scroll(self, event):
        """Handle scroll events for virtual scrolling"""
        if not self.virtual_scrolling or not self.list:
            return

        # Determine scroll direction and amount
        if event.delta > 0 or event.num == 4:  # Scroll up
            scroll_amount = -3  # Scroll up by 3 items
        else:  # Scroll down
            scroll_amount = 3   # Scroll down by 3 items

        # Calculate new visible range
        new_start = max(0, self.visible_start + scroll_amount)
        # Get list length safely
        list_length = self._get_list_length()

        max_start = max(0, list_length - self.animePerPage)
        new_start = min(new_start, max_start)

        if new_start != self.visible_start:
            self.visible_start = new_start
            self.visible_end = min(new_start + self.animePerPage, list_length)
            self._update_visible_items()

    def _update_visible_items(self):
        """Update which items are visible in the virtual scroll area"""
        if not self.virtual_scrolling:
            return

        # Clear current visible widgets
        for widget_info in self.visible_widgets.values():
            widget_info['canvas'].grid_remove()
            widget_info['label'].grid_remove()
            # Return to pool
            self._return_widget_to_pool(widget_info)

        self.visible_widgets.clear()

        # Create widgets for visible items
        que = queue.Queue()
        self.parent.getElemImages(que)

        list_length = self._get_list_length()

        for i in range(self.visible_start, min(self.visible_end, list_length)):
            anime = self._get_list_item(i)
            if anime:
                widget_info = self._get_widget_from_pool()
                self._create_virtual_elem(i, anime, widget_info, que)
                self.visible_widgets[i] = widget_info

        # Update canvas scroll region
        total_height = (list_length // self.animePerRow + 1) * self.item_height
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), total_height))

    def _get_widget_from_pool(self):
        """Get a widget from the pool or create a new one"""
        if self.widget_pool:
            return self.widget_pool.pop()
        else:
            # Create new widget
            canvas = Canvas(
                self,
                width=225,
                height=310,
                highlightthickness=0,
                bg=self.parent.colors["Gray3"],
            )
            label = Label(
                self,
                text="",
                bg=self.parent.colors["Gray2"],
                fg=self.parent.colors["White"],
                font=("Source Code Pro Medium", 13),
                bd=0,
                wraplength=220,
            )
            return {'canvas': canvas, 'label': label}

    def _return_widget_to_pool(self, widget_info):
        """Return widget to pool for reuse"""
        if len(self.widget_pool) < self.max_pool_size:
            # Clear widget state
            widget_info['canvas'].delete("all")
            widget_info['label'].config(text="")
            self.widget_pool.append(widget_info)

    def _create_virtual_elem(self, index, anime, widget_info, queue):
        """Create a virtual scrolling element"""
        canvas = widget_info['canvas']
        label = widget_info['label']

        # Calculate grid position
        row = (index // self.animePerRow) * 2  # *2 because of image + label rows
        col = index % self.animePerRow

        # Position widgets
        canvas.grid(column=col, row=row, padx=5, pady=5)
        label.grid(column=col, row=row + 1, padx=5, pady=5)

        # Configure canvas
        canvas.delete("all")  # Clear previous content
        if self.blank_image is None:
            self.blank_image = self.parent.getImage(None, (225, 310))
        canvas.create_image(0, 0, image=self.blank_image, anchor="nw")
        canvas.image = self.blank_image  # Keep reference

        # Bind events
        canvas.bind("<Button-1>", lambda e, id=anime.id: self.parent.drawOptionsWindow(id))
        canvas.bind("<Button-3>", lambda e, id=anime.id: self.parent.view(id))

        # Configure label
        title = anime.title or "Unknown Title"
        if len(title) > 35:
            title = title[:35] + "..."

        if anime.like == 1:
            title += " ❤"

        label.config(
            text=title,
            fg=self.parent.colors[self.parent.tagcolors.get(anime.tag, "White")]
        )
        label.name = str(anime.id)

        # Load image asynchronously
        filename = os.path.join(self.parent.cache, str(anime.id) + ".jpg")
        pics = self.parent.getAnimePictures(anime.id)
        if pics:
            url = pics[0]["url"]
            queue.put((filename, url, canvas))

    def find(self, limit=1, **kwargs):
        c = 0
        for anime in self.list:
            if all(anime[k] == v for k, v in kwargs.items()):
                yield anime
                c += 1
                if c >= limit:
                    return

    def remove(self, **kwargs):
        for anime in self.list:
            if all(anime[k] == v for k, v in kwargs.items()):
                self.list.remove(anime)  # type: ignore  # AnimeList has remove method
                break
        self.createList()

    def set(self, data):
        if not isinstance(data, AnimeList):
            raise TypeError("AnimeList instance required, not: {}".format(type(data)))
        else:
            self.list = data
        self.next_list = None
        self.createList()

    def from_filter(self, criteria, listrange=(0, 50)):
        self.list, self.next_list = self.parent.getAnimelist(criteria, listrange)

        self.update_scrollzone()  # Necessary?
        self.createList()

    def createList(self, start=0, waiting=None, list_id=None):
        if list_id is None:
            list_id = self.list_id + 1
            self.list_id = list_id
            # self.log("ANIME_LIST", f'New list id: {list_id}')

        self.generate_list(start, list_id)

    def generate_list(self, start, list_id):
        que = queue.Queue()
        self.parent.getElemImages(que)

        if start == 0:
            try:
                self.canvas.yview_moveto(0)
                while len(self.winfo_children()) > 0:
                    for child in self.winfo_children():
                        child.destroy()

            except Exception as e:
                self.log("MAIN_STATE", "[ERROR] - On AnimeListFrame.create_list():", e)
                return

            if self.list_id != list_id:
                # self.log("ANIME_LIST", f'Interrupted, list id: {list_id}')
                return

        # Ensure the Load More button is on the last column
        anime_count = self.animePerPage // self.animePerRow * self.animePerRow - 1

        ids = set()
        row = []
        self.list_timer = Timer(
            "Anime List Timer", lambda *args: self.log("ANIME_LIST", *args)
        )

        last_ind = queue.Queue()
        last_ind.put(anime_count)

        def draw_row(list_id):
            buf = []
            while row:
                args = row.pop(0)
                buf.append(args)
            self.parent.getAnimePicturesCache(
                [a[1].id for a in buf]
            )  # Generate image cache / batch sql requests

            for args in buf:
                tmp = self.create_elem(*args)
                if tmp:
                    ids.add(tmp)
                # if args[1]['status'] == 'UPDATE': # TODO - Use a thread?
                #     self.parent.api.anime(args[1]['id'])
            if self.list_id != list_id:
                return False  # == break

        def func(start, stop, list_id):
            def wrapped(i, data):
                if i < 0 or i + start >= stop:
                    return False  # == break

                if self.list_id != list_id or self.parent.closing:
                    # self.log("ANIME_LIST", f'Interrupted, list id: {list_id}')
                    return False  # == break

                if data is None:
                    if (
                        i == 0 and start == 0
                    ):  # If start != 0 then there must be previous results so it's fine
                        Label(
                            self,
                            text="No results",
                            font=("Source Code Pro Medium", 20),
                            bg=self.parent.colors["Gray2"],
                            fg=self.parent.colors["Gray4"],
                        ).grid(columnspan=self.animePerRow, row=0, pady=50)
                    return False  # == break
                row.append((i + start, data, que))
                # print(i+start)

                if (i + start) % self.animePerRow == 2:
                    return draw_row(list_id)

            return wrapped

        def cb(start, list_id):
            def wrapped(i):
                if list_id != self.list_id:
                    return
                # try:
                #     if ids:
                #         with self.parent.database.get_lock():
                #             sql = 'UPDATE anime SET status="UPDATE" WHERE id IN (' + ', '.join(
                #                 str(i) for i in ids) + ')'
                #             self.parent.database.sql(sql, get_output=False)

                last_ind.put(i)

                if i < last_ind.get(block=False):
                    if self.next_list is not None:
                        self.list, self.next_list = self.next_list()

                        # Check if we have a valid list before trying to map
                        if self.list is not None:
                            # Can't use a while cuz we're using tkinter function scheduler, so recursive fn goes brrr
                            self.list.map(  # type: ignore
                                func(start, anime_count + start, list_id),
                                lambda func: self.after(100, func),
                                cb(start, list_id),
                            )

                        return
                else:
                    try:
                        if not self.list.empty():  # type: ignore
                            self.load_more_button(start + i - len(row) + 1)

                        else:
                            # while row:
                            # 	args = row.pop(0)
                            # 	self.create_elem(*args)
                            draw_row(list_id)

                        self.list_timer.stats()
                        self.parent.stopSearch = True
                    finally:
                        que.put("STOP")

            return wrapped

        self.list.map(  # type: ignore
            func(start, anime_count + start, list_id),
            lambda func: self.after(100, func),
            cb(start, list_id),
        )

        pass

    def create_elem(self, index, anime, queue):
        self.list_timer.start()
        if self.blank_image is None:
            self.blank_image = self.parent.getImage(None, (225, 310))

        title = anime.title
        if title is None:
            self.list_timer.stop()
            return

        if len(title) > 35:
            title = title[:35] + "..."

        img_can = Canvas(
            self,
            width=225,
            height=310,
            highlightthickness=0,
            bg=self.parent.colors["Gray3"],
        )
        img_can.bind(
            "<Button-1>", lambda e, id=anime.id: self.parent.drawOptionsWindow(id)
        )
        img_can.bind("<Button-3>", lambda e, id=anime.id: self.parent.view(id))
        img_can.grid(column=index % self.animePerRow, row=index // self.animePerRow * 2)

        img_can.create_image(0, 0, image=self.blank_image, anchor="nw")
        img_can.image = self.blank_image  # type: ignore  # Keep reference to prevent garbage collection

        if anime.like == 1:
            title += " ❤"

        lbl = Label(
            self,
            text=title,
            bg=self.parent.colors["Gray2"],
            fg=self.parent.colors[self.parent.tagcolors[anime.tag]],
            font=("Source Code Pro Medium", 13),
            bd=0,
            wraplength=220,
        )

        lbl.grid(
            column=index % self.animePerRow, row=(index // self.animePerRow * 2) + 1
        )
        lbl.name = str(anime.id)  # type: ignore  # Custom attribute for identification

        self.update_scrollzone([img_can, lbl])

        filename = os.path.join(self.parent.cache, str(anime.id) + ".jpg")
        # url = anime.picture
        pics = self.parent.getAnimePictures(anime.id)
        if pics:  # TODO - Choose best pic
            url = pics[0]["url"]
            queue.put((filename, url, img_can))
            out = None
        else:
            out = anime.id
        self.list_timer.stop()
        return out

    def load_more_button(self, index):
        img_can = Canvas(
            self,
            width=225,
            height=310,
            highlightthickness=0,
            bg=self.parent.colors["Gray2"],
        )
        img_can.grid(
            column=(index - 1) % self.animePerRow,
            row=(index - 1) // self.animePerRow * 2,
        )

        size = 75
        x, y = int(225 / 2 - size / 2), int(310 / 2 - size / 2)
        pos = (
            x,
            y + size / 2,
            x + size,
            y + size / 2,
            x + size / 2,
            y + size / 2,
            x + size / 2,
            y,
            x + size / 2,
            y + size,
        )
        img_can.create_line(  # type: ignore
            *pos, capstyle="round", fill=self.parent.colors["Gray4"], width=15
        )

        lbl = Label(
            self,
            text="Load more...",
            bg=self.parent.colors["Gray2"],
            fg=self.parent.colors["Gray4"],
            font=("Source Code Pro Medium", 13),
            bd=0,
            wraplength=220,
        )
        lbl.grid(
            column=(index - 1) % self.animePerRow,
            row=((index - 1) // self.animePerRow * 2) + 1,
        )
        lbl.name = str(-1)  # type: ignore  # Custom attribute for identification

        toDestroy = (img_can, lbl)
        img_can.bind("<Button-1>", lambda e, s=index: self.load_more(index, toDestroy))

    def load_more(self, start, toDestroy):
        [e.destroy() for e in toDestroy]
        self.createList(start=start - 1)


class TableFrame(Frame):
    def __init__(
        self,
        parent,
        keys,
        cb=None,
        scrollbar=True,
        sort_key=None,
        invert_sort=True,
        **kwargs,
    ):
        self.column_keys: dict = (
            keys  # Renamed to avoid conflict with Tkinter keys() method
        )
        self.sort_key = sort_key or next(iter(self.column_keys.keys()))
        self.filtered = {}
        self.invert_sort = invert_sort
        self.cb = cb
        self.use_scrollbar = scrollbar
        self.config_ = kwargs
        self.keys_config = {}
        self.cell_config = None
        self.table = []
        self.wid_table = DefaultDict([])

        super().__init__(parent)
        self.configure(**kwargs)

    def draw_keys(self):
        for i, key in enumerate(self.column_keys):
            # self.grid_columnconfigure(i, weight=1)
            self.table_zone.grid_columnconfigure(i, weight=1)
            key_frame = Frame(self.table_zone, bg="pink" if i % 2 == 0 else "white")
            key_frame.grid_columnconfigure(0, weight=1)

            b = Button(key_frame, text=key, command=lambda a=key: self.sort_by(a))
            # b.configure(command=lambda a=key, b=b: self.filter_by(a, b))
            b.configure(**parse_args(b, dict_merge(self.config_, self.keys_config)))
            b.grid(row=0, column=0, sticky="nsew")

            if self.sort_key == key:
                if self.invert_sort:
                    sort_txt = "▼"
                else:
                    sort_txt = "▲"
            else:
                sort_txt = "►"

            c = Button(key_frame, text=sort_txt, command=lambda a=key: self.sort_by(a))
            c.configure(**parse_args(c, dict_merge(self.config_, self.keys_config)))
            c.grid(row=0, column=1, sticky="nse")

            key_frame.grid(row=0, column=i, sticky="nsew")

    def extend(self, data_list):
        # self.table.extend(data_list)
        for data in data_list:
            self.add_row(data)

    def add_row(self, data):
        key = lambda e: e.get(self.column_keys[self.sort_key], -1) * (
            -1 if self.invert_sort else 1
        )  # This wont work for text but whatever
        bisect.insort(
            self.table, data, key=key
        )  # Ig i could have made that function myself but whatever, this isn't a contest
        # self.table.append(data)

    def pop(self, i):
        return self.table.pop(i)

    def remove(self, data):
        self.table.remove(data)

    def clear(self):
        self.table = []

    def sort_by(self, key):
        if self.sort_key == key:
            self.invert_sort = not self.invert_sort
        else:
            self.sort_key = key
            self.invert_sort = True
        self.table.sort(
            key=lambda e: e.get(self.column_keys[self.sort_key], -1),
            reverse=self.invert_sort,
        )
        self.draw_table()

    def filter_by(self, key, wid):
        pop = Toplevel(wid)
        pop.overrideredirect(True)

        x, y = (
            wid.winfo_rootx(),
            wid.winfo_rooty() + wid.winfo_height(),
        )

        pop.geometry(f"+{x}+{y}")

        # TODO - There are wayyy to many possibilities, what's even the point of this?

    def draw_table(self):
        for w in self.winfo_children():
            w.destroy()

        self.table_zone = ScrollableFrame(self, axis="V", scrollbar=False)
        self.draw_keys()

        # Should always be sorted
        # entries = sorted(
        #     self.table,
        #     key=lambda e: e.get(self.keys[self.sort_key], -1),
        #     reverse=self.invert_sort,
        # )

        for row, data in enumerate(self.table):
            for i, key in enumerate(self.column_keys.values()):
                b = Button(
                    self.table_zone,
                    text=data.get(key, "Nan"),
                )
                if self.cb is not None:
                    b.configure(command=lambda a=data: self.cb(a))  # type: ignore
                conf = parse_args(b, self.config_)
                if self.cell_config is not None:
                    conf = dict_merge(conf, self.cell_config(row, i, data) or {})
                b.configure(**conf)
                b.grid(row=row + 1, column=i, sticky="nsew")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.table_zone.config(**parse_args(self.table_zone, self.config_))
        self.table_zone.grid(
            row=0, column=0, columnspan=len(self.column_keys), sticky="nsew", padx=1
        )
        self.table_zone.update_scrollzone()

        if self.use_scrollbar:
            self.scrollbar = CustomScrollbar(self)

            self.scrollbar.config(
                command=self.table_zone.canvas.yview, orient="vertical"
            )
            self.table_zone.canvas.configure(yscrollcommand=self.scrollbar.set)

            self.grid_columnconfigure(1, weight=1)

            self.scrollbar.grid(
                row=0, rowspan=2, column=len(self.column_keys) + 1, sticky="ns"
            )

    def configure(self, cb=None, **kwargs):  # type: ignore
        if cb is not None:
            self.cb = cb
        self.config_ = kwargs
        super().configure(**parse_args(self, self.config_))

    def configure_keys(self, **kwargs):
        self.keys_config = kwargs

    def configure_cells(self, cb):
        self.cell_config = cb


class Timer:
    def __init__(self, name, logger=None):
        self.startTime = time.time()
        self.name = name

        self.timer = None
        self.timeList = []

        if logger is None:
            self.log = log
        else:
            self.log = logger

    def start(self):
        self.stop()
        self.timer = time.time()

    def stop(self):
        if self.timer is not None:
            self.timeList.append(time.time() - self.timer)
            self.timer = None

    def stats(self):
        nameBracks = "[{}]".format(self.name.center(10))
        total = time.time() - self.startTime
        self.log(nameBracks, "Total:", int(total * 1000), "ms")
        if len(self.timeList) > 0:
            total = sum(self.timeList)
            avg = total / len(self.timeList)
            self.log(
                nameBracks,
                "Average:",
                int(avg * 1000),
                "ms/loop - Loops:",
                len(self.timeList),
                " (",
                int(total * 1000),
                "ms)",
            )


class LoginDialog(Dialog):
    def __init__(self, fields, title, parent=None, validator=None):
        if len(fields) == 0:
            raise ValueError("You should at least have one field set!")

        self.fields = fields

        self.validator = validator

        self.headless = sys.platform == "linux" and "DISPLAY" not in os.environ
        if self.headless:
            # Running headless
            self.results = {}

            for i, (field, value) in enumerate(self.fields.items()):
                text = f"{field}"
                if value:
                    text += f"({value})"
                out = None
                while not out:
                    out = input(text + ": ")

                    if not out:
                        if value:
                            out = value

                    if out:
                        self.results[field] = out

            pass
        else:
            self.results = None

            Dialog.__init__(self, parent, title)

    def body(self, master):
        self.entries = {}

        for i, (field, value) in enumerate(self.fields.items()):
            Label(master, text=f"{field.capitalize()}: ", justify="right").grid(
                row=i, column=0, padx=5, sticky="w"
            )

            entry = Entry(master, name="entry_" + field)
            if value is not None:
                entry.insert("end", value)
            entry.grid(row=i, column=1, padx=5, sticky="we")
            setattr(self, "entry_" + field, entry)
            self.entries[field] = entry

        return next(iter(self.entries.values()))

    def validate(self):  # type: ignore
        try:
            self.results = {}
            for field, entry in self.entries.items():
                self.results[field] = entry.get()
        except Exception as e:
            showwarning(
                "Error", "An error occured" + str(e) + "\nPlease try again", parent=self
            )
            return 0

        check = self.validator(self.results)  # type: ignore
        if check != 1:
            showwarning("Error", str(check) + "\nPlease try again")
            return 0

        return 1


def parse_args(wid, kwargs):
    return dict((k, v) for k, v in kwargs.items() if k in wid.config().keys())


def new_iter(first, iter):
    yield first
    for i in iter:
        yield i


def merge_iter(a, b):
    for i in a:
        yield i
    for i in b:
        yield i


def peek(iter):
    try:
        first = next(iter, None)
    except StopIteration:
        return None, ()
    except Exception as e:
        return None, iter
    else:
        return first, new_iter(first, iter)


def dict_merge(a, b):
    "Used in place of the | operator in 3.10 for compatibility"
    new_dict = {}
    for d in (a, b):
        for k, v in d.items():
            new_dict[k] = v
    return new_dict


def project_modules(root="./"):
    ignore = ("__pycache__", ".git", "venv", "lib", "build", "dist", ".vscode")
    modules = {}
    pattern = re.compile(r"(?:from ([\w_\.]*) import \S*)|(?:import ([\w_\.]*))")
    for f in os.listdir(root):
        if f in ignore:
            continue
        path = os.path.realpath(os.path.join(root, f))
        if os.path.isdir(path):
            modules = dict_merge(modules, project_modules(path))
            continue
        end = f.split(".")[-1]
        if end == "py":
            with open(path, encoding="utf-8") as file:
                for i, line in enumerate(file):
                    for match in re.finditer(pattern, line):
                        groups = match.groups()
                        if groups[0]:
                            m = groups[0]
                            if m in modules.keys():
                                modules[m].append((path, i + 1))
                            else:
                                modules[m] = [(path, i + 1)]
                        elif groups[1]:
                            if "," in groups[1]:
                                for m in groups[1].split(","):
                                    if m in modules.keys():
                                        modules[m].append((path, i + 1))
                                    else:
                                        modules[m] = [(path, i + 1)]
                            else:
                                m = groups[1]
                                if m in modules.keys():
                                    modules[m].append((path, i + 1))
                                else:
                                    modules[m] = [(path, i + 1)]
    return dict(sorted(modules.items()))


def persist_manager_settings(category: str, manager_name: str, settings_dict: dict):
    """Persist manager settings into the global settings.json under `category`.

    category is typically 'file_managers' or 'torrent_managers'.
    """
    try:
        from .constants import Constants
    except Exception:
        from constants import Constants

    appdata = Constants.getAppdata()
    settings_path = os.path.join(appdata, "settings.json")

    try:
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
    except Exception:
        data = {}

    cat = data.get(category, {})
    if manager_name not in cat:
        cat[manager_name] = {}
    # Overwrite manager settings with provided dict
    cat[manager_name].update(settings_dict)
    # Update last used keys when appropriate
    if category == "file_managers":
        cat["last_fm_used"] = manager_name
    elif category == "torrent_managers":
        cat["last_tm_used"] = manager_name

    data[category] = cat

    try:
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, sort_keys=True, indent=4, ensure_ascii=False)
    except Exception:
        # Don't crash on failure to persist
        pass


def project_stats(root="./", isroot=False):
    def pp_bytes(size):
        units = ("o", "Ko", "Mo", "Go", "To")
        i = 0
        while size / 1000 > 1:
            size = size // 1000
            i += 1
        return str(size) + " " + units[i]

    ignore = ("__pycache__", ".git", "venv", "lib", "build", "dist", ".vscode")
    lines, files, folders, size = 0, 0, 0, 0
    for f in os.listdir(root):
        if f in ignore:
            continue
        end = f.split(".")[-1]
        path = os.path.join(root, f)
        if os.path.isfile(path):
            size += os.path.getsize(path)
            if end == "py":
                files += 1
                try:
                    with open(path, encoding="utf-8") as file:
                        lines += len(file.readlines()) + 1
                except Exception as e:
                    pass
        elif os.path.isdir(path):
            t_lines, t_files, t_folders, t_size = project_stats(path)
            lines += t_lines
            files += t_files
            folders += t_folders + 1
            size += t_size
    if isroot:
        log(
            "{} lines in the project, {} files, {} folders, total size: {}".format(
                lines, files, folders, pp_bytes(size)
            )
        )
    return lines, files, folders, size


if __name__ == "__main__":
    import os
    import shutil

    libs = [
        "C:\\Users\\willi\\AppData\\Local\\Programs\\Python\\Python310\\lib",
        "C:\\Users\\willi\\AppData\\Local\\Programs\\Python\\Python310",
        "E:\\Anime Manager\\venv\\lib\\site-packages",
    ]
    root = os.path.normpath("E:/Anime Manager/installer/Lib")

    ignore = [f.rsplit(".", 1)[0] for f in os.listdir()]

    if False:

        for k, v in project_modules().items():
            if k.startswith(".") or k in ignore:
                continue
            log(k, ":")
            try:
                # Code injection fix: Replace unsafe exec/eval with safe importlib approach
                # Use importlib to safely load modules
                import importlib.util

                spec = importlib.util.find_spec(k)
                if spec is None:
                    log(f"Module {k} not found, skipping")
                    continue

                if spec.origin is None:
                    log(f"Module {k} has no origin, skipping")
                    continue

                path = spec.origin
                dirname = os.path.dirname(path)
                for libs_root in libs:
                    try:
                        rel_path = os.path.relpath(path, libs_root)
                    except ValueError:
                        continue
                    else:
                        if rel_path.startswith(os.pardir):
                            continue
                        name = rel_path.split("\\", 1)[0]
                        path = os.path.join(libs_root, name)
                        break
                else:
                    # No root found??
                    # Just keep current path
                    name = os.path.basename(path)

                dest = os.path.join(root, name)
                shutil.copyfile(path, dest)
            except Exception as e:
                log(f"Error: {e}")
            # for p in v:
            #     log('   File "{}", line {}'.format(*p))
    project_stats(os.path.abspath(r"D:\willi\Documents\Python"), True)


class MemoryManager:
    """Comprehensive memory management system for the application"""

    def __init__(self, memory_limit_gb=4.0, enable_tracemalloc=True):
        self.memory_limit_bytes = int(memory_limit_gb * 1024 * 1024 * 1024)
        self.process = psutil.Process()
        self.monitoring_active = False
        self.monitor_thread = None
        self.alert_callbacks = []

        # Memory monitoring
        self.memory_history = []
        self.gc_stats = {'collections': 0, 'freed_objects': 0, 'peak_memory': 0}
        self.memory_levels = {
            'low': 0.7,      # < 70% of limit
            'medium': 0.85,  # 70-85% of limit
            'high': 0.95,    # 85-95% of limit
            'critical': 1.0  # > 95% of limit
        }

        # Object pooling
        self.object_pools = defaultdict(list)
        self.pool_limits = {
            'anime': 100,
            'character': 50,
            'search_result': 200,
            'thumbnail': 50,
            'image': 100
        }

        # Weak references for leak detection
        self.weak_refs = weakref.WeakSet()
        self.tracked_objects = {}
        self.leak_threshold_hours = 1.0

        # Performance monitoring
        self.performance_stats = {
            'memory_checks': 0,
            'alerts_triggered': 0,
            'objects_pooled': 0,
            'leaks_detected': 0
        }

        # Enable tracemalloc for detailed memory tracking
        if enable_tracemalloc:
            tracemalloc.start()
            self.tracemalloc_enabled = True
        else:
            self.tracemalloc_enabled = False

    def start_monitoring(self, interval_seconds=30.0):
        """Start background memory monitoring"""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval_seconds,),
            daemon=True,
            name="MemoryMonitor"
        )
        self.monitor_thread.start()
        print(f"Memory monitoring started (limit: {self.memory_limit_bytes / (1024**3):.1f}GB)")

    def stop_monitoring(self):
        """Stop memory monitoring"""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5.0)
        print("Memory monitoring stopped")

    def _monitor_loop(self, interval_seconds):
        """Background monitoring loop"""
        while self.monitoring_active:
            try:
                stats = self.get_memory_stats()
                self.memory_history.append((time.time(), stats))

                # Keep only recent history (last 60 minutes)
                cutoff_time = time.time() - 3600
                self.memory_history = [
                    (t, s) for t, s in self.memory_history if t > cutoff_time
                ]

                # Check memory pressure and take action
                self._handle_memory_pressure(stats)

                # Update performance stats
                self.performance_stats['memory_checks'] += 1

                time.sleep(interval_seconds)

            except Exception as e:
                print(f"Memory monitoring error: {e}")
                time.sleep(interval_seconds)

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics"""
        try:
            memory_info = self.process.memory_info()
            current_mb = memory_info.rss / (1024 * 1024)

            # Get memory level
            usage_ratio = current_mb / (self.memory_limit_bytes / (1024 * 1024))
            memory_level = 'low'
            for level, threshold in self.memory_levels.items():
                if usage_ratio >= threshold:
                    memory_level = level
                else:
                    break

            # Update peak memory
            if current_mb > self.gc_stats['peak_memory']:
                self.gc_stats['peak_memory'] = current_mb

            # Get GC stats
            gc_stats = gc.get_stats()

            # Get tracemalloc stats if enabled
            tracemalloc_stats = None
            if self.tracemalloc_enabled:
                try:
                    current, peak = tracemalloc.get_traced_memory()
                    tracemalloc_stats = {
                        'current_mb': current / (1024 * 1024),
                        'peak_mb': peak / (1024 * 1024)
                    }
                except:
                    pass

            return {
                'current_mb': current_mb,
                'peak_mb': self.gc_stats['peak_memory'],
                'usage_ratio': usage_ratio,
                'memory_level': memory_level,
                'available_mb': psutil.virtual_memory().available / (1024 * 1024),
                'gc_collections': sum(stat['collections'] for stat in gc_stats),
                'object_counts': gc.get_count(),
                'tracemalloc': tracemalloc_stats,
                'pool_sizes': {k: len(v) for k, v in self.object_pools.items()},
                'tracked_objects': len(self.tracked_objects)
            }

        except Exception as e:
            print(f"Error getting memory stats: {e}")
            return {
                'current_mb': 0,
                'peak_mb': 0,
                'usage_ratio': 0,
                'memory_level': 'unknown',
                'available_mb': 0,
                'gc_collections': 0,
                'object_counts': (0, 0, 0),
                'tracemalloc': None,
                'pool_sizes': {},
                'tracked_objects': 0
            }

    def _handle_memory_pressure(self, stats: Dict[str, Any]):
        """Handle memory pressure based on current level"""
        level = stats['memory_level']

        if level == 'high':
            print(f"High memory usage detected ({stats['current_mb']:.1f}MB)")
            self._cleanup_non_essential()
            self.force_garbage_collection()

        elif level == 'critical':
            print(f"Critical memory usage detected ({stats['current_mb']:.1f}MB)")
            self._aggressive_cleanup()
            self.force_garbage_collection()
            self._trigger_alerts('critical_memory', stats)

    def force_garbage_collection(self):
        """Force garbage collection with statistics"""
        before_stats = self.get_memory_stats()

        # Run garbage collection
        collected = gc.collect()

        after_stats = self.get_memory_stats()

        freed_mb = before_stats['current_mb'] - after_stats['current_mb']
        self.gc_stats['collections'] += 1
        self.gc_stats['freed_objects'] += collected

        print(f"GC: Collected {collected} objects, freed {freed_mb:.2f}MB")

    def get_object_from_pool(self, object_type: str) -> Any:
        """Get object from pool or create new one"""
        if object_type in self.object_pools and self.object_pools[object_type]:
            obj = self.object_pools[object_type].pop()
            self.performance_stats['objects_pooled'] += 1
            return obj

        # Create new object based on type
        return self._create_object(object_type)

    def return_object_to_pool(self, object_type: str, obj: Any):
        """Return object to pool for reuse"""
        if object_type in self.object_pools:
            # Clear object state before pooling
            self._clear_object_state(obj)

            # Add to pool if under limit
            if len(self.object_pools[object_type]) < self.pool_limits.get(object_type, 50):
                self.object_pools[object_type].append(obj)

    def track_object(self, obj: Any, name: str = None, metadata: Dict[str, Any] = None):
        """Track object for memory leak detection"""
        if name is None:
            name = f"object_{id(obj)}"

        # Create weak reference to avoid circular dependencies
        weak_ref = weakref.ref(obj, lambda ref: self._object_collected(name))
        self.weak_refs.add(weak_ref)

        self.tracked_objects[name] = {
            'weak_ref': weak_ref,
            'created_at': time.time(),
            'type': type(obj).__name__,
            'metadata': metadata or {}
        }

    def _object_collected(self, name: str):
        """Callback when tracked object is garbage collected"""
        if name in self.tracked_objects:
            del self.tracked_objects[name]

    def detect_memory_leaks(self) -> List[Dict[str, Any]]:
        """Detect potential memory leaks"""
        leaks = []
        current_time = time.time()

        for name, info in self.tracked_objects.items():
            weak_ref = info['weak_ref']

            # Check if object is still alive after threshold time
            if weak_ref() is not None:
                age_hours = (current_time - info['created_at']) / 3600
                if age_hours > self.leak_threshold_hours:
                    leaks.append({
                        'name': name,
                        'type': info['type'],
                        'age_hours': age_hours,
                        'metadata': info['metadata'],
                        'still_alive': True
                    })

        self.performance_stats['leaks_detected'] = len(leaks)
        return leaks

    def add_alert_callback(self, callback: Callable):
        """Add callback for memory alerts"""
        self.alert_callbacks.append(callback)

    def _trigger_alerts(self, alert_type: str, data: Dict[str, Any]):
        """Trigger memory alerts"""
        self.performance_stats['alerts_triggered'] += 1

        for callback in self.alert_callbacks:
            try:
                callback(alert_type, data)
            except Exception as e:
                print(f"Alert callback error: {e}")

    def optimize_memory_usage(self):
        """Comprehensive memory optimization"""
        print("Starting comprehensive memory optimization...")

        # 1. Force garbage collection
        print("Running garbage collection...")
        self.force_garbage_collection()

        # 2. Clear object pools
        print("Clearing object pools...")
        total_cleared = 0
        for pool_type, pool in self.object_pools.items():
            total_cleared += len(pool)
            pool.clear()
        print(f"Cleared {total_cleared} objects from pools")

        # 3. Clear tracked objects (force cleanup)
        print("Cleaning up tracked objects...")
        leaks_before = len(self.detect_memory_leaks())
        self.tracked_objects.clear()
        self.weak_refs.clear()
        print(f"Cleaned up tracking data (was tracking {leaks_before} potential leaks)")

        # 4. Run final garbage collection
        print("Final garbage collection...")
        self.force_garbage_collection()

        # Show results
        final_stats = self.get_memory_stats()
        print(f"Memory optimization complete. Current usage: {final_stats['current_mb']:.2f}MB")

        return final_stats

    def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive memory performance report"""
        current_stats = self.get_memory_stats()
        leaks = self.detect_memory_leaks()

        # Calculate memory efficiency metrics
        memory_efficiency = 1.0 - (current_stats['usage_ratio'])
        pool_utilization = sum(len(pool) for pool in self.object_pools.values()) / sum(self.pool_limits.values()) if self.pool_limits else 0

        return {
            'current_memory_mb': current_stats['current_mb'],
            'peak_memory_mb': current_stats['peak_mb'],
            'memory_limit_gb': self.memory_limit_bytes / (1024**3),
            'usage_percentage': current_stats['usage_ratio'] * 100,
            'memory_level': current_stats['memory_level'],
            'memory_efficiency': memory_efficiency,
            'pool_utilization': pool_utilization,
            'gc_collections': self.gc_stats['collections'],
            'objects_freed': self.gc_stats['freed_objects'],
            'tracked_objects': len(self.tracked_objects),
            'potential_leaks': len(leaks),
            'pool_sizes': current_stats['pool_sizes'],
            'performance_stats': self.performance_stats.copy(),
            'memory_history_points': len(self.memory_history),
            'leak_details': leaks[:10],  # First 10 leaks for brevity
            'tracemalloc_enabled': self.tracemalloc_enabled,
            'tracemalloc_stats': current_stats['tracemalloc']
        }

    def _create_object(self, object_type: str) -> Any:
        """Create new object of specified type"""
        # This would be implemented based on actual object types used
        if object_type == 'anime':
            return {'type': 'anime', 'data': {}}
        elif object_type == 'character':
            return {'type': 'character', 'data': {}}
        elif object_type == 'search_result':
            return {'type': 'search_result', 'data': {}}
        else:
            return {'type': object_type, 'data': {}}

    def _clear_object_state(self, obj: Any):
        """Clear object state for pooling"""
        if isinstance(obj, dict):
            # Clear dict contents but keep structure
            keys_to_remove = [k for k in obj.keys() if k != 'type']
            for key in keys_to_remove:
                del obj[key]
            if 'data' in obj:
                obj['data'].clear()

    def _cleanup_non_essential(self):
        """Clean up non-essential memory usage"""
        # Clear any caches that can be rebuilt
        # This would be implemented based on application-specific caches
        pass

    def _aggressive_cleanup(self):
        """Perform aggressive memory cleanup"""
        # Clear all pools
        for pool in self.object_pools.values():
            pool.clear()

        # Force multiple GC cycles
        for _ in range(3):
            gc.collect()

        # Clear weak references
        self.weak_refs.clear()

        print("Aggressive memory cleanup completed")


# Global memory manager instance
_memory_manager = None

def get_memory_manager() -> MemoryManager:
    """Get the global memory manager instance"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager

def track_memory_object(obj: Any, name: str = None, metadata: Dict[str, Any] = None):
    """Convenience function to track an object for memory leak detection"""
    get_memory_manager().track_object(obj, name, metadata)

def get_object_from_pool(object_type: str) -> Any:
    """Convenience function to get object from pool"""
    return get_memory_manager().get_object_from_pool(object_type)

def return_object_to_pool(object_type: str, obj: Any):
    """Convenience function to return object to pool"""
    get_memory_manager().return_object_to_pool(object_type, obj)
