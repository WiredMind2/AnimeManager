"""
APICoordinator - the single entry point for multi-provider metadata search.

The coordinator owns the
:class:`~application.services.ingestion_pipeline.IngestionPipeline` worker
pool and a :class:`~shared.telemetry.TelemetryCollector` handle. It
normalizes raw provider responses into :class:`~shared.contracts.AnimeRecord`
DTOs, deduplicates them by id, and routes the resulting batch through a
single persistence sink bound to :class:`DatabaseManager`.

Feature flags:

* ``new_ingestion_pipeline`` (default ``True``) -- when False, falls back
  to the legacy ``self._api.searchAnime(...)`` thread-fan-out path.
* ``db_gateway_writes_only`` (default ``True``) -- when False, the sink
  is not attached and persistence is left to the caller (used by tests
  and as a safety knob during rollout).

See ``docs/developer/api_db_pipeline.rst`` for the full data-flow
diagram and operational runbook.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any, Dict, Iterable, List, Mapping, Optional

from shared.base_component import BaseComponent
from shared.contracts import (
    AnimeRecord,
    IngestionResult,
    IngestionStatus,
    ProviderName,
)
from application.services.ingestion_pipeline import (
    IngestionPipeline,
    ProviderSpec,
    _deduplicate,
    deduplicate_records,
)
from application.services.catalog_enrichment import expand_external_ids_with_mapping
from application.services.catalog_identity import (
    CatalogIdentityService,
    _normalize_external_ids,
)
from domain.policies.schedule_recency import filter_recent_schedule_records
from adapters.persistence.catalog_repository import CatalogIndexRepository
from application.services.anime_write_service import WriteSource
from shared.telemetry import get_telemetry
from adapters.persistence.models import Anime, AnimeList


class APICoordinator(BaseComponent):
    """Bounded-concurrency, gateway-only multi-provider search coordinator."""

    def __init__(self, *, max_workers: int = 4, provider_timeout_s: float = 45.0):
        super().__init__("APICoordinator")
        self._api = None
        self._database_manager = None
        self._feature_flags: Dict[str, bool] = {
            "new_ingestion_pipeline": True,
            "db_gateway_writes_only": True,
        }
        self._rate_limiter = RateLimiter()
        self._telemetry = get_telemetry()
        self._max_workers = max_workers
        self._provider_timeout = provider_timeout_s
        # Eagerly create the pipeline so callers don't have to drive a
        # lifecycle. The executor is owned by the pipeline.
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._pipeline: Optional[IngestionPipeline] = IngestionPipeline(
            max_workers=max_workers,
            provider_timeout_s=provider_timeout_s,
            executor=self._executor,
        )
        self._catalog_identity: Optional[CatalogIdentityService] = None
        self._write_service = None

    def close(self) -> None:
        """Release the pipeline executor; safe to call more than once."""
        pipeline = self._pipeline
        self._pipeline = None
        if pipeline is not None:
            pipeline.close()
        executor = self._executor
        self._executor = None
        if executor is not None:
            executor.shutdown(wait=True)

    def set_api(self, api) -> None:
        """Attach the multi-provider API facade (``adapters.api.AnimeAPI``)."""
        self._api = api

    def set_database_manager(self, database_manager) -> None:
        """Attach the database manager used for unified persistence."""
        self._database_manager = database_manager
        self._catalog_identity = None

    def set_catalog_identity(self, service: CatalogIdentityService) -> None:
        """Attach the catalogue identity service (optional; lazy-inited from DB)."""
        self._catalog_identity = service

    def set_write_service(self, write_service: Any) -> None:
        """Attach the centralized write gateway used by ingestion sinks."""
        self._write_service = write_service

    def configure(self, flags: Dict[str, bool]) -> None:
        """Update feature flags. Unknown keys are ignored by the pipeline."""
        self._feature_flags.update(flags or {})

    def search_anime(
        self,
        terms: str,
        limit: int = 50,
        force_search: bool = False,
    ) -> Optional[AnimeList]:
        """Search for anime across all loaded providers.

        Returns ``None`` for an empty query, when no API has been
        attached, or when every provider failed. Otherwise returns an
        ``AnimeList`` of the deduplicated results.
        """
        if not self._api:
            self.log("API_COORDINATOR", "[ERROR] - API not initialized")
            return None
        if not terms or len(terms.strip()) < 3:
            return None
        if not self._rate_limiter.allow_request():
            self.log("API_COORDINATOR", "Rate limit exceeded, skipping search")
            return None

        try:
            self.log("API_COORDINATOR", f"Searching '{terms}' with APIs")
            results = self._perform_api_search(terms, limit)
        except Exception as exc:
            self.log("API_COORDINATOR", f"Search failed: {exc}")
            self._telemetry.increment("coordinator.search_errors")
            return None

        if results:
            try:
                count = len(results)
            except TypeError:
                # Some result containers (e.g. ``AnimeList`` / ``ItemList``)
                # are lazy async iterables and intentionally do not expose
                # ``__len__``; log without a count rather than crashing.
                self.log("API_COORDINATOR", "Search returned results")
            else:
                self.log("API_COORDINATOR", f"Found {count} results")
            return results
        self.log("API_COORDINATOR", "No results found")
        return None

    def _perform_api_search(self, terms: str, limit: int) -> Optional[AnimeList]:
        """Run the configured search path."""
        if (
            self._feature_flags.get("new_ingestion_pipeline", True)
            and hasattr(self._api, "get_providers")
            and self._pipeline is not None
        ):
            return self._search_via_pipeline(terms, limit)
        # Legacy rollback path: hand back whatever the AnimeAPI facade
        # returns; the caller is responsible for persistence.
        return self._api.searchAnime(terms, limit=limit)

    def stream_search_anime(
        self,
        terms: str,
        limit: int = 50,
    ) -> Iterable[Any]:
        """Yield legacy-shaped Anime objects progressively per provider.

        Each batch corresponds to one provider finishing -- callers can
        push partial results to the UI as soon as they arrive instead
        of blocking on the slowest provider. The persistence sink is
        still invoked at the very end with the full deduplicated set
        so the local catalog gets warmed identically to the blocking
        ``search_anime`` path.
        """
        if not self._api:
            self.log("API_COORDINATOR", "[ERROR] - API not initialized")
            return
        if not terms or len(terms.strip()) < 3:
            return
        if not self._rate_limiter.allow_request():
            self.log("API_COORDINATOR", "Rate limit exceeded, skipping search")
            return
        if (
            not self._feature_flags.get("new_ingestion_pipeline", True)
            or not hasattr(self._api, "get_providers")
            or self._pipeline is None
        ):
            # Legacy path is not streamable -- fall back to the
            # single-batch search so callers can still consume the
            # generator uniformly.
            result = self._api.searchAnime(terms, limit=limit)
            if result:
                for item in result:
                    yield item
            return

        providers = [p for p in self._api.get_providers() if p is not None]
        if not providers:
            return
        specs = [self._spec_for(provider) for provider in providers]
        sink = (
            self._build_sink(source=WriteSource.STREAM)
            if self._feature_flags.get("db_gateway_writes_only", True)
            else None
        )
        self.log("API_COORDINATOR", f"Streaming '{terms}' across {len(specs)} providers")
        emitted = 0
        try:
            for provider_name, records in self._pipeline.stream(
                specs, terms, limit=limit, sink=sink
            ):
                for record in records:
                    yield self._record_to_anime(record)
                    emitted += 1
                self.log(
                    "API_COORDINATOR",
                    f"Streamed +{len(records)} from {provider_name} (total {emitted})",
                )
        except Exception as exc:  # noqa: BLE001 - never let streaming break the WS
            self.log("API_COORDINATOR", f"Stream failed mid-flight: {exc}")
            self._telemetry.increment("coordinator.search_errors")

    def fetch_latest(
        self,
        limit: int = 50,
        *,
        per_provider: bool = False,
        provider_timeout_s: Optional[float] = None,
    ) -> Optional[IngestionResult]:
        """Pull the latest anime data from every provider that exposes
        a ``schedule`` endpoint.

        Each provider's ``schedule(limit=...)`` call is routed through
        the same :class:`IngestionPipeline` used by interactive search,
        so partial failures, dedupe and the persistence sink behave
        identically. Used by the startup-jobs orchestrator to warm the
        local database with the current season's metadata.

        Returns the underlying :class:`IngestionResult`, or ``None`` if
        no API has been attached / no providers expose ``schedule``.
        """
        if not self._api:
            self.log("API_COORDINATOR", "[ERROR] - API not initialized")
            return None
        if self._pipeline is None:
            return None
        if not hasattr(self._api, "get_providers"):
            return None

        providers = [p for p in self._api.get_providers() if p is not None]
        schedule_providers = [
            provider for provider in providers if hasattr(provider, "schedule")
        ]
        specs = [
            self._schedule_spec_for(provider)
            for provider in schedule_providers
        ]
        if not specs:
            return None

        persist_sink = (
            self._build_sink(enrich=True, source=WriteSource.SCHEDULE)
            if self._feature_flags.get("db_gateway_writes_only", True)
            else None
        )
        timeout = (
            float(provider_timeout_s)
            if provider_timeout_s is not None
            else max(float(self._provider_timeout), 60.0)
        )
        pipeline = self._pipeline
        original_timeout = pipeline._provider_timeout
        window_days = self._read_schedule_recency_days()
        fetch_limit = max(int(limit) * 3, int(limit))
        self._set_schedule_light_mode(schedule_providers, True)
        try:
            pipeline._provider_timeout = timeout
            result: IngestionResult = pipeline.run(
                specs,
                "",
                limit=fetch_limit,
                sink=None,
                limit_per_provider=per_provider,
                parallel=True,
            )
            records = self._batch_assign_catalog_ids(result.records)
            records = deduplicate_records(records)
            pre_filter_count = len(records)
            records = filter_recent_schedule_records(
                records,
                window_days=window_days,
                limit=limit,
            )
            filtered_out = pre_filter_count - len(records)
            if filtered_out:
                self.log(
                    "API_COORDINATOR",
                    f"Schedule recency filter dropped {filtered_out} row(s); "
                    f"kept {len(records)} within {window_days} day(s)",
                )
            if not records and pre_filter_count:
                self.log(
                    "API_COORDINATOR",
                    f"Schedule recency filter removed all {pre_filter_count} "
                    f"candidate row(s) (window_days={window_days})",
                )
            persisted_count = 0
            if persist_sink is not None and records:
                persisted_count = persist_sink(records)
            result.records = records
            result.persisted_count = persisted_count
        finally:
            pipeline._provider_timeout = original_timeout
            self._set_schedule_light_mode(schedule_providers, False)
        self._telemetry.set_gauge(
            "coordinator.last_schedule_records", float(len(result.records))
        )
        self._telemetry.set_gauge(
            "coordinator.last_schedule_failed", float(result.failed_providers)
        )
        self._telemetry.set_gauge(
            "coordinator.last_schedule_persisted", float(result.persisted_count)
        )
        self.log(
            "API_COORDINATOR",
            f"Schedule fetch completion={result.status.value} "
            f"records={len(result.records)} persisted={result.persisted_count} "
            f"failed={result.failed_providers}/"
            f"{result.total_providers} elapsed_ms={result.elapsed_ms}",
        )
        return result

    def _schedule_spec_for(self, provider: Any) -> ProviderSpec:
        """Build a :class:`ProviderSpec` whose search callable invokes
        ``provider.schedule(limit=...)``.

        The :class:`IngestionPipeline` contract is ``(terms, limit) ->
        Iterable``, so the unused ``terms`` argument is accepted and
        discarded here.
        """
        provider_name = (
            getattr(provider, "__name__", None) or type(provider).__name__
        )

        def schedule_search(_terms: str, lim: int) -> Iterable[Any]:
            try:
                return provider.schedule(limit=lim)
            except TypeError:
                # Some legacy wrappers accept positional-only ``limit``.
                return provider.schedule(lim)

        def adapter(raw: Any) -> Optional[AnimeRecord]:
            return self._schedule_light_adapter(raw, provider_name=provider_name)

        return ProviderSpec(
            name=provider_name,
            search=schedule_search,
            adapter=adapter,
        )

    def browse_season(
        self,
        year: int,
        season: str,
        limit: int = 50,
    ) -> Optional[AnimeList]:
        """Fetch anime for a broadcast season across providers exposing ``season``."""
        if not self._api:
            self.log("API_COORDINATOR", "[ERROR] - API not initialized")
            return None
        if not self._rate_limiter.allow_request():
            self.log("API_COORDINATOR", "Rate limit exceeded, skipping season browse")
            return None
        if (
            self._feature_flags.get("new_ingestion_pipeline", True)
            and hasattr(self._api, "get_providers")
            and self._pipeline is not None
        ):
            return self._browse_season_via_pipeline(year, season, limit)
        season_fn = getattr(self._api, "season", None)
        if not callable(season_fn):
            return None
        try:
            results = season_fn(year, season, limit=limit)
        except TypeError:
            results = season_fn(year, season, limit)
        if not results:
            return None
        return results

    def stream_browse_season(
        self,
        year: int,
        season: str,
        limit: int = 50,
    ) -> Iterable[Any]:
        """Yield legacy-shaped anime objects for a broadcast season."""
        if not self._api:
            self.log("API_COORDINATOR", "[ERROR] - API not initialized")
            return
        if not self._rate_limiter.allow_request():
            self.log("API_COORDINATOR", "Rate limit exceeded, skipping season browse")
            return
        if (
            not self._feature_flags.get("new_ingestion_pipeline", True)
            or not hasattr(self._api, "get_providers")
            or self._pipeline is None
        ):
            result = self.browse_season(year, season, limit=limit)
            if result:
                for item in result:
                    yield item
            return

        providers = [p for p in self._api.get_providers() if p is not None]
        specs = [
            self._season_spec_for(provider, year, season)
            for provider in providers
            if hasattr(provider, "season")
        ]
        if not specs:
            return
        sink = (
            self._build_sink(source=WriteSource.SEASON)
            if self._feature_flags.get("db_gateway_writes_only", True)
            else None
        )
        self.log(
            "API_COORDINATOR",
            f"Streaming season {season} {year} across {len(specs)} providers",
        )
        emitted = 0
        try:
            for provider_name, records in self._pipeline.stream(
                specs,
                "",
                limit=limit,
                sink=sink,
            ):
                for record in records:
                    yield self._record_to_anime(record)
                    emitted += 1
                self.log(
                    "API_COORDINATOR",
                    f"Season stream +{len(records)} from {provider_name} (total {emitted})",
                )
        except Exception as exc:  # noqa: BLE001
            self.log("API_COORDINATOR", f"Season stream failed mid-flight: {exc}")
            self._telemetry.increment("coordinator.search_errors")

    def _browse_season_via_pipeline(
        self,
        year: int,
        season: str,
        limit: int,
    ) -> Optional[AnimeList]:
        providers = [p for p in self._api.get_providers() if p is not None]
        specs = [
            self._season_spec_for(provider, year, season)
            for provider in providers
            if hasattr(provider, "season")
        ]
        if not specs:
            return None
        sink = (
            self._build_sink(source=WriteSource.SEASON)
            if self._feature_flags.get("db_gateway_writes_only", True)
            else None
        )
        result: IngestionResult = self._pipeline.run(
            specs,
            "",
            limit=limit,
            sink=sink,
            limit_per_provider=True,
        )
        self._telemetry.set_gauge(
            "coordinator.last_season_records", float(len(result.records))
        )
        self._telemetry.set_gauge(
            "coordinator.last_season_failed", float(result.failed_providers)
        )
        self.log(
            "API_COORDINATOR",
            f"Season browse completion={result.status.value} "
            f"records={len(result.records)} failed={result.failed_providers}/"
            f"{result.total_providers} elapsed_ms={result.elapsed_ms}",
        )
        if result.status == IngestionStatus.FAILED or not result.records:
            return None
        return AnimeList([self._record_to_anime(r) for r in result.records])

    def _season_spec_for(
        self,
        provider: Any,
        year: int,
        season: str,
    ) -> ProviderSpec:
        provider_name = (
            getattr(provider, "__name__", None) or type(provider).__name__
        )

        def season_search(_terms: str, lim: int) -> Iterable[Any]:
            try:
                return provider.season(year, season, limit=lim)
            except TypeError:
                return provider.season(year, season, lim)

        def adapter(raw: Any) -> Optional[AnimeRecord]:
            return self._legacy_adapter(raw, provider_name=provider_name)

        return ProviderSpec(
            name=provider_name,
            search=season_search,
            adapter=adapter,
        )

    def browse_genre(
        self,
        genre: str,
        limit: int = 50,
    ) -> Optional[AnimeList]:
        """Fetch anime for a genre across providers exposing ``genre``."""
        if not self._api:
            self.log("API_COORDINATOR", "[ERROR] - API not initialized")
            return None
        if not self._rate_limiter.allow_request():
            self.log("API_COORDINATOR", "Rate limit exceeded, skipping genre browse")
            return None
        if (
            self._feature_flags.get("new_ingestion_pipeline", True)
            and hasattr(self._api, "get_providers")
            and self._pipeline is not None
        ):
            return self._browse_genre_via_pipeline(genre, limit)
        genre_fn = getattr(self._api, "genre", None)
        if not callable(genre_fn):
            return None
        try:
            results = genre_fn(genre, limit=limit)
        except TypeError:
            results = genre_fn(genre, limit)
        if not results:
            return None
        return results

    def stream_browse_genre(
        self,
        genre: str,
        limit: int = 50,
    ) -> Iterable[Any]:
        """Yield legacy-shaped anime objects for a genre browse."""
        if not self._api:
            self.log("API_COORDINATOR", "[ERROR] - API not initialized")
            return
        if not self._rate_limiter.allow_request():
            self.log("API_COORDINATOR", "Rate limit exceeded, skipping genre browse")
            return
        if (
            not self._feature_flags.get("new_ingestion_pipeline", True)
            or not hasattr(self._api, "get_providers")
            or self._pipeline is None
        ):
            result = self.browse_genre(genre, limit=limit)
            if result:
                for item in result:
                    yield item
            return

        providers = [p for p in self._api.get_providers() if p is not None]
        specs = [
            self._genre_spec_for(provider, genre)
            for provider in providers
            if hasattr(provider, "genre")
        ]
        if not specs:
            return
        sink = (
            self._build_sink(source=WriteSource.GENRE)
            if self._feature_flags.get("db_gateway_writes_only", True)
            else None
        )
        self.log(
            "API_COORDINATOR",
            f"Streaming genre {genre} across {len(specs)} providers",
        )
        emitted = 0
        try:
            for provider_name, records in self._pipeline.stream(
                specs,
                "",
                limit=limit,
                sink=sink,
            ):
                for record in records:
                    yield self._record_to_anime(record)
                    emitted += 1
                self.log(
                    "API_COORDINATOR",
                    f"Genre stream +{len(records)} from {provider_name} (total {emitted})",
                )
        except Exception as exc:  # noqa: BLE001
            self.log("API_COORDINATOR", f"Genre stream failed mid-flight: {exc}")
            self._telemetry.increment("coordinator.search_errors")

    def _browse_genre_via_pipeline(
        self,
        genre: str,
        limit: int,
    ) -> Optional[AnimeList]:
        providers = [p for p in self._api.get_providers() if p is not None]
        specs = [
            self._genre_spec_for(provider, genre)
            for provider in providers
            if hasattr(provider, "genre")
        ]
        if not specs:
            return None
        sink = (
            self._build_sink(source=WriteSource.GENRE)
            if self._feature_flags.get("db_gateway_writes_only", True)
            else None
        )
        result: IngestionResult = self._pipeline.run(
            specs,
            "",
            limit=limit,
            sink=sink,
            limit_per_provider=True,
        )
        self._telemetry.set_gauge(
            "coordinator.last_genre_records", float(len(result.records))
        )
        self._telemetry.set_gauge(
            "coordinator.last_genre_failed", float(result.failed_providers)
        )
        self.log(
            "API_COORDINATOR",
            f"Genre browse completion={result.status.value} "
            f"records={len(result.records)} failed={result.failed_providers}/"
            f"{result.total_providers} elapsed_ms={result.elapsed_ms}",
        )
        if result.status == IngestionStatus.FAILED or not result.records:
            return None
        return AnimeList([self._record_to_anime(r) for r in result.records])

    def _genre_spec_for(
        self,
        provider: Any,
        genre: str,
    ) -> ProviderSpec:
        provider_name = (
            getattr(provider, "__name__", None) or type(provider).__name__
        )

        def genre_search(_terms: str, lim: int) -> Iterable[Any]:
            try:
                return provider.genre(genre, limit=lim)
            except TypeError:
                return provider.genre(genre, lim)

        def adapter(raw: Any) -> Optional[AnimeRecord]:
            return self._legacy_adapter(raw, provider_name=provider_name)

        return ProviderSpec(
            name=provider_name,
            search=genre_search,
            adapter=adapter,
        )

    def _search_via_pipeline(self, terms: str, limit: int) -> Optional[AnimeList]:
        """Run providers through the canonical ingestion pipeline."""
        providers = list(self._api.get_providers())
        if not providers:
            return None
        specs = [self._spec_for(provider) for provider in providers if provider is not None]
        sink = (
            self._build_sink(source=WriteSource.SEARCH)
            if self._feature_flags.get("db_gateway_writes_only", True)
            else None
        )
        result: IngestionResult = self._pipeline.run(
            specs,
            terms,
            limit=limit,
            sink=sink,
        )
        self._telemetry.set_gauge("coordinator.last_search_records", float(len(result.records)))
        self._telemetry.set_gauge("coordinator.last_search_failed", float(result.failed_providers))
        self.log(
            "API_COORDINATOR",
            f"Search completion={result.status.value} "
            f"records={len(result.records)} failed={result.failed_providers}/"
            f"{result.total_providers} elapsed_ms={result.elapsed_ms}",
        )
        if result.status == IngestionStatus.FAILED or not result.records:
            return None
        return AnimeList([self._record_to_anime(r) for r in result.records])

    def _spec_for(self, provider: Any) -> ProviderSpec:
        """Build a `ProviderSpec` around a legacy provider wrapper."""
        provider_name = getattr(provider, "__name__", None) or type(provider).__name__

        def search(terms: str, limit: int) -> Iterable[Any]:
            if not hasattr(provider, "searchAnime"):
                return ()
            return provider.searchAnime(terms, limit=limit)

        def adapter(raw: Any) -> Optional[AnimeRecord]:
            return self._legacy_adapter(raw, provider_name=provider_name)

        return ProviderSpec(name=provider_name, search=search, adapter=adapter)

    def _ensure_catalog_identity(self) -> Optional[CatalogIdentityService]:
        if self._catalog_identity is not None:
            return self._catalog_identity
        db_manager = self._database_manager
        if db_manager is None:
            return None
        db = db_manager.get_database()
        if db is None:
            return None
        self._catalog_identity = CatalogIdentityService.from_database(
            db,
            log_fn=lambda msg: self.log("API_COORDINATOR", msg),
        )
        return self._catalog_identity

    @staticmethod
    def _set_schedule_light_mode(providers: Iterable[Any], enabled: bool) -> None:
        for provider in providers:
            if hasattr(provider, "schedule_light"):
                provider.schedule_light = enabled

    def _read_schedule_recency_days(self) -> int:
        """Return configured schedule recency window from attached API settings."""
        api = self._api
        settings = getattr(api, "settings", None) if api is not None else None
        if not isinstance(settings, dict):
            getters = getattr(api, "_getters", None) if api is not None else None
            settings = getattr(getters, "settings", None)
        anime_cfg = settings.get("anime") if isinstance(settings, dict) else None
        if not isinstance(anime_cfg, dict):
            return 90
        try:
            days = int(anime_cfg.get("scheduleRecencyDays", 90))
        except (TypeError, ValueError):
            return 90
        return max(1, days)

    def _schedule_light_adapter(
        self,
        raw: Any,
        *,
        provider_name: str = "",
    ) -> Optional[AnimeRecord]:
        """Project schedule rows without per-row DB lookups or side writes."""
        return self._project_legacy_anime(raw, provider_name=provider_name)

    def _batch_assign_catalog_ids(
        self, records: List[AnimeRecord]
    ) -> List[AnimeRecord]:
        if not records:
            return []

        identity = self._ensure_catalog_identity()
        if identity is None:
            return records

        mapping_port = None
        db_manager = self._database_manager
        if db_manager is not None:
            mapping_port = getattr(db_manager, "_mapping_port", None)

        pending_indices: List[int] = []
        payloads: List[Dict[str, int]] = []
        mapping_cache: Dict[tuple[str, int], Dict[str, int]] = {}
        for idx, record in enumerate(records):
            normalized = _normalize_external_ids(record.external_ids or {})
            if normalized and record.id < 0:
                normalized = expand_external_ids_with_mapping(
                    normalized,
                    mapping_port,
                    cache=mapping_cache,
                )
                pending_indices.append(idx)
                payloads.append(normalized)

        if not payloads:
            return records

        try:
            resolved = identity.resolve_external_ids_batch(payloads)
        except Exception as exc:
            self.log(
                "API_COORDINATOR",
                f"Batch catalog resolve failed: {type(exc).__name__}: {exc}",
            )
            self._telemetry.increment("coordinator.batch_resolve_errors")
            return records

        updated = list(records)
        for idx, entry in zip(pending_indices, resolved):
            updated[idx] = replace(
                updated[idx],
                id=entry.catalog_id,
                external_ids=dict(entry.external_ids),
            )
        return updated

    def _legacy_adapter(
        self,
        raw: Any,
        *,
        provider_name: str = "",
    ) -> Optional[AnimeRecord]:
        """Project a legacy `Anime`-like object into the canonical record."""
        record = self._project_legacy_anime(raw, provider_name=provider_name)
        if record is None:
            return None

        identity = self._ensure_catalog_identity()
        db_manager = self._database_manager
        if identity is None or db_manager is None:
            return record

        db = db_manager.get_database()
        if db is None:
            return record

        pinned_ctx = getattr(db, "pinned_pool_connection", None)
        use_pool = bool(getattr(db, "USE_CONNECTION_POOL", False))

        def _resolve_identity() -> Optional[AnimeRecord]:
            external_ids = CatalogIndexRepository(db).get_external_ids(record.id)
            if not external_ids:
                return record

            resolved = identity.resolve_external_ids(
                external_ids,
                source_provider=record.source_provider.value,
            )
            if (
                resolved.catalog_id == record.id
                and resolved.external_ids == record.external_ids
            ):
                return record

            return AnimeRecord(
                id=resolved.catalog_id,
                title=record.title,
                title_synonyms=record.title_synonyms,
                synopsis=record.synopsis,
                episodes=record.episodes,
                duration=record.duration,
                status=record.status,
                rating=record.rating,
                date_from=record.date_from,
                date_to=record.date_to,
                picture=record.picture,
                trailer=record.trailer,
                broadcast=record.broadcast,
                genres=record.genres,
                external_ids=dict(resolved.external_ids),
                source_provider=record.source_provider,
            )

        if pinned_ctx is not None and use_pool:
            with pinned_ctx():
                return _resolve_identity()
        return _resolve_identity()

    @staticmethod
    def _project_legacy_anime(
        raw: Any,
        *,
        provider_name: str = "",
    ) -> Optional[AnimeRecord]:
        if raw is None:
            return None
        rid = getattr(raw, "id", None)
        pending_external = getattr(raw, "_schedule_external_ids", None)
        normalized_external = (
            _normalize_external_ids(pending_external) if pending_external else {}
        )
        if rid is None and normalized_external:
            rid = _provisional_id_from_external_ids(normalized_external)
        if rid is None:
            return None
        try:
            rid = int(rid)
        except (TypeError, ValueError):
            return None
        title = getattr(raw, "title", None) or ""
        source = _provider_name_from_spec(provider_name)
        genres = getattr(raw, "genres", None) or ()
        if isinstance(genres, (list, tuple)):
            genres = tuple(str(g) for g in genres if g)
        else:
            genres = ()
        synonyms = getattr(raw, "title_synonyms", None) or ()
        if isinstance(synonyms, (list, tuple)):
            synonyms = tuple(str(s) for s in synonyms if s)
        elif synonyms:
            synonyms = (str(synonyms),)
        else:
            synonyms = ()
        return AnimeRecord(
            id=rid,
            title=str(title),
            title_synonyms=synonyms,
            synopsis=getattr(raw, "synopsis", None),
            episodes=_safe_int(getattr(raw, "episodes", None)),
            duration=_safe_int(getattr(raw, "duration", None)),
            status=_safe_str(getattr(raw, "status", None)),
            rating=_safe_str(getattr(raw, "rating", None)),
            date_from=_safe_int(getattr(raw, "date_from", None)),
            date_to=_safe_int(getattr(raw, "date_to", None)),
            picture=_safe_str(getattr(raw, "picture", None)),
            trailer=_safe_str(getattr(raw, "trailer", None)),
            broadcast=_safe_str(getattr(raw, "broadcast", None)),
            genres=genres,
            external_ids=normalized_external or {},
            source_provider=source,
        )

    @staticmethod
    def _record_to_anime(record: AnimeRecord) -> Anime:
        """Reconstruct a legacy `Anime` object from a normalized record."""
        anime = Anime()
        for key in (
            "id",
            "title",
            "synopsis",
            "episodes",
            "duration",
            "status",
            "rating",
            "date_from",
            "date_to",
            "picture",
            "trailer",
            "broadcast",
        ):
            value = getattr(record, key)
            if value is not None:
                try:
                    setattr(anime, key, value)
                except Exception:
                    # Some attributes are managed by the legacy class; ignore.
                    pass
        for meta_key in ("title_synonyms", "genres"):
            meta_value = getattr(record, meta_key, None)
            if meta_value:
                try:
                    setattr(anime, meta_key, list(meta_value))
                except Exception:
                    pass
        return anime

    def _build_sink(
        self,
        *,
        enrich: bool = True,
        source: WriteSource = WriteSource.SEARCH,
    ):
        """Return a persistence sink bound to the configured DatabaseManager."""
        db_manager = self._database_manager
        if db_manager is None:
            return None

        def sink(records: List[AnimeRecord]) -> int:
            try:
                write_service = self._write_service
                if write_service is not None:
                    result = write_service.persist_records(records, source=source)
                    persisted = int(result.persisted)
                    if result.errors:
                        self._telemetry.increment("coordinator.persist_errors")
                else:
                    animes = [self._record_to_anime(r) for r in records]
                    persisted = db_manager.upsert_anime_batch(animes)
                if enrich and persisted:
                    ids = [r.id for r in records]
                    threading.Thread(
                        target=lambda: db_manager.enrich_catalog_identities_for_ids(
                            ids
                        ),
                        name="catalog-enrich-search",
                        daemon=True,
                    ).start()
                return persisted
            except Exception as exc:
                self.log("API_COORDINATOR", f"Failed persisting search results: {exc}")
                self._telemetry.increment("coordinator.persist_errors")
                return 0

        return sink


def _provisional_id_from_external_ids(external_ids: Mapping[str, int]) -> int:
    fingerprint = tuple(sorted(external_ids.items()))
    value = abs(hash(fingerprint)) & 0x7FFFFFFF
    return -value if value else -1


def _provider_name_from_spec(provider_name: str) -> ProviderName:
    lowered = (provider_name or "").lower()
    if "jikan" in lowered or "mal" in lowered:
        return ProviderName.JIKAN
    if "anilist" in lowered:
        return ProviderName.ANILIST
    if "kitsu" in lowered:
        return ProviderName.KITSU
    return ProviderName.UNKNOWN


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class RateLimiter:
    """Simple sliding-window rate limiter used by `APICoordinator`."""

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests: List[float] = []
        self.lock = threading.Lock()

    def allow_request(self) -> bool:
        with self.lock:
            now = time.time()
            self.requests = [req for req in self.requests if now - req < 60]
            if len(self.requests) < self.requests_per_minute:
                self.requests.append(now)
                return True
            return False
