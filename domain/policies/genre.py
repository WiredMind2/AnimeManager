"""Pure policies for genre browse and search."""

from __future__ import annotations

from domain.errors import ValidationError

# Canonical AniList/MAL genre set, title-cased to match APIUtils.save_genres normalization.
GENRES: frozenset[str] = frozenset(
    {
        "Action",
        "Adventure",
        "Comedy",
        "Drama",
        "Ecchi",
        "Fantasy",
        "Hentai",
        "Horror",
        "Mahou Shoujo",
        "Mecha",
        "Music",
        "Mystery",
        "Psychological",
        "Romance",
        "Sci-Fi",
        "Slice Of Life",
        "Sports",
        "Supernatural",
        "Thriller",
    }
)

_GENRE_LOOKUP: dict[str, str] = {g.lower(): g for g in GENRES}


def normalize_genre(value: str) -> str:
    """Return a canonical genre name or raise ``ValidationError``."""
    normalized = (value or "").strip()
    if not normalized:
        raise ValidationError("Genre name is required.")
    canonical = _GENRE_LOOKUP.get(normalized.lower())
    if canonical is None:
        allowed = ", ".join(sorted(GENRES))
        raise ValidationError(f"Genre must be one of: {allowed}.")
    return canonical


def format_genre_label(genre: str) -> str:
    """Human label for a validated genre token."""
    return normalize_genre(genre)
