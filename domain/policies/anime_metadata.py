"""Pure helpers for detecting incomplete anime catalogue metadata."""

from __future__ import annotations

from domain.entities import AnimeEntity


def is_anime_metadata_missing(
    entity: AnimeEntity | None,
    *,
    catalog_id: int | None = None,
) -> bool:
    """Return True when a catalogue id is known but display metadata is absent."""
    if entity is None:
        effective_id = int(catalog_id or 0)
    else:
        effective_id = entity.id if entity.id > 0 else int(catalog_id or 0)

    if effective_id <= 0:
        return False

    title = ""
    synonyms: list[str] = []
    if entity is not None:
        title = (entity.title or "").strip()
        synonyms = [str(s).strip() for s in (entity.title_synonyms or []) if s]
    if not title:
        return True
    return not synonyms
