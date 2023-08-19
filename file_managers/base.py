try:
    from ..utils import LoginDialog
except ImportError:
    import sys, os
    sys.path.append(os.path.abspath('./'))
    from utils import LoginDialog

class BaseFileManager:
    name = ''
    def __init__(self, settings={}, update=False):
        self.settings = settings

        if update or self.settings.get('dataPath', '') == '':
            self.change_path(settings)

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

    def delete(self, path):
        """Delete a file or folder"""
        raise NotImplementedError()
    
    def change_path(self, root):
        """Update cwd, and sometimes login infos as well"""
        raise NotImplementedError()
    
