"""Helpers for resolving effective auto-download preferences."""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional, Sequence

from application.services.auto_download_matching import ReleasePreference

SOURCE_MODES = frozenset({"search", "rss"})
DEFAULT_SOURCE_MODE = "rss"
DEFAULT_RESOLUTION = "720p"

DEFAULT_BUILTIN_FEEDS: list[dict[str, Any]] = [
    {
        "id": "subsplease-720",
        "label": "SubsPlease 720p",
        "url": "https://subsplease.org/rss/?r=720",
        "enabled": True,
        "builtin": True,
    },
    {
        "id": "subsplease-1080",
        "label": "SubsPlease 1080p",
        "url": "https://subsplease.org/rss/?r=1080",
        "enabled": False,
        "builtin": True,
    },
]


def _norm_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _norm_mode(value: Any) -> str:
    mode = str(value or DEFAULT_SOURCE_MODE).strip().lower()
    return mode if mode in SOURCE_MODES else DEFAULT_SOURCE_MODE


def _parse_feed_ids(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return [part.strip() for part in text.split(",") if part.strip()]
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    return []


def default_prefs_dict(
    *,
    settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return default preference fields from global settings."""
    auto_cfg = {}
    if isinstance(settings, Mapping):
        auto_cfg = settings.get("auto_download") or {}
        if not isinstance(auto_cfg, Mapping):
            auto_cfg = {}
    mode = _norm_mode(auto_cfg.get("default_source_mode"))
    resolution = _norm_text(auto_cfg.get("default_resolution")) or DEFAULT_RESOLUTION
    return {
        "source_mode": mode,
        "publisher": None,
        "resolution": resolution.lower() if resolution else DEFAULT_RESOLUTION,
        "feed_ids": [],
        "use_inferred": True,
    }


def normalize_prefs_row(
    row: Mapping[str, Any] | None,
    *,
    settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize a stored prefs row with defaults filled in."""
    base = default_prefs_dict(settings=settings)
    if not isinstance(row, Mapping):
        return base
    mode = _norm_mode(row.get("source_mode") or base["source_mode"])
    publisher = _norm_text(row.get("publisher"))
    resolution = _norm_text(row.get("resolution"))
    if resolution:
        resolution = resolution.lower()
    else:
        resolution = base["resolution"]
    feed_ids = _parse_feed_ids(row.get("feed_ids"))
    use_inferred_raw = row.get("use_inferred")
    if use_inferred_raw is None:
        use_inferred = True
    else:
        use_inferred = bool(use_inferred_raw)
    return {
        "source_mode": mode,
        "publisher": publisher.lower() if publisher else None,
        "resolution": resolution,
        "feed_ids": feed_ids,
        "use_inferred": use_inferred,
    }


def resolve_release_preference(
    prefs: Mapping[str, Any],
    *,
    inferred: Optional[ReleasePreference],
    settings: Mapping[str, Any] | None = None,
) -> Optional[ReleasePreference]:
    """Build effective release preference from explicit prefs, inference, defaults."""
    publisher = _norm_text(prefs.get("publisher"))
    resolution = _norm_text(prefs.get("resolution"))
    use_inferred = bool(prefs.get("use_inferred", True))

    if use_inferred and inferred is not None:
        if not publisher:
            publisher = inferred.publisher
        if not resolution:
            resolution = inferred.resolution

    if not publisher and isinstance(settings, Mapping):
        anime_cfg = settings.get("anime") or {}
        if isinstance(anime_cfg, Mapping):
            tops = anime_cfg.get("topPublishers") or []
            if isinstance(tops, Sequence) and tops:
                publisher = _norm_text(tops[0])

    if not resolution:
        defaults = default_prefs_dict(settings=settings)
        resolution = defaults["resolution"]

    if not publisher or not resolution:
        return None
    return ReleasePreference(
        publisher=publisher.lower(),
        resolution=resolution.lower(),
    )


def list_configured_feeds(
    settings: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return builtin + custom feed dicts from settings (may include disabled)."""
    out: list[dict[str, Any]] = []
    feeds_cfg: Mapping[str, Any] = {}
    if isinstance(settings, Mapping):
        auto_cfg = settings.get("auto_download") or {}
        if isinstance(auto_cfg, Mapping):
            raw_feeds = auto_cfg.get("feeds") or {}
            if isinstance(raw_feeds, Mapping):
                feeds_cfg = raw_feeds
    for key in ("builtin", "custom"):
        rows = feeds_cfg.get(key) or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            feed_id = _norm_text(row.get("id"))
            url = _norm_text(row.get("url"))
            if not feed_id or not url:
                continue
            out.append(
                {
                    "id": feed_id,
                    "label": _norm_text(row.get("label")) or feed_id,
                    "url": url,
                    "enabled": bool(row.get("enabled", True)),
                    "builtin": key == "builtin",
                }
            )
    if not any(f.get("builtin") for f in out):
        out = list(DEFAULT_BUILTIN_FEEDS) + [f for f in out if not f.get("builtin")]
    return out


def select_feeds_for_anime(
    settings: Mapping[str, Any] | None,
    feed_ids: Sequence[str] | None,
) -> list[dict[str, Any]]:
    """Return enabled feeds, optionally filtered by ``feed_ids``."""
    configured = list_configured_feeds(settings)
    enabled = [f for f in configured if f.get("enabled")]
    wanted = {str(x).strip() for x in (feed_ids or []) if str(x).strip()}
    if not wanted:
        return enabled
    return [f for f in enabled if f["id"] in wanted]
