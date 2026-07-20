"""Tests for responsive cover selection helpers."""

from domain.cover_images import (
    ANILIST_COVER_DIMENSIONS,
    ANILIST_SIZE_LABELS,
    CoverVariant,
    cover_variants_from_mapping,
    largest_cover_url,
    needed_cover_px,
    pick_cover_url,
)


def test_needed_cover_px_multiplies_dpr():
    assert needed_cover_px(180, device_pixel_ratio=2) == 360
    assert needed_cover_px(0, device_pixel_ratio=2) == 0


def test_pick_cover_url_prefers_smallest_adequate():
    variants = [
        CoverVariant(url="s", size="small", width=100, height=140),
        CoverVariant(url="m", size="medium", width=230, height=326),
        CoverVariant(url="l", size="large", width=460, height=650),
        CoverVariant(url="xl", size="original", width=960, height=1360),
    ]
    assert pick_cover_url(variants, needed_px=200) == "m"
    assert pick_cover_url(variants, needed_px=400) == "l"
    assert pick_cover_url(variants, needed_px=50) == "s"


def test_pick_cover_url_falls_back_to_largest_when_none_adequate():
    variants = [
        {"url": "s", "size": "small", "width": 100},
        {"url": "m", "size": "medium", "width": 230},
    ]
    assert pick_cover_url(variants, needed_px=900) == "m"


def test_pick_cover_url_uses_fallback_when_empty():
    assert pick_cover_url([], needed_px=200, fallback="fb") == "fb"
    assert pick_cover_url(None, needed_px=200, fallback=None) is None


def test_pick_cover_url_unsized_uses_size_rank():
    variants = [
        {"url": "small-url", "size": "small"},
        {"url": "large-url", "size": "large"},
    ]
    assert pick_cover_url(variants, needed_px=400) == "large-url"


def test_anilist_cover_variants_map_extra_large_to_original():
    variants = cover_variants_from_mapping(
        {
            "medium": "http://m",
            "large": "http://l",
            "extraLarge": "http://xl",
        },
        dimensions_by_key=ANILIST_COVER_DIMENSIONS,
        size_labels=ANILIST_SIZE_LABELS,
    )
    by_size = {v.size: v for v in variants}
    assert by_size["medium"].width == 230
    assert by_size["large"].width == 460
    assert by_size["original"].width == 960
    assert largest_cover_url(variants) == "http://xl"
