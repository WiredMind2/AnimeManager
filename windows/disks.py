import os
import shutil
from tkinter import Canvas, Frame, Label, TclError

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


class Disks:
    def drawDiskWindow(self):
        # Functions
        if True:

            def getFiles(folder):
                files, folders = [], []
                for f in os.listdir(folder):
                    if os.path.isfile(folder + "/" + f):
                        files.append(f)
                    else:
                        if f != "Torrents":
                            folders.append(f)
                            a, b = getFiles(folder + "/" + f)
                            files += a
                            folders += b
                return files, folders

            def size_format(size):
                units = ("b", "Kb", "Mb", "Gb", "Tb")
                u = 0
                while u < len(units) - 1:
                    if size >= 1000:
                        size = size // 1000
                        u += 1
                    else:
                        break
                return f"{size:,}" + " " + units[u]

            def exit(e=None):
                self.diskWindow.destroy()

        # Window init - Fancy corners - Events
        if True:
            disk = self.animePath.split("/")[0]
            if self.diskWindow is None or not self.diskWindow.winfo_exists():
                size = (self.diskWindowMinWidth, self.diskWindowMinHeight)
                self.diskWindow = RoundTopLevel(
                    self.initWindow,
                    title="Disk " + disk,
                    minsize=size,
                    bg=self.colors["Gray2"],
                    fg=self.colors["Gray4"],
                )
            else:
                self.diskWindow.clear()
                self.diskWindow.focus()

        # Bars
        if True:
            barFrame = Frame(self.diskWindow, bg=self.colors["Gray2"])
            length = 500
            radius = 25
            usageColors = {75: "Green", 90: "Orange", 100: "Red"}
            total, used, free = shutil.disk_usage(disk)
            usedSize = length * used / total
            usedPrct = used / total * 100
            for p, c in list(usageColors.items())[::-1]:
                if usedPrct <= p:
                    color = c

            # self.diskWindow.titleLbl.configure(text="Disk "+disk, font=("Source Code Pro Medium",20),
            #         bg= self.colors['Gray2'], fg= self.colors['Gray4'],)

            bar = Canvas(
                barFrame,
                bg=self.colors["Gray2"],
                width=length,
                height=radius * 2,
                highlightthickness=0,
            )
            bar.create_line(
                radius,
                radius,
                length - radius,
                radius,
                capstyle="round",
                fill=self.colors["Gray4"],
                width=radius,
            )
            bar.create_line(
                radius,
                radius,
                usedSize - radius,
                radius,
                capstyle="round",
                fill=self.colors[color],
                width=radius,
            )
            bar.grid(row=1, column=0, columnspan=3)
            Label(
                barFrame,
                text="%d GB used" % (used // (2**30)),
                wraplength=900,
                font=("Source Code Pro Medium", 12),
                bg=self.colors["Gray2"],
                fg=self.colors["Gray4"],
            ).grid(row=2, column=0)
            Label(
                barFrame,
                text="%d GB total" % (total // (2**30)),
                wraplength=900,
                font=("Source Code Pro Medium", 12),
                bg=self.colors["Gray2"],
                fg=self.colors["Gray4"],
            ).grid(row=2, column=1)
            Label(
                barFrame,
                text="%d GB free" % (free // (2**30)),
                wraplength=900,
                font=("Source Code Pro Medium", 12),
                bg=self.colors["Gray2"],
                fg=self.colors["Gray4"],
            ).grid(row=2, column=2)
            barFrame.grid_columnconfigure(1, weight=1)
            barFrame.pack(pady=20)

        # Size info
        if True:
            cache_size = sum(
                os.path.getsize(os.path.join(self.cache, f))
                for f in os.listdir(self.cache)
            )
            db_size = os.path.getsize(self.dbPath)

            sizeFrame = Frame(self.diskWindow, bg=self.colors["Gray2"])
            Label(
                sizeFrame,
                text="Cache size:",
                font=("Source Code Pro Medium", 12),
                bg=self.colors["Gray2"],
                fg=self.colors["Gray4"],
            ).grid(row=0, column=0)
            Label(
                sizeFrame,
                text=size_format(cache_size),
                font=("Source Code Pro Medium", 12),
                bg=self.colors["Gray2"],
                fg=self.colors["Gray4"],
            ).grid(row=0, column=1)

            Label(
                sizeFrame,
                text="Database size:",
                font=("Source Code Pro Medium", 12),
                bg=self.colors["Gray2"],
                fg=self.colors["Gray4"],
            ).grid(row=1, column=0)
            Label(
                sizeFrame,
                text=size_format(db_size),
                font=("Source Code Pro Medium", 12),
                bg=self.colors["Gray2"],
                fg=self.colors["Gray4"],
            ).grid(row=1, column=1)
            [sizeFrame.grid_columnconfigure(i, weight=1) for i in range(2)]
            sizeFrame.pack(pady=20)

        # Stats info
        if True:
            fileFrame = Frame(self.diskWindow, bg=self.colors["Gray2"])
            t = Label(
                fileFrame,
                text="Animes folder:",
                wraplength=900,
                font=("Source Code Pro Medium", 20),
                bg=self.colors["Gray2"],
                fg=self.colors["Gray4"],
            )
            t.grid(row=0, column=0, columnspan=2)
            files, folders = getFiles(self.animePath)
            Label(
                fileFrame,
                text="%d files - %d folders" % (len(files), len(folders)),
                wraplength=900,
                font=("Source Code Pro Medium", 15),
                bg=self.colors["Gray2"],
                fg=self.colors["Gray4"],
            ).grid(row=1, column=0, sticky="nsew")
            # [fileFrame.grid_columnconfigure(i,weight=1) for i in range(2)]
            fileFrame.pack(pady=20)
