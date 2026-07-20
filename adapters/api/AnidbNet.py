"""AniDB metadata provider (HTTP API + offline titles dump).

Search uses the daily anime-titles dump so we never hammer AniDB for
queries. Detail hydration uses the registered HTTP API with a 24h disk
cache. Browse methods (season/genre/top/schedule) are intentionally
omitted so the coordinator keeps AniDB out of high-QPS fan-out.
"""

from __future__ import annotations

import gzip
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote

try:
    from .APIUtils import Anime, APIUtils, EnhancedSession
    from adapters.persistence.models import NoIdFound
except ImportError:  # pragma: no cover
    from APIUtils import Anime, APIUtils, EnhancedSession
    from adapters.persistence.models import NoIdFound

try:
    from shared.security import load_secret
except ImportError:  # pragma: no cover
    from AnimeManager.shared.security import load_secret  # type: ignore[no-redef]

# AniDB resource type ids → our index columns.
_RESOURCE_TO_INDEX = {
    2: "mal_id",  # MyAnimeList
    43: "anilist_id",  # AniList
}

_TITLES_DUMP_URL = "https://anidb.net/api/anime-titles.xml.gz"
_HTTP_API_URL = "http://api.anidb.net:9001/httpapi"
_PICTURE_CDN = "https://cdn.anidb.net/images/main/{}"
_CACHE_TTL_S = 24 * 60 * 60
_HTTP_COOLDOWN_S = 2.0
_BBCODE_RE = re.compile(r"\[/?[^\]]+\]")
_WHITESPACE_RE = re.compile(r"\s+")


class _TitlesIndex:
    """In-memory aid → titles index built from the daily dump."""

    def __init__(self) -> None:
        # aid -> (main_title, synonyms)
        self._by_aid: Dict[int, Tuple[str, Tuple[str, ...]]] = {}
        # lowercased title -> list of aids (for search)
        self._title_to_aids: Dict[str, List[int]] = {}
        self._lock = threading.RLock()
        self.loaded = False

    def clear(self) -> None:
        with self._lock:
            self._by_aid.clear()
            self._title_to_aids.clear()
            self.loaded = False

    def load_xml(self, xml_bytes: bytes) -> int:
        root = ET.fromstring(xml_bytes)
        by_aid: Dict[int, Tuple[str, Tuple[str, ...]]] = {}
        title_to_aids: Dict[str, List[int]] = {}

        for anime_el in root.findall("anime"):
            aid_raw = anime_el.get("aid")
            if not aid_raw:
                continue
            try:
                aid = int(aid_raw)
            except (TypeError, ValueError):
                continue

            main_title = ""
            synonyms: List[str] = []
            for title_el in anime_el.findall("title"):
                text = (title_el.text or "").strip()
                if not text:
                    continue
                title_type = (title_el.get("type") or "").lower()
                lang = (title_el.get("{http://www.w3.org/XML/1998/namespace}lang") or "").lower()
                if title_type == "main" and not main_title:
                    main_title = text
                elif title_type == "official" and lang in ("en", "x-jat") and not main_title:
                    main_title = text
                else:
                    synonyms.append(text)

            if not main_title:
                if synonyms:
                    main_title = synonyms[0]
                    synonyms = synonyms[1:]
                else:
                    continue

            # Deduplicate while preserving order.
            seen = {main_title.casefold()}
            unique_syn: List[str] = []
            for syn in synonyms:
                key = syn.casefold()
                if key in seen:
                    continue
                seen.add(key)
                unique_syn.append(syn)

            by_aid[aid] = (main_title, tuple(unique_syn))
            for label in (main_title, *unique_syn):
                key = label.casefold()
                title_to_aids.setdefault(key, [])
                if aid not in title_to_aids[key]:
                    title_to_aids[key].append(aid)

        with self._lock:
            self._by_aid = by_aid
            self._title_to_aids = title_to_aids
            self.loaded = True
        return len(by_aid)

    def get(self, aid: int) -> Optional[Tuple[str, Tuple[str, ...]]]:
        with self._lock:
            return self._by_aid.get(int(aid))

    def search(self, query: str, limit: int = 50) -> List[Tuple[int, str, Tuple[str, ...]]]:
        """Return ``(aid, main_title, synonyms)`` ranked by simple match quality."""
        needle = (query or "").strip().casefold()
        if not needle or limit <= 0:
            return []

        with self._lock:
            if not self.loaded:
                return []
            items = list(self._by_aid.items())

        scored: List[Tuple[int, int, str, Tuple[str, ...]]] = []
        for aid, (main_title, synonyms) in items:
            labels = (main_title, *synonyms)
            best = -1
            for label in labels:
                folded = label.casefold()
                if folded == needle:
                    best = max(best, 300)
                elif folded.startswith(needle):
                    best = max(best, 200 - min(len(folded), 99))
                elif needle in folded:
                    best = max(best, 100 - min(len(folded), 99))
            if best < 0:
                continue
            scored.append((best, aid, main_title, synonyms))

        scored.sort(key=lambda row: (-row[0], row[2].casefold(), row[1]))
        return [(aid, title, syns) for _, aid, title, syns in scored[:limit]]


