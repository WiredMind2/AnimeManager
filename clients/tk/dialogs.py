import sys

import tkinter as tk
from tkinter import (ALL, BOTH, BOTTOM, END, FLAT, GROOVE, HORIZONTAL, LEFT,
                      NE, NW, RAISED, RIDGE, RIGHT, SE, SOLID, SUNKEN, SW, TOP,
                      VERTICAL, Button, Canvas, Checkbutton, E, Entry, Frame,
                      Label, N, OptionMenu, S, Scrollbar, Toplevel, W, X, Y,
                      font, ttk)
from tkinter.messagebox import showwarning
from tkinter.simpledialog import Dialog


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