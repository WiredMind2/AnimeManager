"""SubsPlease JSON search API client.

Used for:
* auto-download 720p episode catch-up (``search`` / ``search_for_episode``)
* interactive torrent search via :class:`SearchFacade` (``search_interactive``)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

from adapters.search.subsplease import (
    parse_subsplease_release,
    release_matches_catalog,
)

_LOG = logging.getLogger("animemanager.subsplease_api")

_DEFAULT_UA = "AnimeManager/1.0 (+local; rss-auto-download)"
_API_BASE = "https://subsplease.org/api/"
_ENGINE_URL = "https://subsplease.org/"
_INFOHASH_RE = re.compile(r"xt=urn:btih:([A-Za-z0-9]+)", re.IGNORECASE)
_ASCII_QUERY_RE = re.compile(r"[A-Za-z0-9]")

# Prefer short, searchable Latin queries; skip pure CJK / single-letter noise.
_MIN_ASCII_QUERY_LEN = 4


def _default_fetch(url: str, timeout_s: float) -> str:
    req = Request(url, headers={"User-Agent": _DEFAULT_UA})
    with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 — fixed SubsPlease API host
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def _extract_infohash(magnet: str) -> Optional[str]:
    match = _INFOHASH_RE.search(magnet or "")
    if not match:
        return None
    return match.group(1).lower()


def _magnet_size_bytes(magnet: str) -> int:
    """Best-effort size from magnet ``xl`` query param; ``0`` when absent."""
    try:
        qs = parse_qs(urlparse(magnet).query)
        raw = (qs.get("xl") or [None])[0]
        if raw is None:
            return 0
        return max(0, int(str(raw).strip()))
    except (TypeError, ValueError, AttributeError):
        return 0


def _episode_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _normalize_resolution(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().removesuffix("p")
    return text or None


def is_useful_search_query(term: str) -> bool:
    """Return True when ``term`` is worth sending to the SubsPlease search API."""
    clean = str(term or "").strip()
    if not clean:
        return False
    ascii_chars = "".join(_ASCII_QUERY_RE.findall(clean))
    return len(ascii_chars) >= _MIN_ASCII_QUERY_LEN


def search_query_variants(term: str) -> list[str]:
    """Yield increasingly shorter ASCII-friendly queries for a catalog title.

    SubsPlease search returns an empty list for overly long synonym strings, so
    prefer the segment before ``:`` / em-dash and a short word prefix.
    """
    clean = str(term or "").strip()
    if not clean or not is_useful_search_query(clean):
        return []
    variants: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        text = " ".join(str(value or "").split()).strip(" -–—,;:")
        if not text or not is_useful_search_query(text):
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        variants.append(text)

    _add(clean)
    for sep in (":", "：", "–", "—", " - ", "～"):
        if sep in clean:
            _add(clean.split(sep, 1)[0])
            break
    words = [w for w in re.split(r"\s+", clean) if w]
    if len(words) > 4:
        _add(" ".join(words[:4]))
    if len(words) > 6:
        _add(" ".join(words[:6]))
    return variants


def _display_name(
    *,
    result_name: str,
    show: str,
    episode: Optional[int],
    resolution: str,
    interactive: bool,
) -> str:
    """Build a title ``title_parser`` / catch-up helpers understand."""
    res_label = f"{resolution}p"
    name = str(result_name or "").strip()
    show_title = show or (name.rsplit(" - ", 1)[0].strip() if name else "")
    if not show_title:
        show_title = name or "release"

    if interactive:
        if name:
            return f"[SubsPlease] {name} ({res_label})"
        if episode is not None:
            return f"[SubsPlease] {show_title} - {episode:02d} ({res_label})"
        return f"[SubsPlease] {show_title} ({res_label})"

    # Catch-up: stable name that parse_subsplease_release understands.
    if episode is not None:
        return f"[SubsPlease] {show_title} - {episode:02d} ({res_label}) [API].mkv"
    return f"[SubsPlease] {name or show_title} ({res_label}) [API].mkv"


def parse_search_payload(
    payload: Any,
    *,
    resolution: str | None = "720",
    include_batches: bool = False,
) -> list[dict[str, Any]]:
    """Normalize a SubsPlease ``f=search`` JSON object into candidate dicts.

    * ``resolution="720"`` (default): keep only that resolution (catch-up).
    * ``resolution=None``: keep every resolution with a magnet.
    * ``include_batches=False`` (default): skip null-episode / batch keys.
    * ``include_batches=True``: include batches (interactive search).
    """
    if not isinstance(payload, dict):
        return []
    wanted = _normalize_resolution(resolution)
    # Interactive rows use the short display form when all resolutions are kept
    # and/or batches are included (SearchFacade path).
    interactive = wanted is None
    out: list[dict[str, Any]] = []
    for result_name, result_data in payload.items():
        if not isinstance(result_data, dict):
            continue
        show = str(result_data.get("show") or "").strip()
        episode = _episode_int(result_data.get("episode"))
        # Batch keys look like "Show (01-12)" with null episode.
        if episode is None and not include_batches:
            continue
        page = str(result_data.get("page") or "").strip()
        downloads = result_data.get("downloads")
        if not isinstance(downloads, list):
            continue
        for download in downloads:
            if not isinstance(download, dict):
                continue
            res = str(download.get("res") or "").strip().lower().removesuffix("p")
            if not res:
                continue
            if wanted is not None and res != wanted:
                continue
            magnet = str(download.get("magnet") or "").strip()
            if not magnet.lower().startswith("magnet:"):
                continue
            show_title = show or str(result_name or "").rsplit(" - ", 1)[0].strip()
            if not show_title:
                show_title = str(result_name or "release").strip() or "release"
            display = _display_name(
                result_name=str(result_name or ""),
                show=show_title,
                episode=episode,
                resolution=res,
                interactive=interactive,
            )
            desc_link = f"{_ENGINE_URL}shows/{page}" if page else ""
            out.append(
                {
                    "name": display,
                    "show": show_title,
                    "episode": episode,
                    "link": magnet,
                    "url": magnet,
                    "magnet": magnet,
                    "infohash": _extract_infohash(magnet),
                    "resolution": f"{res}p",
                    "publisher": "subsplease",
                    "source": "subsplease-api",
                    "size": _magnet_size_bytes(magnet),
                    "seeds": 0,
                    "leech": 0,
                    "engine_url": _ENGINE_URL,
                    "desc_link": desc_link,
                }
            )
    return out


def find_subsplease_api_candidate(
    results: Sequence[dict[str, Any]],
    *,
    search_terms: Sequence[str],
    episode: int,
) -> Optional[dict[str, Any]]:
    """Pick the first API result matching catalog terms and target episode."""
    terms = [str(t).strip() for t in search_terms if str(t).strip()]
    if not terms:
        return None
    target = int(episode)
    for row in results:
        if not isinstance(row, dict):
            continue
        ep = _episode_int(row.get("episode"))
        name = str(row.get("name") or "").strip()
        show = str(row.get("show") or "").strip()
        if ep is None and name:
            parsed = parse_subsplease_release(name)
            if parsed is not None:
                ep = parsed.episode
                show = show or parsed.show_title
        if ep is None or ep != target:
            continue
        show_title = show or name
        matched = False
        for term in terms:
            if release_matches_catalog(show_title, term):
                matched = True
                break
            if name and release_matches_catalog(name, term):
                matched = True
                break
        if not matched:
            continue
        magnet = str(row.get("magnet") or row.get("link") or row.get("url") or "").strip()
        if not magnet:
            continue
        return dict(row)
    return None


class SubsPleaseSearchAdapter:
    """HTTP client for SubsPlease ``f=search``."""

    def __init__(
        self,
        *,
        opener: Callable[[str, float], str] | None = None,
        timeout_s: float = 20.0,
        max_pages: int = 3,
        resolution: str = "720",
        timezone: str = "UTC",
    ) -> None:
        self._opener = opener or _default_fetch
        self._timeout_s = float(timeout_s)
        self._max_pages = max(1, int(max_pages))
        self._resolution = str(resolution or "720").strip().removesuffix("p") or "720"
        self._timezone = str(timezone or "UTC").strip() or "UTC"

    def _search_url(self, query: str, page: int) -> str:
        params = urlencode(
            {
                "f": "search",
                "tz": self._timezone,
                "s": query,
                "p": str(page),
            },
            quote_via=quote,
        )
        return f"{_API_BASE}?{params}"

    def _collect(
        self,
        query: str,
        *,
        resolution: str | None,
        include_batches: bool,
    ) -> list[dict[str, Any]]:
        clean = str(query or "").strip()
        if not clean or not is_useful_search_query(clean):
            return []
        collected: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for page in range(self._max_pages):
            url = self._search_url(clean, page)
            try:
                raw = self._opener(url, self._timeout_s)
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                _LOG.warning("SubsPlease search failed for %r page %s: %s", clean, page, exc)
                break
            except Exception as exc:  # noqa: BLE001
                _LOG.warning("SubsPlease search failed for %r page %s: %s", clean, page, exc)
                break
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                _LOG.warning("SubsPlease search returned invalid JSON for %r", clean)
                break
            # API returns {} or [] when there are no hits (long queries often get []).
            if not payload:
                break
            if not isinstance(payload, dict):
                break
            page_rows = parse_search_payload(
                payload,
                resolution=resolution,
                include_batches=include_batches,
            )
            for row in page_rows:
                key = str(row.get("infohash") or row.get("magnet") or row.get("name") or "")
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                collected.append(row)
            if len(payload) == 0:
                break
        return collected

    def search(self, query: str) -> list[dict[str, Any]]:
        """Search SubsPlease and return catch-up candidates (default resolution)."""
        return self._collect(
            query,
            resolution=self._resolution,
            include_batches=False,
        )

    def search_interactive(self, query: str) -> list[dict[str, Any]]:
        """Search SubsPlease for interactive torrent UI (all resolutions + batches)."""
        return self._collect(
            query,
            resolution=None,
            include_batches=True,
        )

    def search_for_episode(
        self,
        search_terms: Sequence[str],
        *,
        episode: int,
    ) -> Optional[dict[str, Any]]:
        """Try useful search terms until a title+episode catch-up match is found."""
        tried: set[str] = set()
        for term in search_terms:
            for query in search_query_variants(term):
                key = query.lower()
                if key in tried:
                    continue
                tried.add(key)
                results = self.search(query)
                match = find_subsplease_api_candidate(
                    results,
                    search_terms=search_terms,
                    episode=episode,
                )
                if match is not None:
                    return match
        return None
