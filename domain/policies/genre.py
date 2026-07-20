"""Pure policies for genre browse and search."""

from __future__ import annotations

from typing import Sequence, Union

from domain.errors import ValidationError

# Canonical AniList/MAL genre set, title-cased to match APIUtils.save_genres normalization.
# Ordered tuple drives stable multi-genre URL / label ordering.
GENRE_ORDER: tuple[str, ...] = (
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
)

GENRES: frozenset[str] = frozenset(GENRE_ORDER)

_GENRE_LOOKUP: dict[str, str] = {g.lower(): g for g in GENRE_ORDER}
_GENRE_RANK: dict[str, int] = {g: i for i, g in enumerate(GENRE_ORDER)}


def normalize_genre(value: str) -> str:
    """Return a canonical genre name or raise ``ValidationError``."""
    normalized = (value or "").strip()
    if not normalized:
        raise ValidationError("Genre name is required.")
    canonical = _GENRE_LOOKUP.get(normalized.lower())
    if canonical is None:
        allowed = ", ".join(GENRE_ORDER)
        raise ValidationError(f"Genre must be one of: {allowed}.")
    return canonical


def normalize_genres(values: Union[str, Sequence[str]]) -> list[str]:
    """Return a deduped, canonically ordered list of genre names.

    Strings may be comma-separated (``\"Action,Comedy\"``). Empty input
    or an empty list raises ``ValidationError``.
    """
    tokens: list[str] = []
    if isinstance(values, str):
        tokens = [part.strip() for part in values.split(",")]
    else:
        for item in values:
            if item is None:
                continue
            text = str(item).strip()
            if not text:
                continue
            if "," in text:
                tokens.extend(part.strip() for part in text.split(","))
            else:
                tokens.append(text)

    if not tokens:
        raise ValidationError("At least one genre is required.")

    seen: set[str] = set()
    canonical: list[str] = []
    for token in tokens:
        if not token:
            continue
        name = normalize_genre(token)
        if name in seen:
            continue
        seen.add(name)
        canonical.append(name)

    if not canonical:
        raise ValidationError("At least one genre is required.")

    canonical.sort(key=lambda g: _GENRE_RANK[g])
    return canonical


def format_genre_label(genres: Union[str, Sequence[str]]) -> str:
    """Human label such as ``Comedy`` or ``Action + Comedy``."""
    names = normalize_genres(genres)
    return " + ".join(names)


def genres_contain_all(
    available: Sequence[str] | None,
    required: Sequence[str],
) -> bool:
    """Return True when ``available`` includes every genre in ``required``."""
    if not required:
        return True
    have = {
        _GENRE_LOOKUP.get(str(g).strip().lower(), "")
        for g in (available or [])
        if g is not None and str(g).strip()
    }
    have.discard("")
    need = set(normalize_genres(list(required)))
    return need.issubset(have)
