"""Tiny icon/PhotoImage loader with caching.

Used by the header bar (menu/filter/close), the loading spinner and the
anime-card placeholder. All paths are resolved against
:data:`clients.tk.theme.ASSETS_DIR` (the bundled ``icons/`` folder).

Pillow is the only required dependency: it is already pinned via
the project's optional GUI extras and the existing imports across the
client codebase.
"""

from __future__ import annotations

import os
import tkinter as tk
import urllib.request
from pathlib import Path
from typing import Optional

from PIL import Image, ImageTk

from clients.tk.theme import ASSETS_DIR, load_theme


_image_cache: dict[tuple[str, Optional[tuple[int, int]]], ImageTk.PhotoImage] = {}
_gif_cache: dict[str, list[tk.PhotoImage]] = {}


def _to_size(size: Optional[tuple[int, int]] | None) -> Optional[tuple[int, int]]:
    if size is None:
        return None
    try:
        w, h = int(size[0]), int(size[1])
        if w <= 0 or h <= 0:
            return None
        return (w, h)
    except (TypeError, ValueError, IndexError):
        return None


def asset_path(name: str) -> Path:
    """Return the absolute path of an asset stored in ``icons/``."""
    return ASSETS_DIR / name


def load_image(
    name: str,
    size: Optional[tuple[int, int]] = None,
    *,
    optional: bool = False,
) -> Optional[ImageTk.PhotoImage]:
    """Load an icon as :class:`PIL.ImageTk.PhotoImage` with caching.

    ``size`` resizes the image with high-quality LANCZOS. When the file
    isn't found and ``optional`` is ``True`` we return ``None`` so the
    caller can render a fallback graphic.
    """
    path = asset_path(name)
    key = (str(path), _to_size(size))
    cached = _image_cache.get(key)
    if cached is not None:
        return cached
    if not path.is_file():
        if optional:
            return None
        raise FileNotFoundError(f"Icon not found: {path}")
    try:
        img = Image.open(path)
        normalized = _to_size(size)
        if normalized is not None:
            img = img.resize(normalized, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        _image_cache[key] = photo
        return photo
    except OSError:
        if optional:
            return None
        raise


def load_gif_frames(name: str) -> list[tk.PhotoImage]:
    """Return all frames of an animated GIF as :class:`tk.PhotoImage`.

    Stored in a cache keyed by absolute path. The frames must be kept
    alive (Tk holds weak refs), hence the module-level cache.
    """
    path = asset_path(name)
    cache_key = str(path)
    if cache_key in _gif_cache:
        return _gif_cache[cache_key]
    if not path.is_file():
        _gif_cache[cache_key] = []
        return []
    frames: list[tk.PhotoImage] = []
    index = 0
    while True:
        try:
            frame = tk.PhotoImage(file=str(path), format=f"gif -index {index}")
        except tk.TclError:
            break
        frames.append(frame)
        index += 1
    _gif_cache[cache_key] = frames
    return frames


def blank_image(width: int, height: int, color: str) -> ImageTk.PhotoImage:
    """Return a solid-color :class:`PhotoImage` of the requested size."""
    key = (f"__blank::{color}", (width, height))
    cached = _image_cache.get(key)
    if cached is not None:
        return cached
    img = Image.new("RGB", (max(1, width), max(1, height)), color)
    photo = ImageTk.PhotoImage(img)
    _image_cache[key] = photo
    return photo


def card_placeholder(width: int, height: int) -> ImageTk.PhotoImage:
    """Get the legacy ``placeholder.png`` resized for cards."""
    icon = load_image("placeholder.png", (width, height), optional=True)
    if icon is not None:
        return icon
    return blank_image(width, height, load_theme().color("Gray3"))


def fetch_poster_to_disk(url: str, dest: Path, timeout: float = 5.0) -> Optional[Path]:
    """Download a poster image into ``dest`` (atomic-ish)."""
    if not url:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "AnimeManager/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response, tmp.open("wb") as fp:
            fp.write(response.read())
        os.replace(tmp, dest)
        return dest
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def load_from_disk(path: Path, size: Optional[tuple[int, int]]) -> Optional[ImageTk.PhotoImage]:
    """Load an arbitrary on-disk image, no caching."""
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return None
        img = Image.open(path)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        normalized = _to_size(size)
        if normalized is not None:
            img = img.resize(normalized, Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)
    except (OSError, ValueError):
        return None


def clear_caches() -> None:
    """Test helper: drop the module-level caches."""
    _image_cache.clear()
    _gif_cache.clear()


__all__ = [
    "asset_path",
    "blank_image",
    "card_placeholder",
    "clear_caches",
    "fetch_poster_to_disk",
    "load_from_disk",
    "load_gif_frames",
    "load_image",
]
