# ADR 0007: Centralized Anime Write Gateway

## Status

Accepted

## Context

Anime catalogue data is currently persisted through multiple paths:

- modern ingestion paths (`search`, `stream`, `season`, `genre`, `schedule`)
  pass through `IngestionPipeline` and `DatabaseManager.upsert_anime_batch`;
- hydration and title backfill still rely on `AnimeAPI.save`, which uses a
  legacy save procedure path;
- providers also perform side-writes during conversion for selected metadata.

This split creates technical debt and inconsistent behavior. The most visible
bug is that hydration/backfill can fail to persist metadata such as
`title_synonyms` when the legacy save path is not correctly wired in the
embedded runtime. Anime 2210 exposed this: providers returned alternative
titles, but the database was not updated from that path.

## Decision

Introduce a single application-layer gateway:
`application/services/anime_write_service.py` (`AnimeWriteService`).

`AnimeWriteService` becomes the only write entrypoint for anime row upsert plus
metadata persistence (`title_synonyms`, `genres`, etc.) via
`DatabaseManager.upsert_anime_batch`.

### Source coverage

All ingestion sources must persist through this gateway:

- `SEARCH`
- `STREAM`
- `SCHEDULE`
- `SEASON`
- `GENRE`
- `HYDRATION`
- `BACKFILL`
- `REPAIR` (scripts/ops that write anime records)

### Converters

Provider payload conversion helpers are consolidated so all paths share the
same canonical transforms between:

- `AnimeRecord`
- legacy `Anime`
- provider payload structures used by identity resolution.

### Migration phases

Phase A (required):

1. Wire coordinator sink to `AnimeWriteService.persist_records`.
2. Route hydration/backfill to `AnimeWriteService` after provider fetch with
   `_persist=False`.
3. Fix embedded runtime wiring so legacy save callers do not fail during
   transition.

Phase B (required):

4. Delegate `AnimeAPI.save` to `AnimeWriteService` so persistence behavior is
   unified.
5. Keep legacy procedure compatibility temporarily, but mark as deprecated.

Phase C (optional, feature-flagged):

6. Defer provider side-writes (`save_genres`, `save_broadcast`,
   `save_relations`) behind a flag so the centralized write pipeline owns
   metadata persistence end-to-end.

## Consequences

- Hydration/backfill persist through the same path as search/schedule writes.
- Metadata persistence is consistent across insertion paths.
- Testing can target one gateway and shared converter set, increasing confidence
  and reducing duplication.
- Legacy write code is retained only as a migration shim and can be removed in
  a later release once callers are fully migrated.
