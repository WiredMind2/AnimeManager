import io
import os
import re
import threading
from tkinter import Button, Canvas, Frame, Label, TclError

import requests
from PIL import Image, ImageTk

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


class Character:
    def drawCharacterWindow(self, character, can_update=True):
        # Functions
        if True:

            def like(id, b):
                d = self.database(id=id, table="characters")
                liked = bool(d["like"])
                self.database.set({"id": id, "like": not liked}, table="characters")

                if not liked:
                    im_path = os.path.join(self.iconPath, "heart.png")
                else:
                    im_path = os.path.join(self.iconPath, "heart(1).png")

                iconSize = (30, 30)
                self.getImage(im_path, iconSize)
                b.configure(image=image)
                b.image = image

                for but in self.characterListTable.winfo_children():
                    if but.winfo_class() == "Button" and but.name == id:
                        text = but.cget("text").replace(" ❤", "")
                        if not liked:
                            text += " ❤"
                        but["text"] = text
                        break

            def switchAnime(id):
                try:
                    self.characterWindow.exit()
                except Exception:
                    pass
                try:
                    self.characterListWindow.exit()
                except Exception:
                    pass
                try:
                    self.reload(id, False)
                except Exception:
                    self.drawOptionsWindow(id)

            def update(id):
                c = self.api.character(id)

                try:
                    self.characterWindow.after(10, self.drawCharacterWindow, c, False)
                except Exception:
                    pass

        # Main window - Fancy corners - Events
        if True:
            size = (
                self.characterWindowWindowMinWidth,
                self.characterWindowWindowMinHeight,
            )
            if self.characterWindow is None or not self.characterWindow.winfo_exists():
                self.characterWindow = RoundTopLevel(
                    self.characterListWindow,
                    title="Loading data...",
                    minsize=size,
                    bg=self.colors["Gray2"],
                    fg=self.colors["Gray3"],
                )
            else:
                self.characterWindow.clear()
            self.characterWindow.grid_rowconfigure(1, weight=1)
            self.characterWindow.grid_columnconfigure(1, minsize=250, weight=1)

        # Data check
        if True:
            if can_update and not character.get("desc"):
                thread = threading.Thread(
                    target=update, args=(character.id,), daemon=True
                )
                thread.start()

        # Picture
        if True:
            filename = os.path.join(self.cache, "c" + str(character["id"]) + ".jpg")

            if "c" + str(character["id"]) + ".jpg" in os.listdir(self.cache):
                image = self.getImage(filename)
            else:
                raw_data = requests.get(character["picture"]).content
                im = Image.open(io.BytesIO(raw_data))
                im = im.resize((225, 310))
                if im.mode != "RGB":
                    im = im.convert("RGB")
                im.save(filename)

                image = ImageTk.PhotoImage(im)

            try:
                can = Canvas(
                    self.characterWindow,
                    width=225,
                    height=310,
                    highlightthickness=0,
                    bg=self.colors["Gray3"],
                )
                can.grid(row=0, column=0, rowspan=2)
                can.create_image(0, 0, image=image, anchor="nw")
                can.image = image
            except Exception as e:
                self.log(
                    "MAIN_STATE", "Error while creating characterWindow window:", e
                )
                try:
                    self.characterWindow.exit()
                except Exception:
                    pass
                return

        # Title panel
        if True:
            self.characterWindow.titleFrame.destroy()
            titleFrame = Frame(self.characterWindow, bg=self.colors["Gray2"])
            titleFrame.grid_columnconfigure(0, weight=1)
            self.characterWindow.titleFrame = titleFrame

            titleLbl = Label(
                titleFrame,
                text=character["name"],
                wraplength=500,
                bg=self.colors["Gray2"],
                font=("Source Code Pro Medium", 18),
                fg=self.colors["Blue" if character.get("role") == "Main" else "White"],
            )
            titleLbl.grid(row=0, column=0, sticky="nsew", columnspan=2)

            self.characterWindow.titleLbl = titleLbl
            self.characterWindow.handles = [titleLbl]

            if bool(character.like):
                im_path = os.path.join(self.iconPath, "heart.png")
            else:
                im_path = os.path.join(self.iconPath, "heart(1).png")
            iconSize = (30, 30)
            image = self.getImage(im_path, iconSize)

            # TODO - Handle multiple animes
            if "anime_id" in character.keys():
                Button(
                    titleFrame,
                    text="Go to anime",
                    bd=0,
                    height=1,
                    relief="solid",
                    font=("Source Code Pro Medium", 13),
                    activebackground=self.colors["Gray2"],
                    activeforeground=self.colors["White"],
                    bg=self.colors["Gray3"],
                    fg=self.colors["White"],
                    command=lambda id=character["anime_id"]: switchAnime(id),
                ).grid(row=1, column=0, sticky="nsew", padx=(20, 0))

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
            likeButton.configure(
                command=lambda id=character["id"], b=likeButton: like(id, b)
            )
            likeButton.image = image
            likeButton.grid(row=1, column=1, sticky="nsew", padx=5)

            titleFrame.grid(row=0, column=1, sticky="nsew")

        # Info panel
        if True:
            infoFrame = Frame(self.characterWindow, bg=self.colors["Gray2"])

            if "desc" in character.keys() and character["desc"] is not None:
                # Cut desc every 40 chars
                desc = "\n".join(
                    re.findall(r"([^\n]{1,40}\S+)|[\n]+", character["desc"], re.M)
                )
                lines = len(desc.split("\n"))
                if lines > 50:
                    Label(
                        infoFrame,
                        text="\n".join(desc.split("\n")[: lines // 2]),
                        wraplength=800,
                        font=("Source Code Pro Medium", 10),
                        bg=self.colors["Gray2"],
                        fg=self.colors["White"],
                    ).grid(row=0, column=0, sticky="n")
                    Frame(infoFrame, width=2, bg=self.colors["Gray4"]).grid(
                        row=0, column=1, sticky="ns", padx=10
                    )
                    Label(
                        infoFrame,
                        text="\n".join(desc.split("\n")[lines // 2 :]),
                        wraplength=800,
                        font=("Source Code Pro Medium", 10),
                        bg=self.colors["Gray2"],
                        fg=self.colors["White"],
                    ).grid(row=0, column=2, sticky="n")
                else:
                    Label(
                        infoFrame,
                        text=desc,
                        wraplength=500,
                        font=("Source Code Pro Medium", 10),
                        bg=self.colors["Gray2"],
                        fg=self.colors["White"],
                    ).grid(row=0, column=0)
            else:
                if can_update:
                    Label(
                        infoFrame,
                        text="Loading...",
                        font=("Source Code Pro Medium", 10),
                        bg=self.colors["Gray2"],
                        fg=self.colors["White"],
                    ).grid(row=0, column=0)

                else:
                    Label(
                        infoFrame,
                        text="No description",
                        font=("Source Code Pro Medium", 10),
                        bg=self.colors["Gray2"],
                        fg=self.colors["White"],
                    ).grid(row=0, column=0)
            # desc
            # infoFrame.grid_rowconfigure(0,weight=1)
            infoFrame.grid_columnconfigure(0, weight=1)
            infoFrame.grid(row=1, column=1, sticky="nsew", padx=(20, 0), pady=(10, 0))

        self.characterWindow.update_events()
