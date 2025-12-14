import re
from operator import itemgetter
from tkinter import Button, Frame, Label, TclError

# Standardized import handling
try:
    # Try importing as package first
    from AnimeManager import search_engines
    from AnimeManager.general_utils import Timer
    from AnimeManager.window_frames import RoundTopLevel, ScrollableFrame
    from AnimeManager.classes import SortedDict, SortedList, TorrentList
except ImportError:
    try:
        # Try relative imports
        from .. import search_engines
        from ..general_utils import Timer
        from ..window_frames import RoundTopLevel, ScrollableFrame
        from ..classes import SortedDict, SortedList, TorrentList
    except ImportError:
        # Fallback to direct imports
        import search_engines
        from general_utils import Timer
        from window_frames import RoundTopLevel, ScrollableFrame
        from classes import SortedDict, SortedList, TorrentList


class Download:
    def drawDdlWindow(self, id, fetcher=None, parent=None):
        # Functions
        if True:

            def filename_slug(f):
                # Format a filename to increase matchs
                return f.lower().replace(" ", "")

            def get_publisher(filename):
                # Try to get a publisher name from a filename

                # '[publisher name]torrent name.torrent'
                publisher_pattern = r"^\[(.*?)\]+"

                result = re.findall(publisher_pattern, filename)
                if len(result) >= 1:
                    return result[0]
                else:
                    return None

            def search_handler(table, fetcher):
                # Handle torrent search and sorting
                timer = Timer(
                    "Torrent search",
                    logger=lambda *args, **kwargs: self.log(
                        "FILE_SEARCH", *args, **kwargs
                    ),
                )  # Init timer

                # Start torrent search
                if fetcher is None:
                    self.log("FILE_SEARCH", "Looking for torrents with id:", id)

                    # Get titles from database
                    database = self.getDatabase()
                    data = database.get(id=id, table="anime")
                    titles = data.title_synonyms + [data.title]
                    # titles = [data.title] # only search torrents with main title

                    fetcher = search_engines.search(titles)

                # Start search
                torrents = TorrentList(fetcher)

                # Init publishers dict

                def key_topPublishers(k):
                    # Bring best publishers to the top of the list
                    if k[0] in self.topPublishers:
                        return len(self.topPublishers) - self.topPublishers.index(k[0])
                    else:
                        return 0

                def key_dualAudio(k):
                    # Try to guess if torrent has dual audio
                    marked = ("dual", "dub")  # TODO - Shouldn't be hardcoded
                    for mark in marked:
                        for title in k[1]:
                            if mark in title["name"].lower():
                                return 1

                    return 0

                def key_seeds(k):
                    # Sort publishers by the highest amount of
                    # seeds in their torrents

                    key, values = k
                    if not values:  # None or empty
                        return -1  # Should be inferior to 0

                    else:
                        max_seeds = max(map(lambda e: int(e["seeds"]), values))
                        return max_seeds

                keys = (
                    # Prioritize 'famous' / 'well-known' publishers
                    (key_topPublishers, True),
                    # Bring torrents with dual audio to the top
                    (key_dualAudio, True),
                    (key_seeds, True),  # Sort by seeds
                )
                publishers = SortedDict(keys=keys)

                def cache_handler(torrent):
                    # Compute some cache data for
                    # each torrent in a thread, it's better to
                    # avoid doing it in main thread

                    filename = torrent["name"]
                    self.getTorrentColor(filename)

                def func(index, torrent):
                    # Add a torrent to the publishers dict
                    # Returns True if something changed

                    if torrent is None:
                        return

                    # Avoid raising an error when the window is closing
                    if self.closing or not self.ddlWindow.winfo_exists():
                        torrents.interrupt()
                        return

                    filename = torrent["name"]
                    # Look for publisher name
                    publisher = get_publisher(filename)

                    if publisher in publishers:
                        # Do not add file if it has already been found with more seeds
                        file_hash = filename_slug(filename)

                        for i, tmp_torrent in enumerate(publishers[publisher]):
                            if file_hash == filename_slug(tmp_torrent["name"]):
                                # Replace torrent if it has more seeds
                                if torrent["seeds"] > tmp_torrent["seeds"]:
                                    publishers[publisher][i] = torrent

                                return
                        else:
                            # Should run if the loop wasn't broken
                            # Add torrent to list
                            publishers[publisher].append(torrent)
                            return
                    else:
                        # Insert new publisher
                        publishers[publisher] = SortedList(
                            keys=((itemgetter("seeds"), True),)
                        )
                        publishers[publisher].append(torrent)
                        return

                def delay(func):
                    self.log("FILE_SEARCH", "Overriding torrents")
                    if publishers:
                        draw_table(table, publishers)

                    self.ddlWindow.after(500, func)

                def cb(index):
                    self.log("FILE_SEARCH", "All torrents found")
                    if index == -1:
                        # No torrents found
                        draw_table(table, {})
                    else:
                        self.log("FILE_SEARCH", "Overriding final torrents")
                        draw_table(table, publishers)
                    timer.stats()

                torrents.map(func, delay, cb)
                torrents.add_callback(cache_handler)

            def draw_table(table, publishers):
                timer = Timer(
                    "Draw torrent table",
                    logger=lambda *args, **kwargs: self.log(
                        "FILE_SEARCH", *args, **kwargs
                    ),
                )
                i = None

                for i, torrent in enumerate(publishers.items()):
                    timer.start()
                    publisher, data = torrent

                    if publisher is None:
                        publisher = "None"

                    # Save data
                    self.ddlWindow.publisherData[publisher] = data

                    button = self.ddlWindow.publisherButtons.get(i, None)
                    if button:
                        if button[0] == publisher:
                            continue  # No need to create a new button, skip
                        else:
                            button[1].destroy()

                    # Get color for button - fetch first color from corresponding torrents
                    for filename in [d["name"] for d in data]:
                        fg = self.getTorrentColor(filename)
                        # White is default color, ignore it
                        if fg != self.colors["White"]:
                            break

                    # Alternating bg color
                    bg = (self.colors["Gray2"], self.colors["Gray3"])[i % 2]

                    # Avoid raising an error when the window is closing
                    if self.closing or not self.ddlWindow.winfo_exists():
                        return

                    b = Button(
                        table,
                        text=publisher,
                        bd=0,
                        height=1,
                        relief="solid",
                        font=("Source Code Pro Medium", 13),
                        activebackground=self.colors["Gray3"],
                        activeforeground=fg,
                        bg=bg,
                        fg=fg,
                        command=lambda publisher=publisher, id=id: self.drawFileListWindow(
                            publisher, id
                        ),
                    )
                    b.grid(row=i, column=0, sticky="nsew")

                    self.ddlWindow.publisherButtons[i] = (publisher, b)

                try:
                    if i is None:
                        self.ddlWindow.titleLbl["text"] = "No files\nfound!"
                    else:
                        self.ddlWindow.titleLbl["text"] = "Publisher:"
                except TclError:
                    pass
                table.update_scrollzone()
                # self.log(
                #     'FILE_SEARCH', f'Updated torrent table in {round(time.time()-start, 2)}s')
                timer.stats()

        # Window init - Fancy corners - Main frame - Events
        if True:
            size = (self.publisherDDLWindowMinWidth, self.publisherDDLWindowMinHeight)
            if self.ddlWindow is None or not self.ddlWindow.winfo_exists():
                if parent is None:
                    parent = self.optionsWindow

                self.ddlWindow = RoundTopLevel(
                    parent,
                    title="Loading...",
                    minsize=size,
                    bg=self.colors["Gray3"],
                    fg=self.colors["Gray2"],
                )
            else:
                self.ddlWindow.clear()
                self.ddlWindow.titleLbl.configure(
                    text="Loading...",
                    bg=self.colors["Gray3"],
                    fg=self.colors["Gray2"],
                    font=("Source Code Pro Medium", 18),
                )

        # Search terms button
        if True:
            Button(
                self.ddlWindow,
                text="Manage search terms",
                bd=0,
                height=1,
                relief="solid",
                font=("Source Code Pro Medium", 13),
                bg=self.colors["Gray2"],
                fg=self.colors["Gray"],
                command=lambda id=id: self.drawSearchTermsWindow(id, self.ddlWindow),
            ).grid(row=0, sticky="ew", pady=(0, 5))

            Button(
                self.ddlWindow,
                text="Search torrent online",
                bd=0,
                height=1,
                relief="solid",
                font=("Source Code Pro Medium", 13),
                activebackground=self.colors["Gray2"],
                activeforeground=self.colors["Gray3"],
                bg=self.colors["Gray3"],
                fg=self.colors["White"],
                command=lambda id=id: self.search_torrent(id),
            ).grid(row=1, column=0, sticky="ew", pady=3, padx=(0, 2))

        # Torrent publisher list
        if True:
            table = ScrollableFrame(self.ddlWindow, bg=self.colors["Gray3"])
            table.grid_columnconfigure(0, weight=1)
            table.grid(row=2)

            self.ddlWindow.publisherData = {}
            self.ddlWindow.publisherButtons = {}
            # que = queue.Queue()
            # is_empty = True
            # t = threading.Thread(
            #     target=fetcher_handler, args=(fetcher, que, id), daemon=True)
            # t.start()
            # handler_loop(table, t, que, is_empty)
            search_handler(table, fetcher)
            # draw_table(table, fetcher)
