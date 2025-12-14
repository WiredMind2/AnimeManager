import json
import os
import queue
import re
import subprocess
import threading
import time
import traceback
from datetime import date, datetime
from datetime import time as datetime_time
from datetime import timedelta
from operator import itemgetter
from sqlite3 import OperationalError
from tkinter import (HORIZONTAL, Button, Canvas, Entry, Frame, Label, Listbox,
                     Menu, OptionMenu, PhotoImage, Scrollbar, StringVar,
                     TclError, Text, Tk, Toplevel)
from tkinter.ttk import Progressbar
from typing import Any, Callable

# Standardized import handling using importlib to avoid static analyzer package resolution issues
try:
    import importlib

    torrent_managers = importlib.import_module("AnimeManager.torrent_managers")
except Exception:
    try:
        # Try relative imports when running as a package
        from .. import torrent_managers
    except Exception:
        # Fallback to direct imports (module placed on sys.path)
        import torrent_managers

try:
    from AnimeManager.window_frames import RoundTopLevel
    from AnimeManager.menu_components import DropDownMenu
except Exception:
    try:
        from ..window_frames import RoundTopLevel
        from ..menu_components import DropDownMenu
    except Exception:
        from window_frames import RoundTopLevel
        from menu_components import DropDownMenu

# Resolve deep package-relative imports in environments where the package
# may not be available on sys.path (for example when running via
# "python launch" or from a frozen binary). Try absolute package imports
# first, then fall back to the already-imported modules or local modules.
try:
    # Prefer absolute imports using the package name
    from AnimeManager.torrent_managers.base import BaseTorrentManager
except Exception:
    try:
        # If running as a proper package, relative import may work
        from ..torrent_managers.base import BaseTorrentManager
    except Exception:
        # Fall back to the top-level module if it was added to sys.path
        from torrent_managers.base import BaseTorrentManager

try:
    # The db manager base class is named BaseDB in the module; alias it to
    # Database so the rest of the code keeps using the expected symbol.
    from AnimeManager.db_managers.base import BaseDB as Database
except Exception:
    try:
        from ..db_managers.base import BaseDB as Database
    except Exception:
        from db_managers.base import BaseDB as Database

try:
    # The file manager base class is named BaseFileManager; alias it to
    # FileManager to keep compatibility with existing annotations/usages.
    from AnimeManager.file_managers.base import BaseFileManager as FileManager
except Exception:
    try:
        from ..file_managers.base import BaseFileManager as FileManager
    except Exception:
        from file_managers.base import BaseFileManager as FileManager

try:
    from AnimeManager.animeAPI.APIUtils import APIUtils as API
except Exception:
    try:
        from ..animeAPI.APIUtils import APIUtils as API
    except Exception:
        from animeAPI.APIUtils import APIUtils as API


