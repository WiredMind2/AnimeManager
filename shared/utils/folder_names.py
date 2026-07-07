"""Filesystem-safe anime folder naming."""

from __future__ import annotations

from typing import Optional


def format_anime_folder_title(title: Optional[str]) -> str:
    """Sanitize a title for use in an on-disk anime folder name."""
    if title is None:
        return " "
    chars: list[str] = []
    for char in title:
        if char.isalnum() or char == " ":
            chars.append(char)
        elif char == "-":
            chars.append(" ")
    return "".join(chars)


def format_anime_folder_name(title: Optional[str], anime_id: int) -> str:
    """Return ``<sanitized title> - <anime_id>`` for library folders."""
    if not title:
        return f"anime_{anime_id}"
    cleaned = format_anime_folder_title(title).strip()
    if not cleaned:
        return f"anime_{anime_id}"
    cleaned = " ".join(cleaned.split())
    return f"{cleaned} - {anime_id}"
