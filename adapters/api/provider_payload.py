"""Map between legacy ``Anime`` objects and typed provider payload records."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

from adapters.persistence.models import Anime
from shared.contracts import (
    AnimeRecord,
    INDEX_PROVIDER_KEYS,
    ProviderAnimePayload,
    ProviderName,
    payload_fingerprint,
)

_PROVIDER_KEY_TO_NAME = {
    "mal_id": ProviderName.JIKAN,
    "anilist_id": ProviderName.ANILIST,
    "kitsu_id": ProviderName.KITSU,
    "anidb_id": ProviderName.ANIDB,
}


def provider_name_for_api_key(api_key: str) -> ProviderName:
    return _PROVIDER_KEY_TO_NAME.get(api_key, ProviderName.UNKNOWN)


def _normalize_external_ids(external_ids: Mapping[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for key, value in (external_ids or {}).items():
        if key not in INDEX_PROVIDER_KEYS or value is None:
            continue
        try:
            out[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return out


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _tupled(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if item)
    return (str(value),)


def _picture_variants(value: Any) -> Tuple[Dict[str, Any], ...]:
    if not value:
        return ()
    if not isinstance(value, (list, tuple)):
        return ()
    out: list[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        out.append(dict(item))
    return tuple(out)


def external_ids_from_anime(
    anime: Any,
    *,
    index_external_ids: Optional[Mapping[str, int]] = None,
    primary_api_key: Optional[str] = None,
    primary_external_id: Optional[int] = None,
) -> Dict[str, int]:
    """Collect known provider ids for identity resolution."""
    out: Dict[str, int] = {}
    if index_external_ids:
        out.update(
            {
                k: int(v)
                for k, v in index_external_ids.items()
                if k in INDEX_PROVIDER_KEYS and v is not None
            }
        )
    pending = getattr(anime, "_schedule_external_ids", None)
    if pending:
        out.update(_normalize_external_ids(pending))
    if primary_api_key and primary_external_id is not None:
        if primary_api_key in INDEX_PROVIDER_KEYS:
            out[primary_api_key] = int(primary_external_id)
    return out


def anime_to_provider_payload(
    anime: Any,
    *,
    source_provider: ProviderName = ProviderName.UNKNOWN,
    external_ids: Optional[Mapping[str, int]] = None,
) -> ProviderAnimePayload:
    """Project a legacy ``Anime`` into a provider-neutral payload.

    Prefers ``_schedule_external_ids`` / explicit ``external_ids`` over any
    catalogue id already stamped on the object (list-light rows).
    """
    title = getattr(anime, "title", None) or ""
    synonyms = _tupled(getattr(anime, "title_synonyms", None))
    genres = _tupled(getattr(anime, "genres", None))

    normalized = _normalize_external_ids(external_ids or {})
    if not normalized:
        normalized = _normalize_external_ids(
            getattr(anime, "_schedule_external_ids", None) or {}
        )

    resolved_provider = source_provider
    if resolved_provider == ProviderName.UNKNOWN and normalized:
        first_key = next(iter(normalized.keys()))
        resolved_provider = provider_name_for_api_key(first_key)

    variants = _picture_variants(getattr(anime, "_pending_pictures", None))
    if not variants:
        variants = _picture_variants(getattr(anime, "picture_variants", None))

    return ProviderAnimePayload(
        title=str(title),
        external_ids=normalized,
        title_synonyms=synonyms,
        synopsis=_safe_str(getattr(anime, "synopsis", None)),
        episodes=_safe_int(getattr(anime, "episodes", None)),
        duration=_safe_int(getattr(anime, "duration", None)),
        status=_safe_str(getattr(anime, "status", None)),
        rating=_safe_str(getattr(anime, "rating", None)),
        date_from=_safe_int(getattr(anime, "date_from", None)),
        date_to=_safe_int(getattr(anime, "date_to", None)),
        picture=_safe_str(getattr(anime, "picture", None)),
        trailer=_safe_str(getattr(anime, "trailer", None)),
        broadcast=_safe_str(getattr(anime, "broadcast", None)),
        genres=genres,
        source_provider=resolved_provider,
        picture_variants=variants,
    )


def payload_to_anime_record(
    payload: ProviderAnimePayload,
    catalog_id: int,
    *,
    external_ids: Optional[Mapping[str, int]] = None,
) -> AnimeRecord:
    """Materialize a catalogue ``AnimeRecord`` after identity resolution."""
    rid = int(catalog_id)
    if rid <= 0:
        raise ValueError(f"catalog_id must be positive, got {catalog_id!r}")
    normalized = _normalize_external_ids(
        external_ids if external_ids is not None else payload.external_ids
    )
    return AnimeRecord(
        id=rid,
        title=str(payload.title or ""),
        title_synonyms=tuple(payload.title_synonyms or ()),
        synopsis=payload.synopsis,
        episodes=payload.episodes,
        duration=payload.duration,
        status=payload.status,
        rating=payload.rating,
        date_from=payload.date_from,
        date_to=payload.date_to,
        picture=payload.picture,
        trailer=payload.trailer,
        broadcast=payload.broadcast,
        genres=tuple(payload.genres or ()),
        external_ids=normalized,
        source_provider=payload.source_provider,
        picture_variants=tuple(payload.picture_variants or ()),
    )


def anime_record_to_legacy_anime(record: AnimeRecord) -> Anime:
    """Reconstruct a legacy ``Anime`` model from a normalized record."""
    anime = Anime()
    for key in (
        "id",
        "title",
        "synopsis",
        "episodes",
        "duration",
        "status",
        "rating",
        "date_from",
        "date_to",
        "picture",
        "trailer",
        "broadcast",
    ):
        value = getattr(record, key)
        if value is not None:
            try:
                setattr(anime, key, value)
            except Exception:
                pass
    for meta_key in ("title_synonyms", "genres"):
        meta_value = getattr(record, meta_key, None)
        if meta_value:
            try:
                setattr(anime, meta_key, list(meta_value))
            except Exception:
                pass
    return anime


def legacy_anime_to_record(
    anime: Any,
    *,
    catalog_id: Optional[int] = None,
    external_ids: Optional[Mapping[str, Any]] = None,
    source_provider: Optional[ProviderName] = None,
) -> Optional[AnimeRecord]:
    """Project a legacy ``Anime`` object into a normalized ``AnimeRecord``."""
    getter = anime.get if isinstance(anime, dict) else None

    def _field(name: str) -> Any:
        if getter is not None:
            return getter(name)
        return getattr(anime, name, None)

    rid = catalog_id if catalog_id is not None else _field("id")
    rid_int = _safe_int(rid)
    if rid_int is None:
        return None

    normalized_external = _normalize_external_ids(external_ids or {})
    if not normalized_external:
        normalized_external = _normalize_external_ids(
            getattr(anime, "_schedule_external_ids", None) or {}
        )
    resolved_provider = source_provider or ProviderName.UNKNOWN
    if resolved_provider == ProviderName.UNKNOWN and normalized_external:
        first_key = next(iter(normalized_external.keys()))
        resolved_provider = provider_name_for_api_key(first_key)

    variants = _picture_variants(getattr(anime, "_pending_pictures", None))
    if not variants:
        variants = _picture_variants(getattr(anime, "picture_variants", None))

    return AnimeRecord(
        id=rid_int,
        title=str(_field("title") or ""),
        title_synonyms=_tupled(_field("title_synonyms")),
        synopsis=_safe_str(_field("synopsis")),
        episodes=_safe_int(_field("episodes")),
        duration=_safe_int(_field("duration")),
        status=_safe_str(_field("status")),
        rating=_safe_str(_field("rating")),
        date_from=_safe_int(_field("date_from")),
        date_to=_safe_int(_field("date_to")),
        picture=_safe_str(_field("picture")),
        trailer=_safe_str(_field("trailer")),
        broadcast=_safe_str(_field("broadcast")),
        genres=_tupled(_field("genres")),
        external_ids=normalized_external,
        source_provider=resolved_provider,
        picture_variants=variants,
    )


__all__ = [
    "anime_record_to_legacy_anime",
    "anime_to_provider_payload",
    "external_ids_from_anime",
    "legacy_anime_to_record",
    "payload_fingerprint",
    "payload_to_anime_record",
    "provider_name_for_api_key",
]
