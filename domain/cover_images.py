"""Cover image variants and responsive URL selection.

Providers expose multiple cover sizes. We store each variant with optional
pixel dimensions and pick the smallest image that still covers the display
slot (needed CSS pixels × device pixel ratio). If none are large enough,
the largest available image is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence

# Documented typical widths/heights when a provider does not return meta.
# Used only as defaults; real Kitsu meta.dimensions override these.
ANILIST_COVER_DIMENSIONS: dict[str, tuple[int, int]] = {
    "medium": (230, 326),
    "large": (460, 650),
    "extraLarge": (960, 1360),
}

JIKAN_COVER_DIMENSIONS: dict[str, tuple[int, int]] = {
    "small_image_url": (168, 236),
    "image_url": (225, 350),
    "large_image_url": (300, 450),
}

MAL_COVER_DIMENSIONS: dict[str, tuple[int, int]] = {
    "small": (100, 141),
    "medium": (225, 318),
    "large": (425, 600),
}

# Anilist GraphQL field → stored size label (VALID_ASSET_SIZES).
ANILIST_SIZE_LABELS: dict[str, str] = {
    "medium": "medium",
    "large": "large",
    "extraLarge": "original",
}

SIZE_RANK: dict[str, int] = {
    "small": 1,
    "medium": 2,
    "large": 3,
    "original": 4,
}


@dataclass(frozen=True, slots=True)
class CoverVariant:
    """One available cover URL with optional pixel dimensions."""

    url: str
    size: str = "medium"
    width: Optional[int] = None
    height: Optional[int] = None

    def as_dict(self) -> dict:
        out: dict = {"url": self.url, "size": self.size}
        if self.width is not None:
            out["width"] = int(self.width)
        if self.height is not None:
            out["height"] = int(self.height)
        return out


def needed_cover_px(css_px: float, *, device_pixel_ratio: float = 1.0) -> int:
    """Convert layout CSS pixels into the target image pixel width."""
    try:
        css = float(css_px)
    except (TypeError, ValueError):
        css = 0.0
    try:
        dpr = float(device_pixel_ratio)
    except (TypeError, ValueError):
        dpr = 1.0
    if css <= 0:
        return 0
    if dpr <= 0:
        dpr = 1.0
    return max(1, int(round(css * dpr)))


def _variant_width(variant: CoverVariant | Mapping) -> Optional[int]:
    if isinstance(variant, CoverVariant):
        width = variant.width
    else:
        width = variant.get("width")
    if width is None:
        return None
    try:
        value = int(width)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _variant_url(variant: CoverVariant | Mapping) -> Optional[str]:
    if isinstance(variant, CoverVariant):
        url = variant.url
    else:
        url = variant.get("url")
    if not url:
        return None
    text = str(url).strip()
    return text or None


def _variant_size_rank(variant: CoverVariant | Mapping) -> int:
    if isinstance(variant, CoverVariant):
        size = variant.size
    else:
        size = variant.get("size") or "medium"
    return SIZE_RANK.get(str(size), 0)


def pick_cover_url(
    variants: Sequence[CoverVariant | Mapping] | None,
    *,
    needed_px: int,
    fallback: Optional[str] = None,
) -> Optional[str]:
    """Return the smallest cover whose width is >= ``needed_px``.

    If no variant is wide enough, return the largest. Variants without a
    known width are only considered after all sized variants, ordered by
    size label rank. ``fallback`` is used when ``variants`` is empty.
    """
    items = list(variants or [])
    sized: list[tuple[int, str]] = []
    unsized: list[tuple[int, str]] = []
    for item in items:
        url = _variant_url(item)
        if not url:
            continue
        width = _variant_width(item)
        if width is not None:
            sized.append((width, url))
        else:
            unsized.append((_variant_size_rank(item), url))

    if sized:
        needed = max(0, int(needed_px or 0))
        adequate = [(w, u) for w, u in sized if w >= needed]
        if adequate:
            adequate.sort(key=lambda pair: pair[0])
            return adequate[0][1]
        sized.sort(key=lambda pair: pair[0], reverse=True)
        return sized[0][1]

    if unsized:
        unsized.sort(key=lambda pair: pair[0], reverse=True)
        return unsized[0][1]

    return fallback


def largest_cover_url(
    variants: Sequence[CoverVariant | Mapping] | None,
    *,
    fallback: Optional[str] = None,
) -> Optional[str]:
    """Return the largest known cover URL (for legacy ``anime.picture``)."""
    return pick_cover_url(variants, needed_px=10**9, fallback=fallback)


def cover_variants_from_mapping(
    urls_by_key: Mapping[str, Optional[str]],
    *,
    dimensions_by_key: Mapping[str, tuple[int, int]],
    size_labels: Mapping[str, str] | None = None,
) -> list[CoverVariant]:
    """Build variants from provider key→url using a dimension catalog."""
    out: list[CoverVariant] = []
    for key, url in urls_by_key.items():
        if not url:
            continue
        size = (size_labels or {}).get(key, key)
        dims = dimensions_by_key.get(key)
        width = dims[0] if dims else None
        height = dims[1] if dims else None
        out.append(
            CoverVariant(
                url=str(url),
                size=str(size),
                width=width,
                height=height,
            )
        )
    return out


def merge_kitsu_dimensions(
    poster: object,
    size: str,
) -> tuple[Optional[int], Optional[int]]:
    """Read Kitsu ``posterImage.meta.dimensions[size]`` when present."""
    meta = getattr(poster, "meta", None)
    if meta is None and isinstance(poster, Mapping):
        meta = poster.get("meta")
    if meta is None:
        return None, None
    dimensions = getattr(meta, "dimensions", None)
    if dimensions is None and isinstance(meta, Mapping):
        dimensions = meta.get("dimensions")
    if dimensions is None:
        return None, None
    entry = None
    if isinstance(dimensions, Mapping):
        entry = dimensions.get(size)
    else:
        entry = getattr(dimensions, size, None)
    if entry is None:
        return None, None
    if isinstance(entry, Mapping):
        width = entry.get("width")
        height = entry.get("height")
    else:
        width = getattr(entry, "width", None)
        height = getattr(entry, "height", None)
    try:
        w = int(width) if width is not None else None
    except (TypeError, ValueError):
        w = None
    try:
        h = int(height) if height is not None else None
    except (TypeError, ValueError):
        h = None
    return w, h


def variants_as_dicts(variants: Iterable[CoverVariant]) -> list[dict]:
    return [v.as_dict() for v in variants]
