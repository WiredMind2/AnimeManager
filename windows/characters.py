import io
import os
import queue
import threading
import time
from tkinter import Button, Canvas, Frame, Label, TclError

from PIL import Image, ImageTk

# Standardized import handling
try:
    # Try importing as package first
    from AnimeManager.window_frames import RoundTopLevel, ScrollableFrame
    from AnimeManager.classes import Character, CharacterList
except ImportError:
    try:
        # Try relative imports
        from ..window_frames import RoundTopLevel, ScrollableFrame
        from ..classes import Character, CharacterList
    except ImportError:
        # Fallback to direct imports
        from window_frames import RoundTopLevel, ScrollableFrame
        from classes import Character, CharacterList


class Characters:
    def drawCharactersWindow(self, id, update=True):
        # Functions
        if True:

            def characterCell(character, index, queue):
                size = (225, 310)
                cell = Frame(self.characterListTable, bg=self.colors["Gray3"])
                cell.grid_rowconfigure(0, weight=1)
                cell.grid_columnconfigure(0, weight=1)

                can = Canvas(
                    cell,
                    width=size[0],
                    height=size[1],
                    highlightthickness=0,
                    bg=self.colors["Gray3"],
                )
                can.grid(row=0, column=0, sticky="ns")
                can.bind(
                    "<Button-1>", lambda e, a=character: self.drawCharacterWindow(a)
                )

                can.create_image(0, 0, image=self.blank_image, anchor="nw")
                can.image = self.blank_image

                title = character.name
                if len(title) >= 20:
                    title = title[:15] + "..."
                if bool(character.like):
                    title += " ❤"
                color = "Blue" if character["role"] == "main" else "White"
                b = Button(
                    cell,
                    text=title,
                    bd=0,
                    height=1,
                    relief="solid",
                    font=("Source Code Pro Medium", 13),
                    activebackground=self.colors["Gray2"],
                    activeforeground=self.colors[color],
                    bg=self.colors["Gray3"],
                    fg=self.colors[color],
                    command=lambda a=character: self.drawCharacterWindow(a),
                )
                b.name = character["id"]
                b.grid(row=1, column=0, sticky="nsew")

                x, y = index // self.animePerRow, index % self.animePerRow
                cell.grid(row=x, column=y, sticky="nsew", pady=2, padx=2)

                filename = os.path.join(self.cache, "c" + str(character["id"]) + ".jpg")
                url = character.picture
                queue.put((filename, url, can))

                return cell

            def getCharacters(id):
                database = self.getDatabase()
                if id == "LIKED":
                    data = database.sql(
                        """
                        SELECT * FROM characters AS c 
                        LEFT JOIN characterRelations AS r 
                        ON c.id=r.id 
                        WHERE like = 1
                        GROUP BY c.id
                        ORDER BY anime_id;""",
                        to_dict=True,
                    )
                else:
                    data = database.sql(
                        "SELECT * FROM characters AS c LEFT JOIN characterRelations AS r ON c.id=r.id WHERE r.anime_id=?;",
                        (id,),
                        to_dict=True,
                    )
                # keys = list(self.database.keys(table="characters"))
                characters = CharacterList(
                    database.get_all_metadata(Character(c)) for c in data
                )
                return characters

            def reload(id, c):
                if getCharacters(id) != c:
                    self.characterListWindow.after(
                        1, self.drawCharactersWindow, id, False
                    )

            def update(id):
                parent.after(10, self.drawCharactersWindow, id)

            def loop_handler(id, t):
                if t.is_alive():
                    self.characterListWindow.after(500, loop_handler, id, t)
                else:
                    self.log("CHARACTERS", "Updating characters table")
                    draw_table()

            def draw_table():
                start = time.time()

                characters = getCharacters(id)

                que = queue.Queue()
                self.getElemImages(que)

                for x in range(self.animePerRow):
                    self.characterListTable.grid_columnconfigure(x, weight=1)

                # index = None
                # for index, character in enumerate(characters):
                def func(index, character):
                    if (
                        self.closing
                        or self.characterListWindow is None
                        or not self.characterListWindow.winfo_exists()
                    ):
                        return

                    if index == 0:
                        # First call
                        self.characterListTable.loadLbl.destroy()

                    cellData = self.characterListWindow.characterCells.get(index, None)
                    if cellData:
                        if cellData[0] == character.id:
                            return  # No need to create a new cell, skip
                        else:
                            cellData[1].destroy()

                    try:
                        cell = characterCell(character, index, que)
                    except Exception as e:
                        self.log(
                            "CHARACTER",
                            "[ERROR] - Can't create cell for character:",
                            character.name,
                            "-",
                            character.id,
                            "-",
                            e,
                        )
                        return

                    self.characterListWindow.characterCells[index] = (
                        character.id,
                        cell,
                    )

                    if index % self.animePerRow == 0:
                        self.characterListTable.update_scrollzone()

                def cb(index):
                    que.put("STOP")

                    if self.characterListTable.winfo_exists():
                        if index == -1:
                            # No characters found
                            self.characterListTable.loadLbl.destroy()

                            Label(
                                self.characterListTable,
                                text="No characters",
                                font=("Source Code Pro Medium", 18),
                                bg=self.colors["Gray3"],
                                fg=self.colors["Red"],
                            ).grid(
                                row=0,
                                column=0,
                                sticky="nsew",
                                pady=2,
                                padx=2,
                                columnspan=self.animePerRow,
                            )

                    self.characterListTable.update_scrollzone()
                    self.log(
                        "CHARACTER",
                        f"Updated characters grid in {round(time.time()-start, 2)}s",
                    )

                characters.map(
                    func, lambda func: self.characterListWindow.after(500, func), cb
                )

            def saveCharacters(id):
                # TODO - Move this directly in API
                database = self.getDatabase()
                characters = self.api.animeCharacters(id)

                # for character in characters:
                def func(index, character):
                    with database.get_lock():
                        # Check if character exists
                        sql = "SELECT EXISTS(SELECT 1 FROM characters WHERE id = ?);"
                        exists = bool(database.sql(sql, (character["id"],))[0][0])
                        if not exists:
                            # Save new character
                            self.log(
                                "CHARACTER",
                                "New character, anime id",
                                id,
                                "id",
                                character["id"],
                                "name",
                                character["name"],
                            )
                            sql = (
                                "INSERT INTO characters("
                                + ",".join(character.keys())
                                + ") VALUES ("
                                + ",".join("?" * len(character.keys()))
                                + ");"
                            )
                            database.sql(sql, character.values(), get_output=False)
                            database.save()
                        else:
                            # TODO - Update character data
                            pass

                characters.map(func, 0.5)

        # Main window - Fancy corners - Events
        if True:
            size = (self.characterListWindowMinWidth, self.characterListWindowMinHeight)
            if self.optionsWindow is not None and self.optionsWindow.winfo_exists():
                parent = self.optionsWindow
            else:
                parent = self.initWindow

            if (
                self.characterListWindow is None
                or not self.characterListWindow.winfo_exists()
            ):
                self.characterListWindow = RoundTopLevel(
                    parent,
                    title="Characters",
                    minsize=size,
                    bg=self.colors["Gray3"],
                    fg=self.colors["Gray2"],
                )
            else:
                self.characterListWindow.clear()
            # self.characterListWindow.titleLbl.configure(text="Characters", bg= self.colors['Gray3'], fg= self.colors['Gray2'], font=("Source Code Pro Medium",18))

            self.characterListWindow.characterCells = {}

            self.characterListTable = ScrollableFrame(
                self.characterListWindow, bg=self.colors["Gray3"]
            )
            self.characterListTable.pack(expand=True, fill="both")

            self.characterListTable.grid_columnconfigure(0, weight=1)

        # Data check
        if True:
            loadLbl = Label(
                self.characterListTable,
                text="Loading data...",
                bg=self.colors["Gray3"],
                fg=self.colors["Gray2"],
                font=("Source Code Pro Medium", 18),
            )
            loadLbl.grid(row=0, column=0, columnspan=self.animePerRow)
            self.characterListTable.loadLbl = loadLbl

        t = threading.Thread(target=saveCharacters, args=(id,), daemon=True)
        t.start()
        loop_handler(id, t)
