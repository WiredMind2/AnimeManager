"""Map legacy provider ``Anime`` objects to :class:`ProviderAnimePayload`."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from shared.contracts import INDEX_PROVIDER_KEYS, ProviderAnimePayload, ProviderName

_PROVIDER_KEY_TO_NAME = {
    "mal_id": ProviderName.JIKAN,
    "anilist_id": ProviderName.ANILIST,
    "kitsu_id": ProviderName.KITSU,
}


def provider_name_for_api_key(api_key: str) -> ProviderName:
    return _PROVIDER_KEY_TO_NAME.get(api_key, ProviderName.UNKNOWN)


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
    """Project a legacy ``Anime`` into a provider-neutral payload."""
    title = getattr(anime, "title", None) or ""
    synonyms = getattr(anime, "title_synonyms", None) or ()
    if isinstance(synonyms, list):
        synonyms = tuple(str(s) for s in synonyms if s)
    elif synonyms:
        synonyms = (str(synonyms),)
    else:
        synonyms = ()

    genres = getattr(anime, "genres", None) or ()
    if isinstance(genres, list):
        genres = tuple(str(g) for g in genres if g)
    else:
        genres = ()

    return ProviderAnimePayload(
        title=str(title),
        external_ids=dict(external_ids or {}),
        title_synonyms=synonyms,
        synopsis=getattr(anime, "synopsis", None),
        episodes=getattr(anime, "episodes", None),
        duration=getattr(anime, "duration", None),
        status=getattr(anime, "status", None),
        rating=getattr(anime, "rating", None),
        date_from=getattr(anime, "date_from", None),
        date_to=getattr(anime, "date_to", None),
        picture=getattr(anime, "picture", None),
        trailer=getattr(anime, "trailer", None),
        broadcast=getattr(anime, "broadcast", None),
        genres=genres,
        source_provider=source_provider,
    )
