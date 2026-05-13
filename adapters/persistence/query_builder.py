"""
Strict, whitelist-only query argument builder for the anime list view.

The legacy `BaseDB.filter` interface concatenates the produced fragments
directly into SQL, so this builder accepts **only** whitelisted enum-like
inputs and validated integers. Anything outside the allow-list collapses
to a safe default (`DEFAULT`) before SQL is touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple


__all__ = ["AnimeListQuery", "build_anime_list_query", "ALLOWED_CRITERIA"]


ALLOWED_CRITERIA: frozenset = frozenset(
    {
        "DEFAULT",
        "LIKED",
        "NONE",
        "UPCOMING",
        "FINISHED",
        "AIRING",
        "RATED",
        "RANDOM",
        "WATCHING",
        "SEEN",
        "WATCHLIST",
    }
)

_RATING_GUARD = "(rating NOT IN('R+','Rx') OR rating IS NULL)"


def _default_table(user_id: int) -> str:
    """Build the canonical `anime` join. `user_id` is forced to int upstream."""
    return (
        f"anime LEFT JOIN user_tags "
        f"ON user_tags.anime_id = anime.id AND user_id={int(user_id)}"
    )


def _watching_table(user_id: int) -> str:
    return (
        "anime LEFT JOIN broadcasts ON anime.id = broadcasts.id "
        f"LEFT JOIN user_tags ON user_tags.anime_id = anime.id AND user_id={int(user_id)}"
    )


@dataclass(frozen=True)
class AnimeListQuery:
    """Whitelisted representation of an anime-list filter."""

    table: str
    filter_clause: str
    order: str
    sort: str
    range: Tuple[int, int]
    params: Mapping[str, Any]

    def to_args(self) -> Dict[str, Any]:
        """Convert to the kw-arg shape consumed by `BaseDB.filter`."""
        return {
            "table": self.table,
            "sort": self.sort,
            "range": self.range,
            "order": self.order,
            "filter": self.filter_clause,
        }


def build_anime_list_query(
    criteria: str,
    listrange: Tuple[int, int],
    *,
    hide_rated: bool,
    user_id: int,
) -> AnimeListQuery:
    """Build a query spec from a whitelisted criteria value.

    Only enum values from `ALLOWED_CRITERIA` are accepted; everything else
    collapses to `DEFAULT`. Integer values are coerced through `int()`.
    The produced SQL fragments contain no caller-controlled text.
    """
    if criteria not in ALLOWED_CRITERIA:
        criteria = "DEFAULT"

    start, stop = listrange
    start = max(0, int(start))
    stop = max(start + 1, int(stop))
    safe_range = (start, stop)

    uid = int(user_id)
    params: Dict[str, Any] = {"user_id": uid}

    if criteria == "DEFAULT":
        clause = "anime.status != 'UPCOMING' AND anime.status != 'UNKNOWN'"
        if hide_rated:
            clause += f" AND {_RATING_GUARD}"
        return AnimeListQuery(
            table=_default_table(uid),
            filter_clause=clause,
            order="anime.date_from",
            sort="DESC",
            range=safe_range,
            params=params,
        )

    base_filter = "status != 'UPCOMING'"
    if hide_rated:
        base_filter += f" AND {_RATING_GUARD}"

    order = "date_from"
    sort = "DESC"
    table = _default_table(uid)
    clause: str

    if criteria == "LIKED":
        clause = f"liked = 1 AND {base_filter}"
    elif criteria == "NONE":
        clause = f"(tag IS NULL OR tag = 'NONE') AND {base_filter}"
    elif criteria in ("UPCOMING", "FINISHED", "AIRING"):
        if criteria == "UPCOMING":
            sort = "ASC"
            clause = f"status = '{criteria}'"
            if hide_rated:
                clause += f" AND {_RATING_GUARD}"
        else:
            clause = f"status = '{criteria}' AND {base_filter}"
        params["status"] = criteria
    elif criteria == "RATED":
        clause = "rating IN('R+','Rx') AND status != 'UPCOMING'"
    elif criteria == "RANDOM":
        order = "RANDOM()"
        clause = "anime.picture IS NOT NULL"
    elif criteria == "WATCHING":
        table = _watching_table(uid)
        clause = f"tag = '{criteria}' AND status != 'UPCOMING'"
        params["tag"] = criteria
    else:
        clause = f"tag = '{criteria}' AND {base_filter}"
        params["tag"] = criteria

    return AnimeListQuery(
        table=table,
        filter_clause=clause,
        order=order,
        sort=sort,
        range=safe_range,
        params=params,
    )
