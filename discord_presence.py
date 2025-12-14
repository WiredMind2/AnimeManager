import asyncio
import json
import os
import random
import shutil
import sys
import tempfile
import threading
import time
import traceback

from pypresence import Presence
from pypresence import exceptions as pp_exceptions


class DiscordPresence:
    def __init__(self):
        if "RPC" not in globals().keys():
            self.RPC = None
            self.init_t = threading.Thread(target=self.get_RPC, daemon=True)
            self.init_t.start()
        else:
            self.RPC = globals()["RPC"]

    def get_RPC(self):
        if "RPC" in globals().keys():
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            RPC = Presence(self.RPC_client_id)
        except pp_exceptions.DiscordNotFound:
            print("Error on RPC: DiscordNotFound")
            return

        try:
            RPC.connect()
        except PermissionError:
            print("Error on RPC: PermissionError")
            return
        except pp_exceptions.DiscordNotFound:
            print("Error on RPC: DiscordNotFound")
            return

        RPC.global_start = time.time()
        RPC.watching = False
        RPC.timer = None

        self.RPC = RPC
        globals()["RPC"] = self.RPC

    def RPC_menu(self):
        threading.Thread(target=self.RPC_menu_, daemon=True).start()

    def RPC_menu_(self):
        while self.RPC is None:
            if self.init_t.is_alive() and not self.closing:
                self.init_t.join()
            else:
                return
        if self.RPC.watching or self.closing:
            return

        start = self.RPC.global_start
        # quote = self.get_random_quote()
        quote = "Hi!"

        try:
            self.RPC.update(
                large_image="icon_rounded",
                details="In the menu",
                state=quote,
                start=start,
            )
        except pp_exceptions.InvalidID:
            pass
        except ConnectionResetError:
            pass
        except Exception as e:
            # TODO - Handle error:
            # Exception has occurred: ConnectionResetError
            # [WinError 995] The I/O operation has been aborted because of either a thread exit or an application request

            print("Unknown error on RPC: ")
            traceback.print_exc()

        if not self.RPC.watching and not self.closing:
            if self.RPC.timer is not None and self.RPC.timer.is_alive():
                # Interrupt previous timer
                self.RPC.timer.cancel()

            self.RPC.timer = threading.Timer(60, self.RPC_menu)
            self.RPC.timer.start()

    def RPC_watching(self, title, **kwargs):
        threading.Thread(
            target=self.RPC_watching_, args=(title,), daemon=True, kwargs=kwargs
        ).start()

    def RPC_watching_(self, title, **kwargs):
        # Kwargs can have three fields: start: float, end: float, eps: [int, int]
        while self.RPC is None:
            if self.init_t.is_alive() and not self.closing:
                self.init_t.join()
            else:
                return
        if self.closing:
            return

        self.RPC.watching = True
        if "eps" in kwargs:
            kwargs["party_size"] = kwargs.pop("eps")
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        try:
            self.RPC.update(
                large_image="icon_rounded",
                details="Watching an anime:",
                state=title,
                **kwargs,
            )
        except Exception as e:
            pass

    def RPC_stop_watching(self):
        if self.RPC is None:
            return
        self.RPC.watching = False
        self.RPC_menu()

    def RPC_stop(self):
        if self.RPC is not None:
            if self.RPC.timer is not None:
                self.RPC.timer.cancel()
            self.RPC.close()

    def get_random_quote(self):
        # Length of category
        # Disk usage
        cats = ("funny", "disk", "cat_length")

        cat = random.choice(cats)

        if cat == "funny":
            funny_quotes = (
                "Forgot to sleep",
                "Is probably asleep",
                "Enjoying life",
                "Probably about to watch an anime",
            )
            return random.choice(funny_quotes)
        elif False and cat == "disk":  # Disk

            def list_sub_dirs(dir):
                out = []
                for f in os.listdir(dir):
                    path = os.path.join(dir, f)
                    if os.path.isdir(path):
                        out += list_sub_dirs(path)
                    else:
                        out.append(path)
                return out

            disk = self.animePath.split("/")[0]
            total, used, free = shutil.disk_usage(disk)
            anime_size = sum(os.path.getsize(p) for p in list_sub_dirs(self.animePath))
            usedPrct = anime_size / total * 100
            return "{}% of the disk space is for animes!".format(str(int(usedPrct)))
        # elif cat == "cat_length": # TODO - Needs auth
        #     tags = {
        #         "LIKED": "Liked {} animes",
        #         "SEEN": "Has seen {} animes",
        #         "WATCHING": "Currently have {} animes to watch",
        #         "WATCHLIST": "Wish to watch {} animes"
        #     }

        #     tag = random.choice(list(tags.keys()))

        #     if tag == "LIKED":
        #         sql = "SELECT COUNT(*) FROM user_tags WHERE like=1;"
        #     else:
        #         sql = "SELECT COUNT(*) FROM anime WHERE tag='{}';".format(tag)

        #     count = self.database.sql(sql)[0][0]

        #     return tags[tag].format(str(count))


def get_ipc_path(pipe=None):
    ipc = "discord-ipc-"
    if pipe:
        ipc = f"{ipc}{pipe}"

    if sys.platform in ("linux", "darwin"):
        tempdir = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
        paths = [".", "snap.discord", "app/com.discordapp.Discord"]
    elif sys.platform == "win32":
        tempdir = r"\\?\pipe"
        paths = ["."]
    else:
        return

    for path in paths:
        full_path = os.path.abspath(os.path.join(tempdir, path))
        if sys.platform == "win32" or os.path.isdir(full_path):
            for entry in os.scandir(full_path):
                if entry.name.startswith(ipc):
                    return entry.path


if __name__ == "__main__":
    pipe = get_ipc_path()

    act_details = {
        "state": "aaa",
        "details": "bbb",
        "timestamps": {"start": time.time(), "end": time.time() + 1000},
        "assets": {
            "large_image": "icon_rounded",
            "large_text": "cccc",
            "small_image": None,
            "small_text": None,
        },
        "party": {"id": None, "size": None},
        "secrets": {"join": None, "spectate": None, "match": None},
        "buttons": None,
        "instance": True,
    }

    payload = {
        "cmd": "SET_ACTIVITY",
        "args": {"pid": os.getpid(), "activity": act_details},
        "nonce": "{:.20f}".format(time.time()),
    }

    data = json.dumps(payload).encode("utf-8")

    # TODO - Connection + Authentification
    with open(pipe, "wb") as f:
        f.write(data)