class Options:
    def __init__(self):
        # Initialize commonly-used attributes so static analysis recognizes them.
        self.animeHashes: dict[str, set] = {}
        self.optionsWindow: "Toplevel | None" = None
        self.tm: "BaseTorrentManager | None" = None
        self.database: "Database | None" = None
        self.api: "API | None" = None
        self.colors: dict[str, str] = {}
        self.iconPath: str = ""
        self.animePath: str = ""
        self.fm: "FileManager | None" = None
        self.animeList: "Listbox | None" = None
        # Provide a no-op logger until real logger is attached
        self.log: Callable[..., None] = lambda *args, **kwargs: None
        self.player: Callable[..., None] | None = None
        self.dbPath: str = ""
        self.RPC_stop_watching: Callable[..., None] = lambda *args, **kwargs: None
        self.RPC_watching: Callable[..., None] = lambda *args, **kwargs: None
        self.getEpisodes: Callable[..., list[dict]] = lambda *args, **kwargs: []
        self.getTorrents: Callable[..., list[dict]] = lambda *args, **kwargs: []
        self.getFolder: Callable[..., str] = lambda *args, **kwargs: ""
        self.getImage: Callable[..., PhotoImage] = lambda *args, **kwargs: PhotoImage()
        # getTorrentsProgress is implemented as a method later in this class
        self.initWindow: Callable[..., None] = lambda *args, **kwargs: None
        self.infoWindowMinWidth: int = 400
        self.infoWindowMinHeight: int = 300

        # Additional placeholders to satisfy static analyzer for dynamic UI callbacks
        self.downloadFile: Callable[..., None] = lambda *args, **kwargs: None
        self.drawTextPopupWindow: Callable[..., None] = lambda *args, **kwargs: None
        self.tagcolors: dict[str, str] = {}
        self.tag_options: dict[str, Any] = {}
        self.drawDdlWindow: Callable[..., None] = lambda *args, **kwargs: None
        self.drawTorrentFilesWindow: Callable[..., None] = lambda *args, **kwargs: None
        self.get_relations: Callable[..., list] = lambda *args, **kwargs: []
        self.getStatus: Callable[..., None] = lambda *args, **kwargs: None
        self.dateStates: dict[str, Any] = {}

        # More placeholders for dynamic attributes used throughout the class
        self.root: "Tk | None" = None
        self.closing: bool = False
        self.logs: dict[str, Any] = {}
        self.actionButtons: list[Button] = []
        self.getDateText: Callable[..., list[str]] = lambda *args, **kwargs: []
        self.getDatabase: Callable[..., "Database"] = lambda *args, **kwargs: None

    def drawOptionsWindow(self, id, user_id=None):
        # Functions
        if True:

            def findTorrent(id):
                if self.animeHashes.get(id):
                    return

                torrents = self.getTorrentsProgress(id)

                if len(torrents) == 0:
                    self.animeHashes[id] = None
                    return

                self.animeHashes[id] = set(map(lambda t: t.hash, torrents))
                self.optionsWindow.after(10, self.reload, id, False)

            def updateLoadingBar(id, bar, text):
                hashes = self.animeHashes.get(id, None)

                if hashes is None:
                    return

                try:
                    torrents = self.tm.list(hashes=hashes)
                except torrent_managers.TorrentException as e:
                    self.log("NETWORK", f"[ERROR] - {str(e)}")
                    value = 100
                else:
                    if len(torrents) == 0:
                        value = 100
                    else:
                        div = sum(map(lambda t: t.size, torrents))
                        if div > 0:
                            value = (
                                sum(map(lambda t: t.downloaded, torrents)) / div * 100
                            )
                        else:
                            value = 0
                        # value = torrent.downloaded / torrent.size * 100

                if value == 100:
                    self.animeHashes[id] = None
                    self.reload(id, update=False)
                else:
                    try:
                        bar["value"] = value
                        # TODO - Fill with zeros
                        text.configure(text=str(round(value, 2)) + "%")
                    except Exception:
                        pass
                    self.optionsWindow.after(500, updateLoadingBar, id, bar, text)

            def updateEpisodes(epsList, title, folder):
                eps = self.getEpisodes(folder)
                self.log(
                    "MEDIA_PLAYERS",
                    f"updateEpisodes called for title={title} folder={folder} eps_count={len(eps) if eps is not None else 0}",
                )
                if len(eps) >= 1 and list(eps)[0] is not None:
                    titles = [e["title"] for e in eps]
                    state = "normal"
                else:
                    titles = []
                    state = "disabled"

                if not "var" in epsList.__dict__:
                    # Was probably removed
                    return
                var = epsList.var

                epsList.configure(
                    *titles,
                    # Pass the selected file string (var.get()) to watch; previous code passed
                    # the event object in some cases, causing scoping issues and NameError.
                    command=lambda selected, title=title, var=var: watch(
                        title, selected, eps, var
                    ),
                    state=state,
                )

                colorFileEntries(id, eps, epsList)
                epsList.bind(
                    "<Button-1>",
                    lambda e, a=id, b=eps, c=epsList: colorFileEntries(a, b, c),
                )

            def colorFileEntries(id, eps, epsList):
                last_seen = self.getDatabase().get(id=id, table="anime")["last_seen"]
                if len(eps) >= 1 and list(eps)[0] is not None:
                    path_list = [i["path"] for i in eps]
                else:
                    path_list = []
                if last_seen is not None and last_seen in path_list:
                    for i in range(path_list.index(last_seen) + 1):
                        epsList.menu.entryconfig(i, foreground=self.colors["Green"])

            def like(id, b):
                liked = bool(self.getDatabase().get(id=id, table="anime").like)
                self.getDatabase().set(
                    {"id": id, "like": not liked}, table="anime", get_output=False
                )

                if not liked:
                    im_path = os.path.join(self.iconPath, "heart.png")
                else:
                    im_path = os.path.join(self.iconPath, "heart(1).png")

                folder = self.getFolder(id)
                showFolderButtons = folder is not None and self.fm.isdir(
                    self.animePath + "/" + folder
                )

                iconSize = (50, 50) if showFolderButtons else (30, 30)
                image = self.getImage(im_path, iconSize)
                b.configure(image=image)
                b.image = image

                for lbl in self.animeList.winfo_children():
                    if lbl.winfo_class() == "Label" and lbl.name == str(id):
                        text = lbl.cget("text").replace(" ❤", "")
                        if not liked:
                            text += " ❤"
                        lbl["text"] = text
                        break

            def watch(title, file, eps, var):
                self.log(
                    "MAIN_STATE",
                    f"watch() invoked for title={title} file={file} eps_len={len(eps) if eps is not None else 0}",
                )
                # Prepare playback variables
                var.set("Watch")
                video = [i["title"] for i in eps].index(file)
                playlist = [i["path"] for i in eps]
                self.log("MAIN_STATE", "Watching", file)
                # RPC and playback: make sure these run with locals in scope
                try:
                    self.RPC_watching(title, eps=[video + 1, len(eps)])
                    # Ensure a player is configured and callable
                    if hasattr(self, "player") and callable(self.player):
                        # Log debug info about the configured player
                        try:
                            self.log(
                                "MEDIA_PLAYERS", "Invoking player:", repr(self.player)
                            )
                        except Exception:
                            pass
                        # Try an in-process start first to surface exceptions in the main log
                        try:
                            self.player(
                                playlist,
                                video,
                                id,
                                self.dbPath,
                                callback=self.RPC_stop_watching,
                                method="NONE",
                            )
                        except Exception:
                            # Log the full traceback and then fall back to spawning the player normally
                            self.log(
                                "MAIN_STATE",
                                "[ERROR] - In-process player start failed:",
                                traceback.format_exc(),
                            )
                            try:
                                self.player(
                                    playlist,
                                    video,
                                    id,
                                    self.dbPath,
                                    callback=self.RPC_stop_watching,
                                )
                            except Exception:
                                self.log(
                                    "MAIN_STATE",
                                    "[ERROR] - Spawned player startup also failed:",
                                    traceback.format_exc(),
                                )
                    else:
                        # No player configured: fallback to opening the file with the OS default
                        try:
                            import webbrowser

                            self.log(
                                "MAIN_STATE",
                                "[ERROR] - No media player configured, opening with system default",
                            )
                            webbrowser.open(playlist[video])
                        except Exception as e:
                            self.log(
                                "MAIN_STATE",
                                "[ERROR] - Failed to open file with system default:",
                                str(e),
                            )
                except Exception:
                    # Don't let an exception in playback crash the tkinter mainloop
                    self.log(
                        "MAIN_STATE",
                        "[ERROR] - Exception while trying to play:",
                        traceback.format_exc(),
                    )

            def ddlFromUrl(id):
                def callback(var, id):
                    url = var.get()
                    self.downloadFile(id, url=url)

                self.drawTextPopupWindow(
                    self.optionsWindow,
                    "Enter torrent url",
                    lambda var, id=id: callback(var, id),
                    fentype="TEXT",
                )

            def tag(id, tag, user_id=None):
                self.set_tag(id, tag, user_id)

                for lbl in self.animeList.winfo_children():
                    if lbl.winfo_class() == "Label" and lbl.name == str(id):
                        lbl.configure(fg=self.colors[self.tagcolors[tag]])
                        break
                self.reload(id, False)

            def trailer(id):
                trailer = anime.trailer
                if trailer is not None:
                    self.log(
                        "MAIN_STATE",
                        "Watching trailer for anime",
                        anime.title,
                        "url",
                        trailer,
                    )
                    self.player((trailer,), 0, url=True)

            def switch(id, titles=None):
                if titles is not None:
                    id = titles[id]
                self.optionsWindow.clear()
                self.drawOptionsWindow(id)

            def dataUpdate(id):
                data = self.api.anime(id)

                if "status" in data.keys() and data.status != "UPDATE":
                    self.optionsWindow.after(10, self.reload, id)

        # Window init - Fancy corners - Main frame
        if True:
            if user_id is None:
                user_id = 4

            with self.getDatabase():
                anime = self.getDatabase().get(id=id, table="anime")

                if anime.title is None:
                    # No data found??
                    self.getDatabase().save()

                    anime = self.getDatabase().get(id=id, table="anime")
                    if anime.title is None:
                        # Anime doesn't exists anymore
                        return

                # TODO - Get rid of that
                data = self.getDatabase().sql(
                    "SELECT tag, liked from user_tags WHERE anime_id=:anime_id AND user_id=:user_id",
                    {"anime_id": id, "user_id": user_id},
                )
                if data:
                    anime.tag, anime.like = data[0]

            if anime.status == "UPDATE" or len(anime.keys()) == 0 or not anime.synopsis:
                threading.Thread(target=dataUpdate, args=(id,), daemon=True).start()

            if len(anime.keys()) == 0:
                anime.title = "Loading..."

            if self.optionsWindow is None or not self.optionsWindow.winfo_exists():
                size = (self.infoWindowMinWidth, self.infoWindowMinHeight)
                self.optionsWindow = RoundTopLevel(
                    self.initWindow,
                    title=anime.title,
                    minsize=size,
                    bg=self.colors["Gray2"],
                    fg=self.colors["Gray3"],
                )
                self.optionsWindow.titleLbl.configure(
                    fg=self.colors[self.tagcolors[anime.tag]]
                )
            else:
                self.optionsWindow.clear()
                self.optionsWindow.titleLbl.configure(
                    text=anime.title,
                    bg=self.colors["Gray2"],
                    fg=self.colors[self.tagcolors[anime.tag]],
                    font=("Source Code Pro Medium", 18),
                )

        # Title - File buttons
        if True:
            titleFrame = Frame(self.optionsWindow, bg=self.colors["Gray2"])

            if self.animeHashes.get(id):
                offRow = 1
                bar = Progressbar(titleFrame, orient=HORIZONTAL, mode="determinate")
                bar.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=2, pady=2)
                text = Label(
                    titleFrame,
                    text="0%",
                    bg=self.colors["Gray2"],
                    fg=self.colors["Gray4"],
                    font=("Source Code Pro Medium", 15),
                )
                text.grid(row=0, column=2, padx=10)

                updateLoadingBar(id, bar, text)
            else:
                offRow = 0
            b = Button(
                titleFrame,
                text="Download torrents",
                bd=0,
                height=1,
                relief="solid",
                font=("Source Code Pro Medium", 13),
                activebackground=self.colors["Gray2"],
                activeforeground=self.colors["White"],
                bg=self.colors["Gray3"],
                fg=self.colors["White"],
                command=lambda id=id: self.drawDdlWindow(id),
            )
            b.bind("<Button-3>", lambda e, id=id: ddlFromUrl(id))
            b.grid(row=1 + offRow, column=0, sticky="nsew", padx=2, pady=2)

            kwargs = {
                "bd": 0,
                "height": 1,
                "relief": "solid",
                "font": ("Source Code Pro Medium", 13),
                "activebackground": self.colors["Gray2"],
                "activeforeground": self.colors["White"],
                "bg": self.colors["Gray3"],
                "fg": self.colors["White"],
            }

            Button(
                titleFrame,
                text="Manage torrents",
                command=lambda id=id: self.drawTorrentFilesWindow(id),
                **kwargs,
            ).grid(row=1 + offRow, column=1, sticky="nsew", padx=2, pady=2)

            folder = self.getFolder(id)
            showFolderButtons = folder is not None and self.fm.exists(folder)
            if showFolderButtons:
                command = (  # TODO - How to deal with this with FTP?
                    "explorer " '"{}"'.format(os.path.abspath(folder))
                )
                Button(
                    titleFrame,
                    text="Open folder",
                    command=lambda c=command: subprocess.run(c),
                    **kwargs,
                ).grid(row=2 + offRow, column=0, sticky="nsew", padx=2, pady=2)

                titles = []
                state = "normal"

                var = StringVar()
                var.set("Watch")
                epsList = DropDownMenu(
                    titleFrame,
                    var,
                    *titles,
                    scrollbar=True,
                    state=state,
                    highlightthickness=0,
                    borderwidth=0,
                    **kwargs,
                )
                epsList.menu.configure(
                    bd=0,
                    borderwidth=0,
                    font=("Source Code Pro Medium", 13),
                    activebackground=self.colors["Gray3"],
                    activeforeground=self.colors["White"],
                    bg=self.colors["Gray2"],
                    fg=self.colors["White"],
                    thickness=20,
                    padx=20,
                    sb_fg=self.colors["Gray3"],
                )
                epsList.menu.root_configure(
                    borderwidth=2, fg=self.colors["Gray3"], bg=self.colors["Gray2"]
                )
                epsList.grid(row=2 + offRow, column=1, sticky="nsew", padx=2, pady=2)
                setattr(epsList, "var", var)

                self.optionsWindow.after(
                    10,
                    lambda a=epsList, b=anime.title, c=folder: updateEpisodes(a, b, c),
                )

            [titleFrame.grid_columnconfigure(i, weight=1) for i in range(2)]

            iconSize = (50, 50) if showFolderButtons else (30, 30)
            if bool(anime.like):
                image = self.getImage(
                    os.path.join(self.iconPath, "heart.png"), iconSize
                )
            else:
                image = self.getImage(
                    os.path.join(self.iconPath, "heart(1).png"), iconSize
                )
            likeButton = Button(
                titleFrame,
                image=image,
                bd=0,
                relief="solid",
                activebackground=self.colors["Gray2"],
                activeforeground=self.colors["White"],
                bg=self.colors["Gray2"],
                fg=self.colors["White"],
            )
            likeButton.configure(command=lambda id=id, b=likeButton: like(id, b))
            setattr(likeButton, "image", image)
            likeButton.grid(row=1 + offRow, column=2, rowspan=2, sticky="nsew", padx=5)
            titleFrame.grid(row=0, column=0, sticky="nsew")

        # Tags
        if True:
            tags = Frame(self.optionsWindow, bg=self.colors["Gray2"])
            Label(
                tags,
                text="Tag as:",
                bg=self.colors["Gray2"],
                fg=self.colors["Gray4"],
                font=("Source Code Pro Medium", 15),
            ).grid(row=0, column=0, pady=10)
            i = -1
            for i, data in enumerate(self.tag_options.items()):
                tag_txt, color, tag_filter = (
                    data[0],
                    data[1]["color"],
                    data[1]["filter"],
                )
                Button(
                    tags,
                    text=tag_txt,
                    bd=0,
                    height=1,
                    relief="solid",
                    font=("Source Code Pro Medium", 13),
                    activebackground=self.colors["Gray2"],
                    activeforeground=self.colors["Green"],
                    bg=self.colors["Gray2"],
                    fg=self.colors[color],
                    command=lambda id=id, tag_filter=tag_filter, user_id=user_id: tag(
                        id, tag_filter, user_id
                    ),
                ).grid(row=0, column=1 + i, sticky="nsew", padx=5)

            if anime.trailer is not None:
                Label(
                    tags,
                    text="-",
                    bg=self.colors["Gray2"],
                    fg=self.colors["Gray4"],
                    font=("Source Code Pro Medium", 13),
                ).grid(row=0, column=i + 2, pady=5)
                Button(
                    tags,
                    text="Watch trailer",
                    bd=0,
                    height=1,
                    relief="solid",
                    font=("Source Code Pro Medium", 13),
                    activebackground=self.colors["Gray2"],
                    activeforeground=self.colors["White"],
                    bg=self.colors["Gray2"],
                    fg=self.colors["White"],
                    command=lambda id=id: trailer(id),
                ).grid(row=0, column=i + 3, sticky="nsew", padx=5)
            tags.grid(row=3, column=0)

        # Synopsis
        if True:
            if anime.synopsis not in ("", None):
                synopsis = Label(
                    self.optionsWindow,
                    text=anime.synopsis,
                    wraplength=900,
                    font=("Source Code Pro Medium", 10),
                    bg=self.colors["Gray2"],
                    fg=self.colors["White"],
                )
            else:
                synopsis = Label(
                    self.optionsWindow,
                    text="No synopsis",
                    wraplength=900,
                    font=("Source Code Pro Medium", 10),
                    bg=self.colors["Gray2"],
                    fg=self.colors["White"],
                )
            synopsis.grid(row=4, column=0)

        # Secondary infos
        if True:
            secondInfos = Frame(self.optionsWindow, bg=self.colors["Gray2"])
            if anime.episodes is not None:
                text = str(anime.episodes) + " episode{}".format(
                    "s" if anime.episodes > 1 else ""
                )
                episodes = Label(
                    secondInfos,
                    text=text,
                    font=("Source Code Pro Medium", 10),
                    bg=self.colors["Gray2"],
                    fg=self.colors["White"],
                )
            else:
                episodes = Label(
                    secondInfos,
                    text="No episodes",
                    font=("Source Code Pro Medium", 10),
                    bg=self.colors["Gray2"],
                    fg=self.colors["White"],
                )
            if anime.rating is not None and anime.rating != "None":
                rating = Label(
                    secondInfos,
                    text="Rating: " + anime.rating,
                    font=("Source Code Pro Medium", 10),
                    bg=self.colors["Gray2"],
                    fg=self.colors["White"],
                )
            else:
                rating = Label(
                    secondInfos,
                    text="No rating",
                    font=("Source Code Pro Medium", 10),
                    bg=self.colors["Gray2"],
                    fg=self.colors["White"],
                )
            if anime.duration not in (None, "None", "Unknown"):
                text = (
                    "("
                    + str(anime.duration)
                    + " min{})".format(
                        " each"
                        if anime.episodes is not None and anime.episodes > 1
                        else ""
                    )
                )
                duration = Label(
                    secondInfos,
                    text=text,
                    font=("Source Code Pro Medium", 10),
                    bg=self.colors["Gray2"],
                    fg=self.colors["White"],
                )
            else:
                duration = Label(
                    secondInfos,
                    text="(Unknown duration)",
                    font=("Source Code Pro Medium", 10),
                    bg=self.colors["Gray2"],
                    fg=self.colors["White"],
                )

            rating.grid(row=0, column=0)
            Label(
                secondInfos,
                text="-",
                font=("Source Code Pro Medium", 10),
                bg=self.colors["Gray2"],
                fg=self.colors["White"],
            ).grid(row=0, column=1)
            episodes.grid(row=0, column=2)
            duration.grid(row=0, column=3)
            secondInfos.grid(row=5, column=0)

        # Genres
        if True:
            genresFrame = Frame(self.optionsWindow, bg=self.colors["Gray2"])
            genres = anime.genres

            all_genres = dict(
                self.getDatabase().sql("SELECT id, name FROM genresIndex")
            )  # This is like, VERY bad

            lbl = None
            for genre_id in genres:
                txt = all_genres.get(genre_id)
                if txt is None or txt == "NONE":
                    txt = "Unknown"
                Label(
                    genresFrame,
                    text=txt,
                    bd=0,
                    height=1,
                    font=("Source Code Pro Medium", 13),
                    bg=self.colors["Gray2"],
                    fg=self.colors["Gray"],
                ).pack(side="left")
                lbl = Label(
                    genresFrame,
                    text=" - ",
                    bd=0,
                    height=1,
                    font=("Source Code Pro Medium", 13),
                    bg=self.colors["Gray2"],
                    fg=self.colors["Gray"],
                )
                lbl.pack(side="left")
            if len(genres) >= 1 and lbl is not None:
                lbl.pack_forget()
            genresFrame.grid(row=6, column=0, pady=10)

        # Relations
        if True:
            relationsFrame = Frame(self.optionsWindow, bg=self.colors["Gray2"])
            relations = self.get_relations(id, type="anime")
            column = 0
            relations = sorted(relations, key=itemgetter("name"))
            with self.getDatabase():
                lbl = None
                for relation in relations:
                    rel_ids = relation["rel_id"]
                    sql = (
                        "SELECT title,id FROM anime WHERE id IN ("
                        + ",".join("?" * len(rel_ids))
                        + ");"
                    )
                    # TODO - Only do a single call to db
                    titles = dict(self.getDatabase().sql(sql, rel_ids))
                    text = relation["name"].title().replace("_", " ")
                    rel_tag = self.getDatabase().sql(
                        "SELECT tag FROM user_tags WHERE user_id=:user_id AND anime_id=:anime_id",
                        {"user_id": user_id, "anime_id": rel_ids[0]},
                    )
                    if len(rel_tag) == 0:
                        rel_tag = "NONE"
                    else:
                        rel_tag = rel_tag[0][0]
                    if len(titles) == 1:
                        Button(
                            relationsFrame,
                            text=text,
                            bd=0,
                            height=1,
                            relief="solid",
                            font=("Source Code Pro Medium", 13),
                            activebackground=self.colors["Gray2"],
                            activeforeground=self.colors["Red"],
                            bg=self.colors["Gray2"],
                            fg=self.colors[self.tagcolors[rel_tag]],
                            command=lambda ids=rel_ids: switch(ids[0]),
                        ).grid(row=0, column=column)
                    elif len(titles) > 1:
                        var = StringVar()
                        var.set(text)
                        # if len(titles) == 1:
                        relList = OptionMenu(
                            relationsFrame,
                            var,
                            *titles.keys(),
                            command=lambda e, titles=titles: switch(e, titles),
                        )
                        relList.configure(
                            indicatoron=False,
                            highlightthickness=0,
                            borderwidth=0,
                            font=("Source Code Pro Medium", 13),
                            activebackground=self.colors["Gray2"],
                            activeforeground=self.colors["White"],
                            bg=self.colors["Gray2"],
                            fg=self.colors["White"],
                        )
                        relList["menu"].configure(
                            bd=0,
                            borderwidth=0,
                            activeborderwidth=0,
                            font=("Source Code Pro Medium", 13),
                            activebackground=self.colors["Gray3"],
                            activeforeground=self.colors["White"],
                            bg=self.colors["Gray2"],
                            fg=self.colors["White"],
                        )
                        relList.grid(row=0, column=column)

                        for i, rel_id in enumerate(rel_ids):
                            relList["menu"].entryconfig(
                                i,
                                foreground=self.colors[
                                    self.tagcolors[
                                        rel_tag
                                    ]  # TODO - Really rel_tag or not?
                                ],
                            )
                    else:
                        self.log(
                            "ERROR",
                            "id:{}, rel_ids:{}, titles:{}".format(
                                str(id), str(rel_ids), str(titles)
                            ),
                        )
                        # raise Exception("ERROR - id:{}, rel_ids:{}, titles:{}".format(str(id),str(rel_ids),str(titles)))

                    if len(titles) > 0:
                        column += 1
                        lbl = Label(
                            relationsFrame,
                            text="-",
                            bd=0,
                            height=1,
                            font=("Source Code Pro Medium", 13),
                            bg=self.colors["Gray2"],
                            fg=self.colors["Gray"],
                        )
                        lbl.grid(row=0, column=column)
                        column += 1

            if column > 0:
                if lbl is not None:
                    lbl.grid_forget()

            relationsFrame.grid(row=7, column=0)

        # State
        if True:
            state = Frame(self.optionsWindow, bg=self.colors["Gray2"])
            datefrom, dateto = anime.date_from, anime.date_to
            if dateto == "None":
                # TODO - Fix that
                dateto = None
                self.log(
                    "MAIN_STATE",
                    f'Anime {anime.title} has "None" instead of None in dateto field',
                )
            if datefrom is not None:
                datefrom = datetime.utcfromtimestamp(datefrom)
            if dateto is not None:
                dateto = datetime.utcfromtimestamp(dateto)

            status = self.getStatus(anime)
            Label(
                state,
                text="Status:",
                bg=self.colors["Gray2"],
                fg=self.colors["Gray4"],
                font=("Source Code Pro Medium", 15),
            ).grid(row=0, column=0, sticky="e")
            statusLbl = Label(
                state,
                text=self.dateStates[status]["text"],
                bg=self.colors["Gray2"],
                fg=self.colors[self.dateStates[status]["color"]],
                font=("Source Code Pro Medium", 13),
            )
            statusLbl.grid(row=0, column=1, sticky="w")
            dateLbl = Label(
                state,
                text="",
                bg=self.colors["Gray2"],
                fg=self.colors[self.dateStates[status]["color"]],
                font=("Source Code Pro Medium", 13),
            )
            if status != "UNKNOWN" and datefrom is not None:
                dateLbl["text"] = "\n".join(self.getDateText(anime))
                dateLbl.grid(row=1, column=0, columnspan=2)
            state.grid(row=8, column=0)

        # Actions
        if True:
            actions = Frame(self.optionsWindow, bg=self.colors["Gray2"])
            i = -1
            for i, data in enumerate(self.actionButtons):
                Button(
                    actions,
                    text=data["text"],
                    bd=0,
                    height=1,
                    relief="solid",
                    font=("Source Code Pro Medium", 13),
                    activebackground=self.colors["Gray2"],
                    activeforeground=self.colors[data["color"]],
                    bg=self.colors["Gray2"],
                    fg=self.colors[data["color"]],
                    command=lambda c=data["command"], id=id: c(id),
                ).grid(row=0, column=i * 2)
                if i < len(self.actionButtons) - 1:
                    Label(
                        actions,
                        text="-",
                        bd=0,
                        height=1,
                        font=("Source Code Pro Medium", 13),
                        bg=self.colors["Gray2"],
                        fg=self.colors["Gray"],
                    ).grid(row=0, column=i * 2 + 1)

            actions.grid(row=9, column=0)

        if id not in self.animeHashes:
            t = threading.Thread(target=findTorrent, args=(id,), daemon=True)
            t.start()

        self.optionsWindow.update_events()

    def copy_title(self, id):
        database = self.getDatabase()
        self.root.clipboard_clear()
        title = database(id=id, table="anime")["title"]
        self.root.clipboard_append(title)

    def reload(self, id, update=True):
        def wait_for_thread(t, cb=None):
            if t.is_alive():
                self.optionsWindow.after(500, wait_for_thread, t, cb)
            elif cb:
                cb()

        def finish_reload():
            if (
                self.closing
                or self.optionsWindow is None
                or not self.optionsWindow.winfo_exists()
            ):
                return

            self.optionsWindow.clear()
            self.drawOptionsWindow(id)

            self.log(
                "TIME",
                "Reloading:".ljust(25),
                round(time.time() - self.reload_start, 2),
                "sec",
            )

        if "TIME" in self.logs:
            self.reload_start = time.time()

        # thread_files = threading.Thread(
        # 	target=self.regroupFiles, args=(True,), daemon=True)
        # thread_files.start()

        # waiter = lambda thread_files=thread_files: wait_for_thread(thread_files, finish_reload)

        if update:
            thread_data = threading.Thread(
                target=self.api.anime, args=(id,), daemon=True
            )
            thread_data.start()
            wait_for_thread(thread_data, finish_reload)

        else:
            finish_reload()

    def set_tag(self, id, tag, user_id=None):
        if user_id is None:
            # Local user is user 0, cuz why not
            user_id = 0

        with self.getDatabase().get_lock():
            sql = "SELECT EXISTS(SELECT 1 FROM user_tags WHERE user_id = :user_id AND anime_id = :anime_id)"
            exists = bool(
                self.getDatabase().sql(sql, {"user_id": user_id, "anime_id": id})[0][0]
            )
            if exists:
                sql = "UPDATE user_tags SET tag=:tag WHERE user_id = :user_id AND anime_id = :anime_id"
            else:
                sql = "INSERT INTO user_tags(user_id, anime_id, tag) VALUES (:user_id, :anime_id, :tag)"

            self.getDatabase().sql(
                sql, {"user_id": user_id, "anime_id": id, "tag": tag}, save=True
            )
            # self.database.set(
            # 	{"user_id": user_id, "anime_id": id, "tag": tag}, table="user_tags", get_output=False
            # )
        pass

    def set_like(self, id, liked, user_id=None):
        if user_id is None:
            # Local user is user 0, cuz why not
            user_id = 0
        with self.getDatabase().get_lock():
            self.getDatabase().set(
                {"user_id": user_id, "anime_id": id, "liked": int(liked)},
                table="user_tags",
                get_output=False,
            )

    def deleteFiles(self, id, user_id=None):
        def clearFolder(path):
            self.log("DB_UPDATE", "Cleaning up folder:", path)
            try:
                # rd /S /Q "\\?\D:\Animes\folder."
                os.system('del /F /S /Q "{}"'.format(path))
            except Exception as e:
                self.log("DISK_ERROR", "Error while removing folder", path, e)
                raise
            c = 0
            while len(os.listdir(path)) != 0 and c < 10:
                time.sleep(1)
                c += 1
            if len(os.listdir(path)) == 0:
                os.rmdir(path)
                self.log("DB_UPDATE", "Deleted all files and removed folder")
            else:
                self.log(
                    "DISK_ERROR", "Some files haven't been removed from folder", path
                )

        path = self.getFolder(id) or ""

        if self.fm.exists(path):
            torrents = self.getTorrents(id)

            try:
                hashes = list(map(lambda t: t.hash, torrents))

                self.log(
                    "DB_UPDATE",
                    "Deleting",
                    path,
                    "-",
                    len(hashes),
                    "torrents to remove",
                )

                self.tm.delete(hashes=hashes)
            except torrent_managers.TorrentException:
                pass

            threading.Timer(1, clearFolder, (path,)).start()
        else:
            self.log("DISK_ERROR", "Folder path doesn't exist:", path)

        self.set_tag(id, "SEEN", user_id)

        for lbl in self.animeList.winfo_children():
            if lbl.winfo_class() == "Label" and lbl.name == str(id):
                lbl.configure(fg=self.colors[self.tagcolors["SEEN"]])
                break
        self.reload(id, False)

    def delete(self, id):
        self.log(
            "DB_UPDATE",
            f"Deleted {self.getDatabase().get(id=id, table='anime').get('title')}",
        )
        self.animeList.remove(id=id)
        self.getDatabase().remove(None, id=id, table="anime")
        self.optionsWindow.exit()

    def deleteSeenEpisodes(self, id):
        folder = self.getFolder(id)
        path = (self.animePath + "/" + folder) if folder is not None else ""

        if self.fm.exists(path):
            toDelete = []
            anime = self.getDatabase().get(id=id, table="anime")
            last_seen = anime.last_seen

            eps = self.getEpisodes(folder)
            if len(eps) >= 1 and list(eps)[0] is not None:
                path_map = {e["path"]: e for e in eps}
            else:
                path_map = {}

            if last_seen is not None and last_seen in path_map.keys():
                for p, e in path_map.items():
                    if p == last_seen:
                        break
                    toDelete.append(p)

            torrents = self.getTorrents(anime.id)

            try:
                hashes = torrents
                hashesToDelete = []

                for t_hash in hashes:
                    for f in self.tm.list(hashes=[t_hash]):
                        sub_p = path + "/" + f.name
                        if sub_p in toDelete:
                            hashesToDelete.append(t_hash)
                            break

                if len(toDelete) > 0:
                    self.log(
                        "DB_UPDATE",
                        "Deleting",
                        len(toDelete),
                        "files from",
                        path,
                        "-",
                        len(hashesToDelete),
                        "torrents to remove",
                    )

                    self.tm.delete(hashes=hashes)

                    cmd = 'del /F /Q "{}"'.format('" "'.join(toDelete))
                    try:
                        os.system(cmd)
                    except Exception:
                        self.log("DISK_ERROR", "Error while removing folder", path)
                        raise
                else:
                    self.log("DB_UPDATE", "No file to delete!")
            except torrent_managers.TorrentException as e:
                self.log("MAIN_STATE", str(e))
                return
        else:
            self.log("DISK_ERROR", "Folder path doesn't exist:", path)
        self.log("DB_UPDATE", "Deleted all files")
        self.reload(id, False)

    def getTorrentsProgress(self, id):
        torrents = self.getTorrents(id)
        if len(torrents) == 0:
            return []

        torrent_hashes = list(map(lambda t: t.hash, torrents))

        try:
            t_infos = self.tm.list(
                filter=torrent_managers.TorrentListFilter.DOWNLOADING,
                hashes=torrent_hashes,
            )
        except torrent_managers.TorrentException:
            return []
        else:
            return t_infos
