import tkinter as tk
from tkinter import (ALL, BOTH, BOTTOM, END, FLAT, GROOVE, HORIZONTAL, LEFT,
                      NE, NW, RAISED, RIDGE, RIGHT, SE, SOLID, SUNKEN, SW, TOP,
                      VERTICAL, Button, Canvas, Checkbutton, E, Entry, Frame,
                      Label, N, OptionMenu, S, Scrollbar, Toplevel, W, X, Y,
                      font, ttk)

try:
    from .general_utils import parse_args, dict_merge
except ImportError:
    from general_utils import parse_args, dict_merge

try:
    from .window_frames import ScrollableFrame
except ImportError:
    from window_frames import ScrollableFrame


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