class AnidbNetWrapper(APIUtils):
    """AniDB provider: titles-dump search + HTTP detail enrichment.

    ``parallel_search`` is False so the coordinator keeps AniDB out of
    the multi-provider search fan-out (titles-only hits lack cross-IDs and
    would create orphan catalog rows). Title resolve stays available via
    ``searchAnime`` for enrichment/backfill; ``anime()`` still joins the
    detail hydration fan-out when ``anidb_id`` is present.
    """

    parallel_search = False

    def __init__(self) -> None:
        super().__init__()
        self.apiKey = "anidb_id"
        self.session = EnhancedSession(timeout=30)
        self.client, self.clientver = self._load_client_credentials()
        self.cooldown = _HTTP_COOLDOWN_S
        self.last = time.time() - self.cooldown
        self._titles = _TitlesIndex()
        self._titles_lock = threading.RLock()
        self._http_lock = threading.Lock()
        self._cache_dir = self._resolve_cache_dir()

    def _resolve_cache_dir(self) -> str:
        base = None
        try:
            from shared.config.constants import Constants

            base = Constants().cache
        except Exception:
            base = None
        if not base:
            base = os.path.join(os.path.expanduser("~"), ".anime_manager_cache")
        path = os.path.join(str(base), "anidb")
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
        return path

    def _load_client_credentials(self) -> Tuple[str, str]:
        settings_data = getattr(self, "settings", {}) or {}
        settings_creds: Dict[str, Any] = {}
        if isinstance(settings_data, dict):
            api_creds = settings_data.get("api_credentials")
            if isinstance(api_creds, dict):
                settings_creds = api_creds.get("anidb") or {}

        client = load_secret(
            "ANIMEMANAGER_ANIDB_CLIENT",
            settings={"ANIMEMANAGER_ANIDB_CLIENT": settings_creds.get("client")},
        )
        clientver = load_secret(
            "ANIMEMANAGER_ANIDB_CLIENTVER",
            settings={
                "ANIMEMANAGER_ANIDB_CLIENTVER": settings_creds.get("clientver")
            },
            default="1",
        )
        return (client or "").strip(), (clientver or "1").strip()

    # --- Public provider surface (search + detail only) -------------------

    def searchAnime(self, search: str, limit: int = 50) -> Iterable[Anime]:
        """Search the offline titles dump; no live HTTP calls."""
        self._ensure_titles_index()
        hits = self._titles.search(search, limit=limit)
        for aid, title, synonyms in hits:
            anime = self._convert_title_hit(aid, title, synonyms)
            if anime:
                yield anime

    def anime(self, id) -> Any:
        """Hydrate full metadata for a catalog id that already has ``anidb_id``."""
        try:
            aid = self.getId(id)
        except NoIdFound:
            return {}
        except Exception:
            return {}
        if aid is None:
            return {}
        try:
            aid_int = int(aid)
        except (TypeError, ValueError):
            return {}
        if not self.client:
            self.log(
                "ANIDB",
                "HTTP detail skipped: register an AniDB client and set "
                "api_credentials.anidb.client / ANIMEMANAGER_ANIDB_CLIENT",
            )
            return {}
        root = self._fetch_anime_xml(aid_int)
        if root is None:
            return {}
        return self._convertAnime(root)

    # --- Titles dump ------------------------------------------------------

    def _titles_dump_path(self) -> str:
        return os.path.join(self._cache_dir, "anime-titles.xml.gz")

    def _ensure_titles_index(self) -> None:
        with self._titles_lock:
            if self._titles.loaded and not self._cache_stale(self._titles_dump_path()):
                return
            xml_bytes = self._load_titles_xml_bytes()
            if not xml_bytes:
                return
            try:
                count = self._titles.load_xml(xml_bytes)
                self.log("ANIDB", f"Titles index loaded: {count} anime")
            except Exception as exc:
                self.log("ANIDB", f"Failed to parse titles dump: {exc}")

    def _load_titles_xml_bytes(self) -> Optional[bytes]:
        path = self._titles_dump_path()
        if os.path.isfile(path) and not self._cache_stale(path):
            try:
                with gzip.open(path, "rb") as fh:
                    return fh.read()
            except Exception as exc:
                self.log("ANIDB", f"Corrupt titles dump cache, re-downloading: {exc}")

        try:
            resp = self.session.request(
                "GET",
                _TITLES_DUMP_URL,
                headers={"User-Agent": self._user_agent()},
            )
            resp.raise_for_status()
            compressed = resp.content
        except Exception as exc:
            self.log("ANIDB", f"Titles dump download failed: {exc}")
            if os.path.isfile(path):
                try:
                    with gzip.open(path, "rb") as fh:
                        return fh.read()
                except Exception:
                    return None
            return None

        try:
            with open(path, "wb") as fh:
                fh.write(compressed)
        except OSError as exc:
            self.log("ANIDB", f"Could not write titles dump cache: {exc}")

        try:
            return gzip.decompress(compressed)
        except Exception as exc:
            self.log("ANIDB", f"Titles dump decompress failed: {exc}")
            return None

    # --- HTTP detail + disk cache -----------------------------------------

    def _anime_cache_path(self, aid: int) -> str:
        return os.path.join(self._cache_dir, f"anime_{int(aid)}.xml")

    def _fetch_anime_xml(self, aid: int) -> Optional[ET.Element]:
        path = self._anime_cache_path(aid)
        if os.path.isfile(path) and not self._cache_stale(path):
            try:
                return ET.parse(path).getroot()
            except Exception:
                pass

        if not self.client:
            return None

        params = {
            "request": "anime",
            "client": self.client,
            "clientver": self.clientver or "1",
            "protover": "1",
            "aid": str(int(aid)),
        }
        with self._http_lock:
            self.delay()
            try:
                resp = self.session.request(
                    "GET",
                    _HTTP_API_URL,
                    params=params,
                    headers={"User-Agent": self._user_agent()},
                )
            except Exception as exc:
                self.log("ANIDB", f"HTTP anime({aid}) failed: {exc}")
                return None

        if resp.status_code != 200:
            self.log("ANIDB", f"HTTP anime({aid}) status {resp.status_code}")
            return None

        text = resp.text or ""
        if "<error" in text.lower():
            self.log("ANIDB", f"HTTP anime({aid}) error body: {text[:200]}")
            return None

        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            self.log("ANIDB", f"HTTP anime({aid}) XML parse error: {exc}")
            return None

        # AniDB wraps payload in <anime> at the root for request=anime.
        if root.tag != "anime":
            anime_el = root.find("anime")
            if anime_el is None:
                self.log("ANIDB", f"HTTP anime({aid}) missing <anime> root")
                return None
            root = anime_el

        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(ET.tostring(root, encoding="unicode"))
        except OSError as exc:
            self.log("ANIDB", f"Could not write anime cache for {aid}: {exc}")

        return root

    def delay(self) -> None:
        """Sleep to respect AniDB's ≥2s HTTP spacing. Caller holds ``_http_lock``."""
        elapsed = time.time() - self.last
        if elapsed < self.cooldown:
            time.sleep(max(self.cooldown - elapsed, 0))
        self.last = time.time()

    def _user_agent(self) -> str:
        name = self.client or "animemanager"
        ver = self.clientver or "1"
        return f"{name}/{ver} (AnimeManager; +https://github.com/)"

    @staticmethod
    def _cache_stale(path: str, ttl_s: int = _CACHE_TTL_S) -> bool:
        try:
            age = time.time() - os.path.getmtime(path)
        except OSError:
            return True
        return age > ttl_s

    # --- Conversion -------------------------------------------------------

    def _convert_title_hit(
        self, aid: int, title: str, synonyms: Sequence[str]
    ) -> Optional[Anime]:
        external_ids = {"anidb_id": int(aid)}
        try:
            catalog_id = self.resolve_catalog_id(external_ids)
        except Exception as exc:
            self.log("ANIDB", f"resolve_catalog_id failed for aid={aid}: {exc}")
            return None

        out = Anime()
        out["id"] = catalog_id
        out["title"] = title
        out["title_synonyms"] = list(synonyms)
        out["date_from"] = None
        out["date_to"] = None
        out["status"] = "UNKNOWN"
        out._schedule_external_ids = dict(external_ids)
        return out

    def _convertAnime(self, root: ET.Element) -> Any:
        aid_raw = root.get("id") or root.get("aid")
        if not aid_raw:
            return {}
        try:
            aid = int(aid_raw)
        except (TypeError, ValueError):
            return {}

        external_ids: Dict[str, int] = {"anidb_id": aid}
        external_ids.update(self._parse_resource_ids(root))

        titles, synonyms = self._parse_titles(root)
        if not titles:
            cached = self._titles.get(aid)
            if cached:
                titles = [cached[0]]
                synonyms = list(cached[1])
        if not titles:
            return {}

        main_title = titles[0]
        all_synonyms = list(dict.fromkeys([*titles[1:], *synonyms]))

        out = Anime()
        try:
            catalog_id = self.resolve_catalog_id(external_ids)
        except Exception as exc:
            self.log("ANIDB", f"resolve_catalog_id failed for aid={aid}: {exc}")
            return {}

        out["id"] = catalog_id
        out["title"] = main_title
        out["title_synonyms"] = all_synonyms

        out["synopsis"] = self._parse_description(root)
        out["episodes"] = self._parse_int_attr(root, "episodecount")
        out["duration"] = None
        out["date_from"] = self._parse_date(root.findtext("startdate"))
        out["date_to"] = self._parse_date(root.findtext("enddate"))
        out["status"] = self.getStatusFromData(out)
        out["rating"] = None
        out["trailer"] = None
        out["broadcast"] = None

        picture_name = (root.findtext("picture") or "").strip()
        pictures: List[Dict[str, Any]] = []
        if picture_name:
            url = _PICTURE_CDN.format(quote(picture_name))
            out["picture"] = url
            pictures = [{"url": url, "size": "original"}]
            try:
                self.save_pictures(catalog_id, pictures)
            except Exception:
                pass
        else:
            out["picture"] = None

        genres = self._parse_genres(root)
        if genres:
            try:
                out["genres"] = genres
                self.save_genres(catalog_id, genres)
            except Exception:
                pass

        rels = self._parse_relations(root)
        if rels:
            try:
                self.save_relations(catalog_id, rels)
            except Exception:
                pass

        out._schedule_external_ids = dict(external_ids)
        return out

    @staticmethod
    def _parse_titles(root: ET.Element) -> Tuple[List[str], List[str]]:
        mains: List[str] = []
        official_en: List[str] = []
        synonyms: List[str] = []
        for title_el in root.findall("titles/title") or root.findall("title"):
            text = (title_el.text or "").strip()
            if not text:
                continue
            title_type = (title_el.get("type") or "").lower()
            lang = (
                title_el.get("{http://www.w3.org/XML/1998/namespace}lang") or ""
            ).lower()
            if title_type == "main":
                mains.append(text)
            elif title_type == "official" and lang in ("en", "x-jat"):
                official_en.append(text)
            else:
                synonyms.append(text)
        ordered = list(dict.fromkeys([*mains, *official_en]))
        return ordered, list(dict.fromkeys(synonyms))

    @staticmethod
    def _parse_description(root: ET.Element) -> Optional[str]:
        raw = root.findtext("description")
        if not raw:
            return None
        text = _BBCODE_RE.sub("", raw)
        text = _WHITESPACE_RE.sub(" ", text).strip()
        return text or None

    @staticmethod
    def _parse_genres(root: ET.Element) -> List[str]:
        genres: List[str] = []
        for tag_name in ("categories/category", "tags/tag"):
            for el in root.findall(tag_name):
                name = (el.findtext("name") or el.get("name") or "").strip()
                if not name:
                    continue
                # Skip meta/weightless tags when AniDB marks them.
                if (el.get("infobox") or "").lower() == "true":
                    pass
                genres.append(name)
        # Prefer unique casing-insensitive names.
        seen = set()
        out: List[str] = []
        for name in genres:
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(name)
        return out

    @staticmethod
    def _parse_relations(root: ET.Element) -> List[Dict[str, Any]]:
        rels: List[Dict[str, Any]] = []
        for el in root.findall("relatedanime/anime"):
            rel_id = el.get("id")
            if not rel_id:
                continue
            try:
                rid = int(rel_id)
            except (TypeError, ValueError):
                continue
            rel_type = (el.get("type") or "other").strip()
            rels.append({"type": "anime", "name": rel_type, "rel_id": rid})
        return rels

    @staticmethod
    def _parse_resource_ids(root: ET.Element) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for res in root.findall("resources/resource"):
            type_raw = res.get("type")
            try:
                type_id = int(type_raw) if type_raw is not None else -1
            except (TypeError, ValueError):
                continue
            index_key = _RESOURCE_TO_INDEX.get(type_id)
            if not index_key:
                continue
            for entity in res.findall("externalentity"):
                ident = (entity.findtext("identifier") or "").strip()
                if not ident:
                    continue
                try:
                    out[index_key] = int(ident)
                except (TypeError, ValueError):
                    continue
                break
        return out

    @staticmethod
    def _parse_int_attr(root: ET.Element, attr: str) -> Optional[int]:
        raw = root.get(attr) or root.findtext(attr)
        if raw is None or str(raw).strip() == "":
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_date(raw: Optional[str]) -> Optional[int]:
        if not raw:
            return None
        text = str(raw).strip()
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
                return int(dt.timestamp())
            except ValueError:
                continue
        return None


__all__ = ["AnidbNetWrapper", "_TitlesIndex"]
