# ADR 0007: Stability Refactor — Canonical Metadata Pipeline

## Status

Accepted (2026-05)

## Context

Metadata ingestion previously relied on multiple overlapping concurrency
paths (`AnimeAPI.wrapper` thread fan-out, coordinator executor, lazy
`ItemList` threads). Provider failures could cascade, application services
imported adapter types directly, and cross-provider ID mapping was
inconsistent.

## Decision

1. **Canonical path**: All multi-provider search and schedule warming flow
   through `APICoordinator` + `IngestionPipeline` + `DatabaseManager`
   persistence sink.
2. **Application bridges**: Legacy entity types are imported only via
   `application.bridges.legacy_entities`.
3. **Provider contract**: Every wrapper under `adapters.api` implements
   `adapters.api.provider_contract` (required: `searchAnime`, `anime`,
   `apiKey`).
4. **Provider health**: `ProviderHealthTracker` quarantines chronically
   failing providers (circuit-breaker semantics).
5. **MAL opt-in**: `MyAnimeListNet` loads automatically when OAuth
   credentials are configured; otherwise it is skipped with a log line.
6. **Stability gate**: `python scripts/stability_gate.py` is mandatory
   before merge during the refactor program.

## Consequences

* Emergency rollback remains available via `new_ingestion_pipeline=false`
  but emits telemetry and log warnings.
* Character/animeography persistence is implemented in `APIUtils.save_animeography`.
* `LegacyMetadataProviderAdapter` lives in `adapters/legacy/metadata_provider_adapter.py`
  to thin `runtime.py`.

## Extension rules

* New metadata providers: add a wrapper module + pass `validate_provider`.
* Do not add new `AnimeAPI.wrapper` fan-out for search/list ingestion.
* Wire providers only through `composition/root.py`.
