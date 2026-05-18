"""Domain entities used by the embedded backend contract.

This module is the canonical home of the entity dataclasses. The
legacy ``backend.domain.entities`` module is a thin compatibility
shim that re-exports from here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class AnimeEntity:
    """Canonical anime representation used across clients."""

    id: int
    title: str
    picture: Optional[str] = None
    title_synonyms: list[str] = field(default_factory=list)
    date_from: Optional[int] = None
    date_to: Optional[int] = None
    synopsis: Optional[str] = None
    episodes: Optional[int] = None
    duration: Optional[int] = None
    rating: Optional[str] = None
    status: Optional[str] = None
    trailer: Optional[str] = None
    genres: list[str] = field(default_factory=list)
    tag: Optional[str] = None
    liked: Optional[bool] = None
    last_seen: Optional[str] = None


@dataclass(slots=True)
class TorrentEntity:
    """Canonical torrent representation used by download workflows."""

    link: str
    name: str
    size: int = 0
    seeds: int = 0
    leech: int = 0
    hash: Optional[str] = None


def _materialize(value: Any) -> Any:
    """Return ``value`` after invoking it if it's a 0-arg callable.

    Legacy ``Anime`` objects extend ``dict`` and store lazy thunks for
    metadata fields (e.g. ``title_synonyms``, ``genres``, ``torrents``);
    those are normally evaluated through ``__getattr__``. When we read
    them via ``dict.get`` we bypass that machinery and may receive the
    raw callable. Materialize it here so downstream code always sees the
    realized value.
    """
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value


def _to_list(value: Any) -> list:
    """Best-effort coercion of legacy metadata into a list."""
    value = _materialize(value)
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    try:
        return list(value)
    except TypeError:
        return [value]


def from_legacy_anime(anime: Any) -> AnimeEntity:
    """Map a legacy Anime object/dict into AnimeEntity."""
    data = (
        dict(anime)
        if hasattr(anime, "__iter__") and not isinstance(anime, dict)
        else anime
    )
    if not isinstance(data, dict):
        data = {}

    def field(name: str) -> Any:
        """Read a field, preferring the materialized attribute when present."""
        raw = data.get(name)
        if raw is None or callable(raw):
            try:
                attr = getattr(anime, name, None)
            except Exception:
                # Legacy lazy fields can fail transiently when the backing
                # DB row cannot be decoded (e.g. dropped connection / partial
                # packet). Entity mapping should degrade to defaults rather
                # than crashing the whole request.
                attr = None
            if attr is not None:
                return attr
        try:
            return _materialize(raw)
        except Exception:
            return None

    anime_id = field("id")
    if anime_id is None:
        anime_id = 0

    title = field("title") or ""
    return AnimeEntity(
        id=int(anime_id),
        title=str(title),
        picture=field("picture"),
        title_synonyms=_to_list(field("title_synonyms")),
        date_from=field("date_from"),
        date_to=field("date_to"),
        synopsis=field("synopsis"),
        episodes=field("episodes"),
        duration=field("duration"),
        rating=field("rating"),
        status=field("status"),
        trailer=field("trailer"),
        genres=_to_list(field("genres")),
        tag=field("tag"),
        liked=(
            bool(field("like"))
            if field("like") is not None
            else (
                bool(field("liked"))
                if field("liked") is not None
                else getattr(anime, "liked", None)
            )
        ),
        last_seen=field("last_seen"),
    )


def title_variants_for_torrent_search(anime: Any) -> list[str]:
    """Build ordered, de-duplicated torrent search terms from anime metadata."""
    if isinstance(anime, dict):
        data = anime
    elif hasattr(anime, "keys") and callable(getattr(anime, "keys", None)):
        try:
            data = dict(anime)
        except Exception:
            return []
    else:
        return []

    def _clean(value: Any) -> str:
        return str(value or "").strip()

    main = _clean(data.get("title"))
    synonyms = _to_list(_materialize(data.get("title_synonyms")))

    out: list[str] = []
    seen: set[str] = set()

    def _add(term: str) -> None:
        text = _clean(term)
        if not text:
            return
        key = text.casefold()
        if key in seen:
            return
        seen.add(key)
        out.append(text)

    if main:
        _add(main)
    for synonym in synonyms:
        _add(synonym)
    return out


__all__ = [
    "AnimeEntity",
    "TorrentEntity",
    "from_legacy_anime",
    "title_variants_for_torrent_search",
]
