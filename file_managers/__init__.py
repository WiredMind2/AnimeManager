try:
    from .FTP import FTPFileManager
    from .local_disk import LocalFileManager
except ImportError:
    from FTP import FTPFileManager
    from local_disk import LocalFileManager

managers = {}
for m in [LocalFileManager, FTPFileManager]:
    managers[m.name] = m
