"""Application-layer bridges to legacy infrastructure types.

Import legacy entity classes from here instead of ``adapters.legacy`` so
application services stay decoupled from adapter package paths.
"""

from application.bridges.legacy_entities import (
    Anime,
    AnimeList,
    Character,
    Magnet,
    NoIdFound,
    Torrent,
)

__all__ = [
    "Anime",
    "AnimeList",
    "Character",
    "Magnet",
    "NoIdFound",
    "Torrent",
]
