"""Tests for auto-download preference resolution helpers."""

from __future__ import annotations

from application.services.auto_download_matching import ReleasePreference
from application.services.auto_download_prefs import (
    DEFAULT_BUILTIN_FEEDS,
    list_configured_feeds,
    normalize_prefs_row,
    resolve_release_preference,
    select_feeds_for_anime,
)


def test_normalize_prefs_defaults():
    prefs = normalize_prefs_row({}, settings={})
    assert prefs["source_mode"] == "rss"
    assert prefs["resolution"] == "720p"
    assert prefs["use_inferred"] is True
    assert prefs["feed_ids"] == []


def test_resolve_uses_explicit_then_inferred_then_top_publisher():
    inferred = ReleasePreference(publisher="erai-raws", resolution="1080p")
    settings = {"anime": {"topPublishers": ["SubsPlease", "SSA"]}}

    explicit = resolve_release_preference(
        {"publisher": "Judas", "resolution": None, "use_inferred": True},
        inferred=inferred,
        settings=settings,
    )
    assert explicit is not None
    assert explicit.publisher == "judas"
    assert explicit.resolution == "1080p"

    fallback = resolve_release_preference(
        {"publisher": None, "resolution": None, "use_inferred": False},
        inferred=inferred,
        settings=settings,
    )
    assert fallback is not None
    assert fallback.publisher == "subsplease"
    assert fallback.resolution == "720p"


def test_list_configured_feeds_injects_builtin_defaults():
    feeds = list_configured_feeds({})
    assert [f["id"] for f in feeds] == [f["id"] for f in DEFAULT_BUILTIN_FEEDS]


def test_select_feeds_filters_by_ids_and_enabled():
    settings = {
        "auto_download": {
            "feeds": {
                "builtin": [
                    {
                        "id": "subsplease-1080",
                        "label": "SP 1080",
                        "url": "https://example.com/1080",
                        "enabled": True,
                    },
                    {
                        "id": "subsplease-720",
                        "label": "SP 720",
                        "url": "https://example.com/720",
                        "enabled": False,
                    },
                ],
                "custom": [
                    {
                        "id": "custom-1",
                        "label": "Custom",
                        "url": "https://example.com/custom",
                        "enabled": True,
                    }
                ],
            }
        }
    }
    all_enabled = select_feeds_for_anime(settings, [])
    assert {f["id"] for f in all_enabled} == {"subsplease-1080", "custom-1"}
    only_custom = select_feeds_for_anime(settings, ["custom-1", "subsplease-720"])
    assert [f["id"] for f in only_custom] == ["custom-1"]
