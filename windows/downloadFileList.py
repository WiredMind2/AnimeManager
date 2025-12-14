from tkinter import Button, Label, TclError

# Standardized import handling
try:
    # Try importing as package first
    from AnimeManager.window_frames import RoundTopLevel
    from AnimeManager.table_frame import TableFrame
    from AnimeManager.constants import Constants
except ImportError:
    try:
        # Try relative imports
        from ..window_frames import RoundTopLevel
        from ..table_frame import TableFrame
        from ..constants import Constants
    except ImportError:
        # Fallback to direct imports
        from window_frames import RoundTopLevel
        from table_frame import TableFrame
        from constants import Constants


class DownloadFileList:
    def drawFileListWindow(self, publisher, id):
        # Functions
        if True:

            def startDownload(id, table):
                def wrapper(data):
                    out = self.downloadFile(id, url=data["url"])
                    download_cb(out, data, table)

                return wrapper

            def download_cb(out, data, table):
                if out.empty():
                    self.fileListWindow.after(10, download_cb, out, data, table)
                    return
                value = out.get()
                color = "Blue" if value is True else "Red"

                # ALL of this should match what is in getters.getTorrentColor()
                # Add a custom cache value for the torrent for it to change color when the table is redrawn

                # Check if title has already been matched before
                if hasattr(Constants, "getTorrentColor_title_cache"):
                    # If title is in cache, skips everything and immediately return the result
                    title_cache = Constants.getTorrentColor_title_cache
                else:
                    # Create empty cache
                    title_cache = {}
                    Constants.getTorrentColor_title_cache = title_cache

                title_cache[data["name"]] = self.colors[color]

                table.draw_table()

            def draw_entry(data, kwargs):  # Not used anymore
                titleLbl = Label(text=data["name"], **kwargs)
                titleLbl.grid(row=row, column=0, sticky="nsew")

                seedsLbl = Label(text=data["seeds"], **kwargs)
                seedsLbl.grid(row=row, column=1, sticky="nsew")

                leechsLbl = Label(text=data["leechs"], **kwargs)
                leechsLbl.grid(row=row, column=2, sticky="nsew")

                sizeLbl = Label(text=data["size"], **kwargs)
                sizeLbl.grid(row=row, column=3, sticky="nsew")

                engineLbl = Label(text=data["engine"], **kwargs)
                engineLbl.grid(row=row, column=4, sticky="nsew")

                def command(
                    e,
                    labels=(titleLbl, sizeLbl, seedsLbl, leechsLbl),
                    url=d["link"],
                    id=id,
                ):
                    return startDownload(labels, url, id)

                titleLbl.bind("<Button-1>", command)
                seedsLbl.bind("<Button-1>", command)
                leechsLbl.bind("<Button-1>", command)
                sizeLbl.bind("<Button-1>", command)

        # Window init - Fancy corners - Main frame - Events
        if True:
            size = (self.torrentDDLWindowMinWidth, self.torrentDDLWindowMinHeight)
            if self.fileListWindow is None or not self.fileListWindow.winfo_exists():
                self.fileListWindow = RoundTopLevel(
                    self.ddlWindow,
                    title="Torrents:",
                    minsize=size,
                    bg=self.colors["Gray2"],
                    fg=self.colors["Gray3"],
                )
            else:
                self.fileListWindow.clear()

        # Table
        if True:
            keys = {
                "Title": "name",
                "Seeds": "seeds",
                "Leechs": "leechs",
                "Size": "size",
                "Engine": "engine",
            }
            table = TableFrame(
                self.fileListWindow,
                keys,
                sort_key="Seeds",
                invert_sort=True,
                bg=self.colors["Gray2"],
            )
            table.configure(cb=startDownload(id, table))
            table.configure_keys(
                font=("Source Code Pro Medium", 13),
                bg=self.colors["Gray3"],
                fg=self.colors["White"],
                bd=0,
            )
            table.configure_cells(lambda i, j, data: data["config"](i, j, data))
            table.pack(expand=True, fill="both", padx=20)

            # table.grid_columnconfigure(0, weight=1)

        # Torrent list
        if True:
            data = self.ddlWindow.publisherData[publisher]

            # maxTitleLength = min(70, len(
            # 	sorted(
            # 		(d['name'] for d in data),
            # 		key=len,
            # 		reverse=True)[0]))
            # maxSizeLength = len(
            # 	str(sorted((d['size'] for d in data), reverse=True)[0]))

            maxTitleLength, maxSizeLength = 70, 0
            for d in data:
                tl = len(d["name"])
                if tl > maxTitleLength:
                    maxTitleLength = tl
                sl = len(str(d["size"]))
                if sl > maxSizeLength:
                    maxSizeLength = sl

            def config(i, j, data):
                fg = self.getTorrentColor(data["name"])
                bg = (self.colors["Gray2"], self.colors["Gray3"])[i % 2]

                kwargs = {
                    # "master": table,
                    "font": ("Source Code Pro Medium", 13),
                    "bg": bg,
                    "fg": fg,
                    "bd": 0,
                }
                return kwargs

            out = []
            for row, d in enumerate(data):
                title = d["name"]

                title = title[(len(publisher) + 3) :]
                if len(title) < 70:
                    name_short = title
                else:
                    name_short = title[:35] + "..." + title[-25:]

                data = {
                    "name": (name_short).ljust(maxTitleLength),
                    "seeds": (str(d["seeds"]) + "▲").rjust(5) + "   ",
                    "leechs": (str(d["leech"]) + "▼").rjust(5) + "   ",
                    "size": str(d["size"]).rjust(maxSizeLength),
                    "engine": str(d["engine_url"][:30]).rjust(30),
                    "title": title,
                    "url": d["link"],
                    "config": config,
                }
                out.append(data)
                # draw_entry(data, kwargs)

            # table.update_scrollzone()
            table.extend(out)
            table.draw_table()
