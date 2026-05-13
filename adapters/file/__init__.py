"""File-system adapters.

This package is the **canonical** home of the file manager
implementations (local disk, FTP). The legacy ``file_managers``
package is a thin compatibility shim that re-exports from here.
"""

from __future__ import annotations

from .FTP import FTPFileManager
from .local_disk import LocalFileManager

managers: dict[str, type] = {}
for _m in [LocalFileManager, FTPFileManager]:
    managers[_m.name] = _m

__all__ = ["FTPFileManager", "LocalFileManager", "managers"]
