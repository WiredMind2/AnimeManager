"""Inspect anime persistence across ingestion and hydration paths.

This script exercises the write pipeline through:
- coordinator search
- coordinator season browse
- coordinator latest schedule fetch
- hydration adapter
- explicit backfill write

It then inspects persisted rows (`anime`, `title_synonyms`, optional `genres`,
and `indexList`) for anime 2210 plus sampled ids touched by these flows.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable, Sequence

from adapters.metadata.anime_hydration_adapter import AnimeHydrationAdapter
from application.services.anime_write_service import AnimeWriteService, WriteSource
from application.services.api_coordinator import APICoordinator
from composition.bootstrap import bootstrap_embedded_deps


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_sql(database, sql: str, params: Sequence[Any] = (), *, to_dict: bool = False):
    try:
        return database.sql(sql, params, to_dict=to_dict, use_cache=False) or []
    except TypeError:
        return database.sql(sql, params, to_dict=to_dict) or []
    except Exception:
        return []


def _extract_ids(result: Any) -> list[int]:
    if result is None:
        return []
    entries: Iterable[Any]
    if isinstance(result, list):
        entries = result
    elif hasattr(result, "records"):
        entries = getattr(result, "records") or []
    elif hasattr(result, "animes"):
        entries = getattr(result, "animes") or []
    else:
        try:
            entries = list(result)
        except Exception:
            return []

    out: list[int] = []
    for item in entries:
        value = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
        rid = _safe_int(value)
        if rid is not None:
            out.append(rid)
    return out


def _normalize_strings(values: Any) -> list[str]:
    if not values:
        return []
    if isinstance(values, (list, tuple, set)):
        return [str(v) for v in values if v]
    return [str(values)]


def _norm_token(value: str) -> str:
    return " ".join(value.lower().split())


@dataclass
class AnimeSnapshot:
    id: int
    title: str | None
    episodes: int | None
    status: str | None
    synonym_count: int
    genre_count: int
    has_index_row: bool
    mal_id: int | None
    anilist_id: int | None
    kitsu_id: int | None
    payload_synonyms_missing: list[str]
    payload_genres_missing: list[str]


def _snapshot_for_id(database, api, anime_id: int) -> AnimeSnapshot:
    anime_rows = _safe_sql(
        database,
        "SELECT id, title, episodes, status FROM anime WHERE id=?",
        (anime_id,),
        to_dict=True,
    )
    anime_row = anime_rows[0] if anime_rows else {}
    title = anime_row.get("title") if anime_row else None
    episodes = _safe_int(anime_row.get("episodes")) if anime_row else None
    status = anime_row.get("status") if anime_row else None

    synonyms = [
        str(row[0])
        for row in _safe_sql(
            database,
            "SELECT value FROM title_synonyms WHERE id=? ORDER BY value",
            (anime_id,),
        )
        if row and row[0]
    ]

    genres = [
        str(row[0])
        for row in _safe_sql(
            database,
            "SELECT value FROM genres WHERE id=? ORDER BY value",
            (anime_id,),
        )
        if row and row[0]
    ]

    index_rows = _safe_sql(
        database,
        "SELECT * FROM indexList WHERE id=?",
        (anime_id,),
        to_dict=True,
    )
    index_row = index_rows[0] if index_rows else {}

    payload_synonyms_missing: list[str] = []
    payload_genres_missing: list[str] = []
    try:
        payload = api.anime(anime_id, _persist=False)
    except Exception:
        payload = None
    if payload is not None:
        source_synonyms = _normalize_strings(getattr(payload, "title_synonyms", None))
        source_genres = _normalize_strings(getattr(payload, "genres", None))
        synonym_set = {_norm_token(value) for value in synonyms}
        genre_set = {_norm_token(value) for value in genres}
        payload_synonyms_missing = [
            value for value in source_synonyms if _norm_token(value) not in synonym_set
        ]
        payload_genres_missing = [
            value for value in source_genres if _norm_token(value) not in genre_set
        ]

    return AnimeSnapshot(
        id=anime_id,
        title=title,
        episodes=episodes,
        status=status,
        synonym_count=len(synonyms),
        genre_count=len(genres),
        has_index_row=bool(index_row),
        mal_id=_safe_int(index_row.get("mal_id")) if index_row else None,
        anilist_id=_safe_int(index_row.get("anilist_id")) if index_row else None,
        kitsu_id=_safe_int(index_row.get("kitsu_id")) if index_row else None,
        payload_synonyms_missing=payload_synonyms_missing,
        payload_genres_missing=payload_genres_missing,
    )


def _library_sample_ids(database, limit: int) -> list[int]:
    rows = _safe_sql(
        database,
        "SELECT id FROM anime WHERE id IS NOT NULL ORDER BY id DESC LIMIT ?",
        (max(1, limit),),
    )
    out: list[int] = []
    for row in rows:
        if not row:
            continue
        rid = _safe_int(row[0])
        if rid is not None:
            out.append(rid)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect anime persistence write paths.")
    parser.add_argument("--anime-id", type=int, default=2210, help="Primary anime id to verify.")
    parser.add_argument("--query", default="chaos head", help="Search query for ingestion path.")
    parser.add_argument("--limit", type=int, default=8, help="Per-path fetch limit.")
    parser.add_argument(
        "--library-sample-size",
        type=int,
        default=2,
        help="Extra ids sampled from local library table.",
    )
    args = parser.parse_args()

    deps = bootstrap_embedded_deps()
    write_service = AnimeWriteService(
        db_manager=deps.db_manager,
        log_fn=lambda msg: deps.logger.log("INSPECT", msg),
    )
    if hasattr(deps.api, "set_write_service"):
        deps.api.set_write_service(write_service)

    coordinator = APICoordinator()
    coordinator.set_api(deps.api)
    coordinator.set_database_manager(deps.db_manager)
    coordinator.set_write_service(write_service)

    hydration = AnimeHydrationAdapter(
        deps.api,
        deps.database,
        write_service=write_service,
        log_fn=lambda msg: deps.logger.log("INSPECT", msg),
    )

    now = datetime.now()
    season = "WINTER"
    if now.month in (3, 4, 5):
        season = "SPRING"
    elif now.month in (6, 7, 8):
        season = "SUMMER"
    elif now.month in (9, 10, 11):
        season = "FALL"

    path_ids: dict[str, list[int]] = {}

    search_result = coordinator.search_anime(args.query, limit=args.limit)
    path_ids["search"] = _extract_ids(search_result)

    season_result = coordinator.browse_season(
        year=now.year,
        season=season,
        limit=args.limit,
    )
    path_ids["season"] = _extract_ids(season_result)

    latest_result = coordinator.fetch_latest(limit=args.limit)
    path_ids["schedule"] = _extract_ids(latest_result)

    hydrated_ok = hydration.hydrate_anime(args.anime_id)
    path_ids["hydration"] = [args.anime_id] if hydrated_ok else []

    backfill_ids = [args.anime_id]
    for source in ("search", "season", "schedule"):
        if path_ids.get(source):
            backfill_ids.append(path_ids[source][0])
    dedup_backfill_ids = list(dict.fromkeys(backfill_ids))
    persisted_backfill: list[int] = []
    for anime_id in dedup_backfill_ids:
        try:
            payload = deps.api.anime(anime_id, _persist=False)
        except Exception:
            continue
        if payload is None:
            continue
        ok = write_service.persist_legacy_anime(
            payload,
            source=WriteSource.BACKFILL,
            catalog_id=anime_id,
        )
        if ok:
            persisted_backfill.append(anime_id)
    path_ids["backfill"] = persisted_backfill

    inspected_ids = [args.anime_id]
    for key in ("search", "season", "schedule", "backfill"):
        if path_ids.get(key):
            inspected_ids.append(path_ids[key][0])
    inspected_ids.extend(_library_sample_ids(deps.database, args.library_sample_size))
    inspected_ids = list(dict.fromkeys(i for i in inspected_ids if i is not None))

    snapshots = [_snapshot_for_id(deps.database, deps.api, anime_id) for anime_id in inspected_ids]
    coordinator.close()

    report = {
        "paths": {k: v[: args.limit] for k, v in path_ids.items()},
        "inspected_ids": inspected_ids,
        "snapshots": [asdict(s) for s in snapshots],
    }

    print(json.dumps(report, indent=2, sort_keys=True))

    hard_fail = any(
        s.id == args.anime_id
        and (
            s.title in (None, "")
            or bool(s.payload_synonyms_missing)
            or bool(s.payload_genres_missing)
        )
        for s in snapshots
    )
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
