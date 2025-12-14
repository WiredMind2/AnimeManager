from tkinter import Button, Entry, StringVar, TclError

# Standardized import handling
try:
    # Try importing as package first
    from AnimeManager.window_frames import RoundTopLevel
except ImportError:
    try:
        # Try relative imports
        from ..window_frames import RoundTopLevel
    except ImportError:
        # Fallback to direct imports
        from window_frames import RoundTopLevel


class TextPopup:
    def drawTextPopupWindow(self, parent, title, callback, fentype="TEXT"):
        # Main window
        if True:
            if self.textPopupWindow is not None and self.textPopupWindow.winfo_exists():
                self.textPopupWindow.exit()
                self.textPopupWindow.destroy()
            self.textPopupWindow = RoundTopLevel(
                parent,
                title=title,
                minsize=(750, 150),
                bg=self.colors["Gray2"],
                fg=self.colors["Gray3"],
            )

        if fentype == "TEXT":
            var = StringVar()
            e = Entry(
                self.textPopupWindow,
                textvariable=var,
                highlightthickness=0,
                borderwidth=0,
                font=("Source Code Pro Medium", 13),
                bg=self.colors["Gray3"],
                fg=self.colors["White"],
            )
            e.bind("<Return>", lambda e, var=var: callback(var))
            e.grid(row=0, column=0, sticky="nsew", padx=5, pady=(0, 20))
            self.textPopupWindow.handles.append(e)
            Button(
                self.textPopupWindow,
                text="Ok",
                bd=0,
                height=1,
                relief="solid",
                font=("Source Code Pro Medium", 13),
                activebackground=self.colors["Gray2"],
                activeforeground=self.colors["Gray3"],
                bg=self.colors["Gray3"],
                fg=self.colors["Gray2"],
                command=lambda var=var: callback(var),
            ).grid(row=0, column=1, sticky="nsew", pady=(0, 20))
        else:
            self.log("ERROR", "Unknown window type", fentype)
            raise
