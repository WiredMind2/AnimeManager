import os
from tkinter import (BOTH, BOTTOM, HORIZONTAL, TOP, Canvas, E, Frame, Label, N,
                     PhotoImage, S, Tk, Toplevel, W, X, Y)
from tkinter.ttk import Progressbar
from typing import Any, Optional


class Loading:
    # Type hints for attributes expected from Manager class
    root: Optional[Any]
    loadingWindow: Any
    colors: dict[str, str]
    iconPath: str

    # Methods expected from Manager class
    def getImage(self, path: str, size: Any = None) -> Any: ...

    def drawLoadingWindow(self):
        if self.root is None:
            self.loadingWindow = Tk()
        else:
            self.loadingWindow = Toplevel(self.root)

        self.loadingWindow.geometry("920x500+{}+{}".format(100, 100))
        self.loadingWindow.configure(bg=self.colors["Gray3"])
        self.loadingWindow.title("Nyaa.si - Custom Browser - Loading...")
        self.loadingWindow.wm_iconphoto(
            False, self.getImage(os.path.join(self.iconPath, "favicon.png"))
        )

        main = Frame(self.loadingWindow, width=920, bg=self.colors["Gray2"])
        for i in range(2):
            main.grid_rowconfigure(i, weight=1)
        main.grid_columnconfigure(0, weight=1)

        Label(
            main,
            text="Loading...",
            bg=self.colors["Gray2"],
            fg=self.colors["Gray4"],
            font=("Source Code Pro Medium", 20),
        ).grid(row=0, column=0, sticky="s")
        self.loadLabel = Label(
            main,
            text="-/-, -:-",
            bg=self.colors["Gray2"],
            fg=self.colors["Gray4"],
            font=("Source Code Pro Medium", 20),
        )
        self.loadLabel.grid(row=1, column=0, sticky="n")
        main.pack(fill="both", expand=True)

        self.loadProgress = Progressbar(
            self.loadingWindow, orient=HORIZONTAL, length=500, mode="determinate"
        )
        self.loadProgress.pack(side="bottom", padx=10, pady=10)
