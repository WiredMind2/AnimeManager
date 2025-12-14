import os
import queue
import threading
from tkinter import Button, Frame, Label, TclError, Toplevel
from tkinter.filedialog import askopenfilenames

# Standardized import handling
try:
    # Try importing as package first
    from AnimeManager import search_engines
    from AnimeManager.window_frames import RoundTopLevel, ScrollableFrame
except ImportError:
    try:
        # Try relative imports
        from .. import search_engines
        from ..window_frames import RoundTopLevel, ScrollableFrame
    except ImportError:
        # Fallback to direct imports
        import search_engines
        from window_frames import RoundTopLevel, ScrollableFrame


class TorrentFiles:
    def drawTorrentFilesWindow(self, id):
        # Functions
        if True:

            def import_torrent(id):
                torrents = getTorrents(id)
                default = '"' + '" "'.join(torrents) + '"'
                filepaths = askopenfilenames(
                    parent=self.root,
                    title="Select torrents",
                    initialdir=self.animePath,
                    initialfile=default,
                    filetypes=[("Torrents files", (".torrent"))],
                )
                torrents = []
                for path in filepaths:  # TODO - Use torrent hash instead
                    torrents.append(path.rsplit("/")[-1])
                if len(torrents) >= 1:
                    database = self.getDatabase()
                    with database.get_lock():
                        for torrent in torrents:
                            self.saveTorrent(torrent, save=False)
                        database.save()

                self.drawTorrentFilesWindow(id)

            def getTorrents(id):
                return self.database.get_metadata(id, "torrents")

            def getTorrentsState(id):
                out = {}
                torrents = self.getTorrents(id)
                hashes = set(map(lambda t: t.hash, torrents))

                try:
                    data = self.tm.list(hashes=hashes)
                except torrent_managers.TorrentException as e:
                    self.log("MAIN_STATE", f"[ERROR] - {str(e)}")
                    return {}

                for t in data:
                    t_hash = t.hash
                    if t_hash in hashes:
                        hashes.remove(t_hash)

                        if t.downloaded == t.size:
                            state = "COMPLETE"
                        elif t.downloaded < t.size:
                            state = "DOWNLOADING"
                        else:
                            self.log(
                                "MAIN_STATE",
                                "[ERROR] - Unknown torrent state:",
                                t.state,
                                "for torrent:",
                                t.name,
                            )
                            state = "UNKNOWN"

                        out[t_hash] = {"name": t.name, "state": state}

                for t_hash in hashes:
                    out[t_hash] = {
                        "name": t_hash,
                        "state": "DELETED",
                    }  # TODO - Somehow get torrent name? -> Have to store it in db

                return out

            def updateTorrentsList():
                def handler(id, que):
                    try:
                        out = getTorrentsState(id)
                    except Exception as e:
                        que.put([])
                    else:
                        que.put(out)

                if self.torrentFilesWindow.torrent_thread is None:
                    que = queue.Queue()
                    t = threading.Thread(target=handler, args=(id, que), daemon=True)
                    t.start()
                    self.torrentFilesWindow.torrent_thread = t
                    self.torrentFilesWindow.torrent_que = que

                if self.torrentFilesWindow.torrent_que.empty():
                    self.torrentFilesWindow.after(100, updateTorrentsList)
                    return

                torrents = self.torrentFilesWindow.torrent_que.get()
                self.torrentFilesWindow.loading_label.destroy()
                if len(torrents) > 0:
                    for i, item in enumerate(torrents.items()):
                        t_hash, torrent = item
                        name = torrent["name"]
                        state = torrent["state"]
                        color = self.torrentsStateColors[state]
                        Label(
                            torrent_list_frame,
                            text=name,
                            bd=0,
                            height=1,
                            relief="solid",
                            font=("Source Code Pro Medium", 13),
                            bg=self.colors["Gray3"],
                            fg=self.colors[color],
                        ).grid(row=i, column=0, sticky="nsew", pady=3, ipady=8)
                        Button(
                            torrent_list_frame,
                            image=downloadIcon,
                            bd=0,
                            height=1,
                            relief="solid",
                            activebackground=self.colors["Gray2"],
                            bg=self.colors["Gray3"],
                            command=lambda id=id, t=name: download_torrent(id, t),
                        ).grid(row=i, column=1, sticky="nsew", pady=3, ipadx=5)
                        Button(
                            torrent_list_frame,
                            image=deleteIcon,
                            bd=0,
                            height=1,
                            relief="solid",
                            activebackground=self.colors["Gray2"],
                            bg=self.colors["Gray3"],
                            command=lambda id=id, h=t_hash, s=state: delete_torrent(
                                id, h, s
                            ),
                        ).grid(row=i, column=2, sticky="nsew", pady=3, ipadx=5)
                else:
                    Label(
                        torrent_list_frame,
                        text="No torrents yet",
                        bd=0,
                        height=1,
                        relief="solid",
                        font=("Source Code Pro Medium", 15),
                        bg=self.colors["Gray2"],
                        fg=self.colors["Gray4"],
                    ).grid(row=0, column=0, sticky="nsew", pady=15, ipady=8)

                torrent_list_frame.update_scrollzone()

            def download_torrent(id, t):
                self.downloadFile(id, hash=t)

                self.torrentFilesWindow.after(1000, self.drawTorrentFilesWindow, id)

            def delete_torrent(id, t_hash, state):
                # TODO - Broken
                self.log("DB_UPDATE", "Removing torrent", t_hash, "for id", id)

                if state in ("COMPLETE", "DOWNLOADING"):
                    try:
                        self.tm.delete(hashes=[t_hash])
                    except torrent_managers.TorrentException:
                        pass
                else:
                    database = self.getDatabase()
                    torrents = self.getTorrents(id)

                    if any(map(lambda t: t_hash == t.hash, torrents)):  # Disabled
                        with database.get_lock():
                            database.sql(
                                "DELETE FROM torrentsIndex WHERE id=? AND value=?",
                                (id, t_hash),
                            )
                            database.save()

                self.drawTorrentFilesWindow(id)

        # Main window
        if True:
            if (
                self.torrentFilesWindow is None
                or not self.torrentFilesWindow.winfo_exists()
            ):
                size = (
                    self.torrentFilesWindowMinWidth,
                    self.torrentFilesWindowMinHeight,
                )
                self.torrentFilesWindow = RoundTopLevel(
                    self.optionsWindow,
                    title="Torrents files",
                    minsize=size,
                    bg=self.colors["Gray2"],
                    fg=self.colors["Gray3"],
                )
            else:
                self.torrentFilesWindow.clear()
                self.torrentFilesWindow.focus()
            self.torrentFilesWindow.grid_rowconfigure(1, weight=1)
            [
                self.torrentFilesWindow.grid_columnconfigure(i, weight=1)
                for i in range(2)
            ]

        # Add/search torrent buttons
        if True:
            Button(
                self.torrentFilesWindow,
                text="Search torrent online",
                bd=0,
                height=1,
                relief="solid",
                font=("Source Code Pro Medium", 13),
                activebackground=self.colors["Gray2"],
                activeforeground=self.colors["Gray3"],
                bg=self.colors["Gray3"],
                fg=self.colors["White"],
                command=lambda id=id: self.search_torrent(id, self.torrentFilesWindow),
            ).grid(row=0, column=0, sticky="nsew", pady=3, padx=(0, 2))

            Button(
                self.torrentFilesWindow,
                text="Locate new torrent",
                bd=0,
                height=1,
                relief="solid",
                font=("Source Code Pro Medium", 13),
                activebackground=self.colors["Gray2"],
                activeforeground=self.colors["Gray3"],
                bg=self.colors["Gray3"],
                fg=self.colors["White"],
                command=lambda id=id: import_torrent(id),
            ).grid(row=0, column=1, sticky="nsew", pady=3, padx=(2, 0))

        # Torrents list
        if True:
            torrent_list_frame = ScrollableFrame(
                self.torrentFilesWindow, bg=self.colors["Gray2"], width=900
            )
            torrent_list_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
            torrent_list_frame.grid_columnconfigure(0, weight=1)

            downloadIcon = self.getImage(
                os.path.join(self.iconPath, "download.png"), (30, 30)
            )
            torrent_list_frame.downloadIcon = downloadIcon
            deleteIcon = self.getImage(
                os.path.join(self.iconPath, "delete.png"), (30, 30)
            )
            torrent_list_frame.deleteIcon = deleteIcon

            self.torrentFilesWindow.loading_label = Label(
                torrent_list_frame,
                text="Looking for torrents...",
                bd=0,
                height=1,
                relief="solid",
                font=("Source Code Pro Medium", 15),
                bg=self.colors["Gray2"],
                fg=self.colors["Gray4"],
            )
            self.torrentFilesWindow.loading_label.grid(
                row=0, column=0, sticky="nsew", pady=15, ipady=8
            )

            self.torrentFilesWindow.torrent_thread = None
            updateTorrentsList()
