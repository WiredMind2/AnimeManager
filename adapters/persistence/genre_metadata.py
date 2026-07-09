"""Resolve genre index ids stored in ``genres.value`` to display names."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

_GENRE_INDEX_TABLE = "genresindex"


def _is_genre_index_id(value: Any) -> bool:
    text = str(value).strip()
    return bool(text) and text.isdigit()


def genre_index_table_available(db: Any) -> bool:
    """Return True when the catalogue has a ``genresindex`` lookup table."""
    try:
        db.sql(f"SELECT 1 FROM {_GENRE_INDEX_TABLE} LIMIT 1")
        return True
    except Exception:
        return False


def resolve_stored_genre_values(db: Any, values: Sequence[Any]) -> list[str]:
    """Map stored genre rows (ids or legacy plain names) to sorted names."""
    if not values:
        return []

    ids: list[int] = []
    names: list[str] = []
    for raw in values:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        if _is_genre_index_id(text):
            ids.append(int(text))
        else:
            names.append(text)

    if ids:
        names.extend(_names_for_genre_ids(db, ids))
    return sorted(set(names))


def _names_for_genre_ids(db: Any, genre_ids: Iterable[int]) -> list[str]:
    unique_ids = sorted({int(i) for i in genre_ids})
    if not unique_ids:
        return []

    placeholders = ",".join("?" for _ in unique_ids)
    sql = (
        f"SELECT id, name FROM {_GENRE_INDEX_TABLE} "
        f"WHERE id IN ({placeholders})"
    )
    try:
        rows = db.sql(sql, unique_ids) or []
    except Exception:
        return [str(i) for i in unique_ids]

    by_id = {
        int(row[0]): str(row[1])
        for row in rows
        if row and row[1] is not None
    }
    return [by_id.get(gid, str(gid)) for gid in unique_ids]


def normalize_genre_values_for_store(db: Any, values: Sequence[Any]) -> list:
    """Convert genre names to ``genresindex`` ids when the lookup table exists."""
    if not values:
        return []
    if not genre_index_table_available(db):
        return sorted({str(v).strip() for v in values if v})

    out: set[int] = set()
    for raw in values:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        if _is_genre_index_id(text):
            out.add(int(text))
            continue
        genre_id = _lookup_or_create_genre_id(db, text)
        if genre_id is not None:
            out.add(genre_id)
    return sorted(out)


def _lookup_or_create_genre_id(db: Any, name: str) -> int | None:
    canonical = name.title().strip()
    if not canonical:
        return None

    rows = db.sql(
        f"SELECT id FROM {_GENRE_INDEX_TABLE} WHERE name = ?",
        (canonical,),
    )
    if rows:
        return int(rows[0][0])

    try:
        db.sql(
            f"INSERT INTO {_GENRE_INDEX_TABLE}(name) VALUES (?)",
            (canonical,),
            save=True,
        )
    except Exception:
        return None

    rows = db.sql(
        f"SELECT id FROM {_GENRE_INDEX_TABLE} WHERE name = ?",
        (canonical,),
    )
    if rows:
        return int(rows[0][0])
    return None
