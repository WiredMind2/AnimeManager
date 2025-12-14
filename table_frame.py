import bisect

import tkinter as tk
from tkinter import (ALL, BOTH, BOTTOM, END, FLAT, GROOVE, HORIZONTAL, LEFT,
                      NE, NW, RAISED, RIDGE, RIGHT, SE, SOLID, SUNKEN, SW, TOP,
                      VERTICAL, Button, Canvas, Checkbutton, E, Entry, Frame,
                      Label, N, OptionMenu, S, Scrollbar, Toplevel, W, X, Y,
                      font, ttk)

try:
    from .classes import DefaultDict
except ImportError:
    from classes import DefaultDict

try:
    from .general_utils import parse_args, dict_merge
except ImportError:
    from general_utils import parse_args, dict_merge

try:
    from .window_frames import ScrollableFrame
except ImportError:
    from window_frames import ScrollableFrame

try:
    from .scrollbars import CustomScrollbar
except ImportError:
    from scrollbars import CustomScrollbar


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