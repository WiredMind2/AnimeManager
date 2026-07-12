import shutil

try:
    from shared.telemetry.logger import Logger
except ImportError:  # pragma: no cover - packaged install fallback
    from AnimeManager.shared.telemetry.logger import Logger  # type: ignore

try:
    from clients.tk.dialogs import LoginDialog
except ImportError:  # pragma: no cover - headless / Docker
    try:
        from AnimeManager.clients.tk.dialogs import LoginDialog  # type: ignore
    except ImportError:
        LoginDialog = None  # type: ignore[assignment,misc]


class BaseFileManager(Logger):
    name = ""

    def __init__(self, settings={}, update=False):
        self.settings = settings

        Logger.__init__(self)

        if update or self.settings.get("dataPath", "") == "":
            self.change_path(settings)
        else:
            self.initialize()

    def initialize(self):
        """Optional, called right after __init__"""
        pass

    def open(self, path, mode="r", **kwargs):
        """Return a file object depending on mode, creating file and folders if necessary"""
        raise NotImplementedError()

    def mkdir(self, path):
        """Create a directory"""
        raise NotImplementedError()

    def list(self, path):
        """List all files in a directory"""
        raise NotImplementedError()

    def exists(self, path):
        """Check if path is valid and exists"""
        raise NotImplementedError()

    def isdir(self, path):
        """Check if path is a directory"""
        raise NotImplementedError()

    def isfile(self, path):
        """Check if path is a file"""
        # By default, will assume that anything that isn't a directory is a file
        return not self.isdir(path)

    def delete(self, path):
        """Delete a file or folder"""
        shutil.rmtree(path)

    def change_path(self, root):
        """Update cwd, and sometimes login infos as well"""
        raise NotImplementedError()
