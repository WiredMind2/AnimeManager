"""Helpers for enriching anime detail payloads from catalogue storage."""

from __future__ import annotations

from typing import Any, Optional

from shared.utils.airing_text import build_airing_lines_from_anime

_EXTERNAL_URL_TEMPLATES: dict[str, tuple[str, str]] = {
    "mal_id": ("MyAnimeList", "https://myanimelist.net/anime/{id}"),
    "anilist_id": ("AniList", "https://anilist.co/anime/{id}"),
    "kitsu_id": ("Kitsu", "https://kitsu.app/anime/{id}"),
}


def _read_field(anime: Any, name: str) -> Any:
    if anime is None:
        return None
    if isinstance(anime, dict):
        return anime.get(name)
    return getattr(anime, name, None)


def load_external_ids(database: Any, anime_id: int) -> dict[str, int]:
    """Read provider external ids from ``indexList`` for an internal id."""
    if database is None:
        return {}
    try:
        rows = database.sql(
            "SELECT * FROM indexList WHERE id=?",
            (anime_id,),
            to_dict=True,
        )
    except Exception:
        return {}
    if not rows:
        return {}
    row = rows[0]
    out: dict[str, int] = {}
    for key, value in row.items():
        if key in {"id"} or value is None:
            continue
        if str(key).endswith("_id"):
            try:
                out[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
    return out


def build_external_urls(external_ids: dict[str, int]) -> list[dict[str, str]]:
    """Turn external id map into labelled outbound links."""
    links: list[dict[str, str]] = []
    for key, provider_id in external_ids.items():
        template = _EXTERNAL_URL_TEMPLATES.get(key)
        if template is None:
            continue
        label, url_pattern = template
        links.append({"label": label, "url": url_pattern.format(id=provider_id)})
    return links


def load_broadcast(database: Any, anime_id: int) -> Optional[str]:
    """Load a ``weekday-hour-minute`` broadcast slot when present."""
    if database is None:
        return None
    try:
        rows = database.sql(
            "SELECT w, h, m FROM broadcasts WHERE id=?",
            (anime_id,),
        )
    except Exception:
        return None
    if not rows or not rows[0]:
        return None
    try:
        w, h, m = rows[0][:3]
        return f"{int(w)}-{int(h)}-{int(m)}"
    except (TypeError, ValueError, IndexError):
        return None


def collect_anime_enrichment(anime: Any, database: Any | None = None) -> dict[str, Any]:
    """Collect optional detail fields for :func:`domain.entities.enrich_anime_entity`."""
    anime_id = _read_field(anime, "id")
    external_ids = (
        load_external_ids(database, int(anime_id))
        if anime_id is not None and database is not None
        else {}
    )
    broadcast = _read_field(anime, "broadcast")
    if broadcast is None and anime_id is not None and database is not None:
        broadcast = load_broadcast(database, int(anime_id))

    popularity = _read_field(anime, "popularity")
    studios = _read_field(anime, "studios") or []
    producers = _read_field(anime, "producers") or []

    if callable(studios):
        try:
            studios = studios()
        except Exception:
            studios = []
    if callable(producers):
        try:
            producers = producers()
        except Exception:
            producers = []

    return {
        "airing_lines": build_airing_lines_from_anime(anime),
        "broadcast": broadcast,
        "popularity": popularity,
        "studios": list(studios) if studios else [],
        "producers": list(producers) if producers else [],
        "external_ids": external_ids,
        "external_urls": build_external_urls(external_ids),
    }
