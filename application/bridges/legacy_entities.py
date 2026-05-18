"""Single choke-point for legacy entity imports used by application services."""

from adapters.legacy.legacy_classes import (  # noqa: F401
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
