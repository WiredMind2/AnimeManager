from tkinter import Frame, Label, TclError

# Standardized import handling
try:
    # Try importing as package first
    from AnimeManager.window_frames import RoundTopLevel, ScrollableFrame
except ImportError:
    try:
        # Try relative imports
        from ..window_frames import RoundTopLevel, ScrollableFrame
    except ImportError:
        # Fallback to direct imports
        from window_frames import RoundTopLevel, ScrollableFrame


class Logs:
    def drawLogsWindow(self):
        # Functions
        if True:

            def addLog(text):
                panel = self.logsWindow.panel
                row = self.logsWindow.row
                bg = "Gray2" if row % 2 == 1 else "Gray3"

                cell = Frame(panel, bg=self.colors["Gray2"])
                Label(
                    cell,
                    text=text,
                    bg=self.colors[bg],
                    fg=self.colors["White"],
                    font=("Source Code Pro Medium", 13),
                ).pack(fill="both", expand=True)
                cell.grid(column=0, row=row, sticky="ew")

                panel.grid_rowconfigure(row, weight=1)
                self.logsWindow.row += 1

            def removeLog(func):
                if self.loggingCb == func:
                    self.loggingCb = None

        # Window init
        if True:
            if self.logsWindow is None or not self.logsWindow.winfo_exists():
                size = (1000, 500)
                self.logsWindow = RoundTopLevel(
                    self.initWindow,
                    title="Logs",
                    minsize=size,
                    bg=self.colors["Gray2"],
                    fg=self.colors["Gray3"],
                )
            else:
                self.logsWindow.clear()
            self.logsWindow.grid_rowconfigure(0, weight=1)
            self.logsWindow.grid_columnconfigure(0, weight=1)

        # Main Panel
        if True:
            panel = ScrollableFrame(
                self.logsWindow, scrollbar=True, bg=self.colors["Gray2"]
            )
            panel.grid(row=0, column=0, sticky="nsew")
            panel.grid_columnconfigure(0, weight=1)

            self.logsWindow.panel = panel
            self.logsWindow.row = 0
            self.loggingCb = addLog
            self.logsWindow.bind("<Destroy>", lambda e: removeLog(addLog))
