"""Domain entities used by the embedded backend contract.

This module is the canonical home of the entity dataclasses. The
legacy ``backend.domain.entities`` module is a thin compatibility
shim that re-exports from here.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
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
    broadcast: Optional[str] = None
    airing_lines: list[str] = field(default_factory=list)
    popularity: Optional[int] = None
    studios: list[str] = field(default_factory=list)
    producers: list[str] = field(default_factory=list)
    external_ids: dict[str, int] = field(default_factory=dict)
    external_urls: list[dict[str, str]] = field(default_factory=list)


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
    try:
        resolved_id = int(anime_id)
    except (TypeError, ValueError):
        resolved_id = 0

    title = field("title") or ""
    return AnimeEntity(
        id=resolved_id,
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


def enrich_anime_entity(entity: AnimeEntity, **fields: Any) -> AnimeEntity:
    """Return a copy of ``entity`` with optional detail fields applied."""
    allowed = {
        "broadcast",
        "airing_lines",
        "popularity",
        "studios",
        "producers",
        "external_ids",
        "external_urls",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return entity
    return replace(entity, **updates)


__all__ = ["AnimeEntity", "TorrentEntity", "from_legacy_anime", "enrich_anime_entity"]
