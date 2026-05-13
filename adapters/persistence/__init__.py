"""Persistence adapters (databases, repositories).

This package is the **canonical** home of the database manager
implementations (SQLite via :class:`thread_safe_db`,
:class:`EmbeddedMariaDB`, :class:`MySQL`). The legacy ``db_managers``
package is a thin compatibility shim that re-exports from here.
"""

from __future__ import annotations

from .dbManager import thread_safe_db
from .embeddedMariaDB import EmbeddedMariaDB
from .mySql import MySQL

databases = {
    "EmbeddedMariaDB": EmbeddedMariaDB,
    "MySQL": MySQL,
    "SQLite": thread_safe_db,
}

__all__ = ["thread_safe_db", "EmbeddedMariaDB", "MySQL", "databases"]
