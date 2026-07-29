"""Match RSS feed entries to an anime + release preference for auto-download."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional, Sequence

from adapters.feeds.rss_feed_adapter import RssFeedEntry
from adapters.search.subsplease import (
    expected_catalog_season,
    extract_title_season,
    parse_subsplease_release,
    release_matches_catalog,
)
from application.services.auto_download_matching import ReleasePreference, _parsed_as_dict

ParseTitleFn = Callable[[str], Any]


def _norm(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    return text or None


def entry_matches_anime(
    entry: RssFeedEntry,
    *,
    search_terms: Sequence[str],
) -> bool:
    """Return True when the entry title plausibly belongs to the anime."""
    title = str(entry.title or "").strip()
    if not title:
        return False
    terms = [str(t).strip() for t in search_terms if str(t).strip()]
    if not terms:
        return False

    sp = parse_subsplease_release(title)
    show_title = sp.show_title if sp is not None else title
    expected = expected_catalog_season(terms)
    release_season = extract_title_season(show_title) or 1
    if release_season != expected:
        return False
    for term in terms:
        if release_matches_catalog(show_title, term):
            return True
        if release_matches_catalog(title, term):
            return True
    return False


def entry_matches_preference(
    entry: RssFeedEntry,
    *,
    preference: ReleasePreference,
    episode: int,
    parse_title: ParseTitleFn,
) -> bool:
    """Return True when entry matches publisher/resolution/episode."""
    title = str(entry.title or "").strip()
    if not title:
        return False

    sp = parse_subsplease_release(title)
    if sp is not None:
        if sp.batch_range is not None:
            return False
        if sp.episode is not None and int(sp.episode) != int(episode):
            return False

    try:
        parsed = _parsed_as_dict(parse_title(title))
    except Exception:  # noqa: BLE001
        parsed = {}

    publisher = _norm(parsed.get("publisher"))
    if sp is not None and not publisher:
        publisher = "subsplease"
    resolution = _norm(parsed.get("resolution"))
    if publisher != preference.publisher:
        return False
    if resolution != preference.resolution:
        return False

    if bool(parsed.get("is_batch")):
        return False

    ep = parsed.get("episode")
    try:
        ep_i = int(ep) if ep is not None else None
    except (TypeError, ValueError):
        ep_i = None
    if sp is not None and sp.episode is not None:
        ep_i = int(sp.episode)
    if ep_i is None or ep_i != int(episode):
        return False
    return True


def find_rss_candidate(
    entries: Iterable[RssFeedEntry],
    *,
    search_terms: Sequence[str],
    preference: ReleasePreference,
    episode: int,
    parse_title: ParseTitleFn,
    seen_keys: set[tuple[str, str]] | None = None,
) -> Optional[dict[str, Any]]:
    """Pick the first matching unseen RSS entry as a download candidate dict."""
    seen = seen_keys or set()
    for entry in entries:
        key = (entry.feed_id, entry.item_key)
        if key in seen:
            continue
        if not entry_matches_anime(entry, search_terms=search_terms):
            continue
        if not entry_matches_preference(
            entry,
            preference=preference,
            episode=episode,
            parse_title=parse_title,
        ):
            continue
        url = entry.download_url
        if not url:
            continue
        return {
            "name": entry.title,
            "link": url,
            "url": url,
            "magnet": url if url.lower().startswith("magnet:") else None,
            "infohash": None,
            "feed_id": entry.feed_id,
            "item_key": entry.item_key,
            "source": "rss",
        }
    return None
