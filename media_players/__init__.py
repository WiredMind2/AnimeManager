import importlib
import os
import traceback

try:
    from ..logger import log
except Exception:
    try:
        from logger import log
    except Exception:

        def log(*a, **k):
            # fallback no-op logger
            print(*a)


# If the repository ships native DLLs in a top-level 'lib' folder (mpv, vlc, etc.),
# add that folder to PATH so Python bindings can find the shared libraries at import
# time. This lets python-mpv/python-vlc locate libmpv/vlc DLLs shipped with the repo.
try:
    project_root = os.path.dirname(os.path.dirname(__file__))
    bundled_lib = os.path.join(project_root, "lib")
    if os.path.isdir(bundled_lib):
        os.environ["PATH"] = bundled_lib + os.pathsep + os.environ.get("PATH", "")

except Exception:
    # Best-effort only; don't fail module import if manipulation fails
    pass


class MediaPlayers:
    def __init__(self):
        self.get_players()

    def get_players(self):
        self.media_players = {}
        root = os.path.dirname(__file__)
        ignore = ("__init__.py", "base_player.py")
        for f in os.listdir(root):
            path = os.path.join(root, f)
            if f in ignore or not os.path.isfile(path) or not f.endswith(".py"):
                continue

            name = f.rsplit(".py", 1)[0]
            class_name = self.convert_name(name)

            try:
                module = importlib.import_module(f"media_players.{name}")
            except Exception as e:
                log("Error while importing media player:", name, "- e:", e)
                continue

            try:
                cls = getattr(module, class_name)
            except AttributeError:
                log("Media player module loaded but class not found:", name, class_name)
                continue

            # Register the player class
            self.media_players[name] = cls
        # log(f'{len(self.media_players)} players found:\n{self.media_players}')

    def convert_name(self, name):  # TODO - Remove self
        out = name[0].upper()
        upper = False
        for letter in name[1:]:
            if letter == "_":
                upper = True
            elif upper:
                out += letter.upper()
                upper = False
            else:
                out += letter
        return out
