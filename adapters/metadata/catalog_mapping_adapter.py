"""HTTP adapters for cross-provider catalogue id lookups."""

from __future__ import annotations

from typing import Dict, Optional

import requests

from shared.contracts import INDEX_PROVIDER_KEYS

_KITSU_MAPPED_SITES = {
    "myanimelist/anime": "mal_id",
    "anidb": "anidb_id",
    "anilist/anime": "anilist_id",
}

_ANILIST_URL = "https://graphql.anilist.co"
_KITSU_URL = "https://kitsu.io/api/edge/anime/{kitsu_id}?include=mappings"


def _safe_provider_id(value) -> int | None:
    """Parse a provider external id; skip AniDB-style alphanumeric refs."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or not text.isdigit():
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


class CatalogMappingAdapter:
    """Resolve provider cross-refs via Kitsu mappings and AniList GraphQL."""

    def __init__(
        self,
        *,
        timeout_s: float = 10.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self._timeout = timeout_s
        self._session = session or requests.Session()

    def lookup_kitsu_mappings(self, kitsu_id: int) -> Dict[str, int]:
        try:
            response = self._session.get(
                _KITSU_URL.format(kitsu_id=int(kitsu_id)),
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return {}

        out: Dict[str, int] = {"kitsu_id": int(kitsu_id)}
        for item in payload.get("included") or []:
            if item.get("type") != "mappings":
                continue
            attrs = item.get("attributes") or {}
            site = attrs.get("externalSite")
            external_id = attrs.get("externalId")
            if site not in _KITSU_MAPPED_SITES or external_id is None:
                continue
            key = _KITSU_MAPPED_SITES[site]
            if key not in INDEX_PROVIDER_KEYS:
                continue
            parsed = _safe_provider_id(external_id)
            if parsed is not None:
                out[key] = parsed
        return out

    def lookup_anilist_cross_ids(self, anilist_id: int) -> Dict[str, int]:
        query = """
        query ($id: Int) {
          Media(id: $id, type: ANIME) {
            id
            idMal
          }
        }
        """
        try:
            response = self._session.post(
                _ANILIST_URL,
                json={"query": query, "variables": {"id": int(anilist_id)}},
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return {}

        media = (payload.get("data") or {}).get("Media")
        if not media:
            return {}

        out: Dict[str, int] = {"anilist_id": int(anilist_id)}
        mal_id = media.get("idMal")
        if mal_id is not None:
            out["mal_id"] = int(mal_id)
        return out

    def lookup_mal_cross_ids(self, mal_id: int) -> Dict[str, int]:
        query = """
        query ($malId: Int) {
          Media(idMal: $malId, type: ANIME) {
            id
            idMal
          }
        }
        """
        try:
            response = self._session.post(
                _ANILIST_URL,
                json={"query": query, "variables": {"malId": int(mal_id)}},
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return {}

        media = (payload.get("data") or {}).get("Media")
        if not media:
            return {}

        out: Dict[str, int] = {"mal_id": int(mal_id)}
        anilist_id = media.get("id")
        if anilist_id is not None:
            out["anilist_id"] = int(anilist_id)
        return out
