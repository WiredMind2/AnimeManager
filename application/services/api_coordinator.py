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
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from shared.base_component import BaseComponent
from shared.contracts import (
    AnimeRecord,
    IngestionResult,
    IngestionStatus,
    ProviderAnimePayload,
    ProviderName,
)
from adapters.api.provider_payload import (
    anime_record_to_legacy_anime,
    anime_to_provider_payload,
    payload_to_anime_record,
)
from application.services.ingestion_pipeline import (
    IngestionPipeline,
    ProviderSpec,
    deduplicate_records,
)
from application.services.catalog_enrichment import expand_external_ids_with_mapping
from application.services.catalog_merge import CatalogMergeService
from application.services.catalog_identity import (
    CatalogIdentityService,
    _normalize_external_ids,
)
from domain.policies.schedule_recency import filter_recent_schedule_records
from adapters.persistence.catalog_repository import (
    CatalogIndexRepository,
    CatalogMergeRepository,
    _batched_writes,
)
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
        # Dedicated pipeline for background warm-up jobs (fetch_latest) so
        # long schedule fetches can never starve interactive browse/search,
        # which shares the main executor above. Created lazily.
        self._background_pipeline: Optional[IngestionPipeline] = None
        self._catalog_identity: Optional[CatalogIdentityService] = None
        self._write_service = None

    def close(self) -> None:
        """Release the pipeline executor; safe to call more than once."""
        pipeline = self._pipeline
        self._pipeline = None
        if pipeline is not None:
            pipeline.close()
        background = self._background_pipeline
        self._background_pipeline = None
        if background is not None:
            background.close()
        executor = self._executor
        self._executor = None
        if executor is not None:
            executor.shutdown(wait=True)

    def _get_background_pipeline(
        self, provider_timeout_s: float
    ) -> IngestionPipeline:
        """Return the lazily-created pipeline reserved for warm-up jobs.

        Only ``fetch_latest`` uses this pipeline, so adjusting its timeout
        per call is safe (no interactive requests race on it).
        """
        pipeline = self._background_pipeline
        if pipeline is None:
            pipeline = IngestionPipeline(
                max_workers=2,
                provider_timeout_s=provider_timeout_s,
            )
            self._background_pipeline = pipeline
        else:
            pipeline._provider_timeout = provider_timeout_s
        return pipeline

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

        providers = self._search_providers()
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
        self._set_list_light_mode(providers, True)
        try:
            for provider_name, payloads in self._pipeline.stream(
                specs, terms, limit=limit, sink=sink
            ):
                finalized = self._finalize_catalog_records(list(payloads))
                for record in finalized:
                    yield self._record_to_anime(record)
                    emitted += 1
                self.log(
                    "API_COORDINATOR",
                    f"Streamed +{len(finalized)} from {provider_name} (total {emitted})",
                )
        except Exception as exc:  # noqa: BLE001 - never let streaming break the WS
            self.log("API_COORDINATOR", f"Stream failed mid-flight: {exc}")
            self._telemetry.increment("coordinator.search_errors")
        finally:
            self._set_list_light_mode(providers, False)

    def fetch_latest(
        self,
        limit: int = 50,
        *,
        per_provider: bool = False,
        provider_timeout_s: Optional[float] = None,
    ) -> Optional[IngestionResult]:
        """Pull the latest anime data from every provider that exposes
        a ``schedule`` endpoint.

        Each provider's ``schedule(limit=...)`` call is routed through a
        dedicated background :class:`IngestionPipeline` (own executor) so
        this long-running warm-up job never starves interactive
        browse/search requests, while partial failures, dedupe and the
        persistence sink behave identically. Used by the startup-jobs
        orchestrator to warm the local database with the current
        season's metadata.

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

        persist_enabled = self._feature_flags.get("db_gateway_writes_only", True)
        timeout = (
            float(provider_timeout_s)
            if provider_timeout_s is not None
            else max(float(self._provider_timeout), 60.0)
        )
        pipeline = self._get_background_pipeline(timeout)
        window_days = self._read_schedule_recency_days()
        fetch_limit = max(int(limit) * 3, int(limit))
        self._set_list_light_mode(schedule_providers, True)
        try:
            result: IngestionResult = pipeline.run(
                specs,
                "",
                limit=fetch_limit,
                sink=None,
                limit_per_provider=per_provider,
                parallel=True,
            )
            records = self._finalize_catalog_records(list(result.payloads))
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
            records = [r for r in records if int(r.id) > 0]
            persisted_count = 0
            if persist_enabled and records:
                persisted_count = self._persist_catalog_records(
                    records,
                    enrich=True,
                    source=WriteSource.SCHEDULE,
                )
            result.records = records
            result.persisted_count = persisted_count
        finally:
            self._set_list_light_mode(schedule_providers, False)
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

        def adapter(raw: Any) -> Optional[ProviderAnimePayload]:
            return self.project_provider_raw(raw, provider_name=provider_name)

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

        providers = [
            provider
            for provider in self._api.get_providers()
            if provider is not None and hasattr(provider, "season")
        ]
        specs = [self._season_spec_for(provider, year, season) for provider in providers]
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
        self._set_list_light_mode(providers, True)
        try:
            for provider_name, payloads in self._pipeline.stream(
                specs,
                "",
                limit=limit,
                sink=sink,
            ):
                finalized = self._finalize_catalog_records(list(payloads))
                for record in finalized:
                    yield self._record_to_anime(record)
                    emitted += 1
                self.log(
                    "API_COORDINATOR",
                    f"Season stream +{len(finalized)} from {provider_name} (total {emitted})",
                )
        except Exception as exc:  # noqa: BLE001
            self.log("API_COORDINATOR", f"Season stream failed mid-flight: {exc}")
            self._telemetry.increment("coordinator.search_errors")
        finally:
            self._set_list_light_mode(providers, False)

    def _browse_season_via_pipeline(
        self,
        year: int,
        season: str,
        limit: int,
    ) -> Optional[AnimeList]:
        providers = [
            provider
            for provider in self._api.get_providers()
            if provider is not None and hasattr(provider, "season")
        ]
        specs = [self._season_spec_for(provider, year, season) for provider in providers]
        if not specs:
            return None
        sink = (
            self._build_sink(source=WriteSource.SEASON)
            if self._feature_flags.get("db_gateway_writes_only", True)
            else None
        )
        self._set_list_light_mode(providers, True)
        try:
            result: IngestionResult = self._pipeline.run(
                specs,
                "",
                limit=limit,
                sink=sink,
                limit_per_provider=True,
            )
        finally:
            self._set_list_light_mode(providers, False)
        self._telemetry.set_gauge(
            "coordinator.last_season_records", float(len(result.payloads))
        )
        self._telemetry.set_gauge(
            "coordinator.last_season_failed", float(result.failed_providers)
        )
        self.log(
            "API_COORDINATOR",
            f"Season browse completion={result.status.value} "
            f"payloads={len(result.payloads)} failed={result.failed_providers}/"
            f"{result.total_providers} elapsed_ms={result.elapsed_ms}",
        )
        if result.status == IngestionStatus.FAILED or not result.payloads:
            return None
        records = self._finalize_catalog_records(list(result.payloads))
        if not records:
            return None
        return AnimeList([self._record_to_anime(r) for r in records])

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

        def adapter(raw: Any) -> Optional[ProviderAnimePayload]:
            return self.project_provider_raw(raw, provider_name=provider_name)

        return ProviderSpec(
            name=provider_name,
            search=season_search,
            adapter=adapter,
        )

    def browse_genre(
        self,
        genre,
        limit: int = 50,
    ) -> Optional[AnimeList]:
        """Fetch anime for genre(s) across providers exposing ``genre``."""
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
        genre,
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

        providers = [
            provider
            for provider in self._api.get_providers()
            if provider is not None and hasattr(provider, "genre")
        ]
        specs = [self._genre_spec_for(provider, genre) for provider in providers]
        if not specs:
            return
        sink = (
            self._build_sink(source=WriteSource.GENRE)
            if self._feature_flags.get("db_gateway_writes_only", True)
            else None
        )
        label = genre if isinstance(genre, str) else ",".join(str(g) for g in genre)
        self.log(
            "API_COORDINATOR",
            f"Streaming genre {label} across {len(specs)} providers",
        )
        emitted = 0
        self._set_list_light_mode(providers, True)
        try:
            for provider_name, payloads in self._pipeline.stream(
                specs,
                "",
                limit=limit,
                sink=sink,
            ):
                finalized = self._finalize_catalog_records(list(payloads))
                for record in finalized:
                    yield self._record_to_anime(record)
                    emitted += 1
                self.log(
                    "API_COORDINATOR",
                    f"Genre stream +{len(finalized)} from {provider_name} (total {emitted})",
                )
        except Exception as exc:  # noqa: BLE001
            self.log("API_COORDINATOR", f"Genre stream failed mid-flight: {exc}")
            self._telemetry.increment("coordinator.search_errors")
        finally:
            self._set_list_light_mode(providers, False)

    def _browse_genre_via_pipeline(
        self,
        genre,
        limit: int,
    ) -> Optional[AnimeList]:
        providers = [
            provider
            for provider in self._api.get_providers()
            if provider is not None and hasattr(provider, "genre")
        ]
        specs = [self._genre_spec_for(provider, genre) for provider in providers]
        if not specs:
            return None
        sink = (
            self._build_sink(source=WriteSource.GENRE)
            if self._feature_flags.get("db_gateway_writes_only", True)
            else None
        )
        self._set_list_light_mode(providers, True)
        try:
            result: IngestionResult = self._pipeline.run(
                specs,
                "",
                limit=limit,
                sink=sink,
                limit_per_provider=True,
            )
        finally:
            self._set_list_light_mode(providers, False)
        self._telemetry.set_gauge(
            "coordinator.last_genre_records", float(len(result.payloads))
        )
        self._telemetry.set_gauge(
            "coordinator.last_genre_failed", float(result.failed_providers)
        )
        self.log(
            "API_COORDINATOR",
            f"Genre browse completion={result.status.value} "
            f"payloads={len(result.payloads)} failed={result.failed_providers}/"
            f"{result.total_providers} elapsed_ms={result.elapsed_ms}",
        )
        if result.status == IngestionStatus.FAILED or not result.payloads:
            return None
        records = self._finalize_catalog_records(list(result.payloads))
        if not records:
            return None
        return AnimeList([self._record_to_anime(r) for r in records])

    def _genre_spec_for(
        self,
        provider: Any,
        genre,
    ) -> ProviderSpec:
        provider_name = (
            getattr(provider, "__name__", None) or type(provider).__name__
        )

        def genre_search(_terms: str, lim: int) -> Iterable[Any]:
            try:
                return provider.genre(genre, limit=lim)
            except TypeError:
                return provider.genre(genre, lim)

        def adapter(raw: Any) -> Optional[ProviderAnimePayload]:
            return self.project_provider_raw(raw, provider_name=provider_name)

        return ProviderSpec(
            name=provider_name,
            search=genre_search,
            adapter=adapter,
        )

    def browse_top(
        self,
        category: str,
        limit: int = 50,
    ) -> Optional[AnimeList]:
        """Fetch top anime for a popularity category across providers."""
        if not self._api:
            self.log("API_COORDINATOR", "[ERROR] - API not initialized")
            return None
        if not self._rate_limiter.allow_request():
            self.log("API_COORDINATOR", "Rate limit exceeded, skipping top browse")
            return None
        if (
            self._feature_flags.get("new_ingestion_pipeline", True)
            and hasattr(self._api, "get_providers")
            and self._pipeline is not None
        ):
            return self._browse_top_via_pipeline(category, limit)
        top_fn = getattr(self._api, "top", None)
        if not callable(top_fn):
            return None
        try:
            results = top_fn(category, limit=limit)
        except TypeError:
            results = top_fn(category, limit)
        if not results:
            return None
        return results

    def stream_browse_top(
        self,
        category: str,
        limit: int = 50,
    ) -> Iterable[Any]:
        """Yield legacy-shaped anime objects for a top browse."""
        if not self._api:
            self.log("API_COORDINATOR", "[ERROR] - API not initialized")
            return
        if not self._rate_limiter.allow_request():
            self.log("API_COORDINATOR", "Rate limit exceeded, skipping top browse")
            return
        if (
            not self._feature_flags.get("new_ingestion_pipeline", True)
            or not hasattr(self._api, "get_providers")
            or self._pipeline is None
        ):
            result = self.browse_top(category, limit=limit)
            if result:
                for item in result:
                    yield item
            return

        providers = [
            provider
            for provider in self._api.get_providers()
            if provider is not None and hasattr(provider, "top")
        ]
        specs = [self._top_spec_for(provider, category) for provider in providers]
        if not specs:
            return
        sink = (
            self._build_sink(source=WriteSource.TOP)
            if self._feature_flags.get("db_gateway_writes_only", True)
            else None
        )
        self.log(
            "API_COORDINATOR",
            f"Streaming top {category} across {len(specs)} providers",
        )
        emitted = 0
        self._set_list_light_mode(providers, True)
        try:
            for provider_name, payloads in self._pipeline.stream(
                specs,
                "",
                limit=limit,
                sink=sink,
            ):
                finalized = self._finalize_catalog_records(list(payloads))
                for record in finalized:
                    yield self._record_to_anime(record)
                    emitted += 1
                self.log(
                    "API_COORDINATOR",
                    f"Top stream +{len(finalized)} from {provider_name} (total {emitted})",
                )
        except Exception as exc:  # noqa: BLE001
            self.log("API_COORDINATOR", f"Top stream failed mid-flight: {exc}")
            self._telemetry.increment("coordinator.search_errors")
        finally:
            self._set_list_light_mode(providers, False)

    def _browse_top_via_pipeline(
        self,
        category: str,
        limit: int,
    ) -> Optional[AnimeList]:
        providers = [
            provider
            for provider in self._api.get_providers()
            if provider is not None and hasattr(provider, "top")
        ]
        specs = [self._top_spec_for(provider, category) for provider in providers]
        if not specs:
            return None
        sink = (
            self._build_sink(source=WriteSource.TOP)
            if self._feature_flags.get("db_gateway_writes_only", True)
            else None
        )
        self._set_list_light_mode(providers, True)
        try:
            result: IngestionResult = self._pipeline.run(
                specs,
                "",
                limit=limit,
                sink=sink,
                limit_per_provider=True,
            )
        finally:
            self._set_list_light_mode(providers, False)
        self._telemetry.set_gauge(
            "coordinator.last_top_records", float(len(result.payloads))
        )
        self._telemetry.set_gauge(
            "coordinator.last_top_failed", float(result.failed_providers)
        )
        self.log(
            "API_COORDINATOR",
            f"Top browse completion={result.status.value} "
            f"payloads={len(result.payloads)} failed={result.failed_providers}/"
            f"{result.total_providers} elapsed_ms={result.elapsed_ms}",
        )
        if result.status == IngestionStatus.FAILED or not result.payloads:
            return None
        records = self._finalize_catalog_records(list(result.payloads))
        if not records:
            return None
        return AnimeList([self._record_to_anime(r) for r in records])

    def _top_spec_for(
        self,
        provider: Any,
        category: str,
    ) -> ProviderSpec:
        provider_name = (
            getattr(provider, "__name__", None) or type(provider).__name__
        )

        def top_search(_terms: str, lim: int) -> Iterable[Any]:
            try:
                return provider.top(category, limit=lim)
            except TypeError:
                return provider.top(category, lim)

        def adapter(raw: Any) -> Optional[ProviderAnimePayload]:
            return self.project_provider_raw(raw, provider_name=provider_name)

        return ProviderSpec(
            name=provider_name,
            search=top_search,
            adapter=adapter,
        )

    def _search_providers(self) -> List[Any]:
        """Providers that join parallel search fan-out.

        Wrappers may set ``parallel_search = False`` (AniDB) to remain on
        the enrichment/detail path only — titles-only hits lack cross-IDs
        and would otherwise create orphan catalog rows.
        """
        out: List[Any] = []
        for provider in self._api.get_providers():
            if provider is None:
                continue
            if not getattr(provider, "parallel_search", True):
                continue
            out.append(provider)
        return out

    def _search_via_pipeline(self, terms: str, limit: int) -> Optional[AnimeList]:
        """Run providers through the canonical ingestion pipeline."""
        providers = self._search_providers()
        if not providers:
            return None
        specs = [self._spec_for(provider) for provider in providers if provider is not None]
        sink = (
            self._build_sink(source=WriteSource.SEARCH)
            if self._feature_flags.get("db_gateway_writes_only", True)
            else None
        )
        self._set_list_light_mode(providers, True)
        try:
            result: IngestionResult = self._pipeline.run(
                specs,
                terms,
                limit=limit,
                sink=sink,
            )
        finally:
            self._set_list_light_mode(providers, False)
        self._telemetry.set_gauge(
            "coordinator.last_search_records", float(len(result.payloads))
        )
        self._telemetry.set_gauge(
            "coordinator.last_search_failed", float(result.failed_providers)
        )
        self.log(
            "API_COORDINATOR",
            f"Search completion={result.status.value} "
            f"payloads={len(result.payloads)} failed={result.failed_providers}/"
            f"{result.total_providers} elapsed_ms={result.elapsed_ms}",
        )
        if result.status == IngestionStatus.FAILED or not result.payloads:
            return None
        records = self._finalize_catalog_records(list(result.payloads))
        if not records:
            return None
        return AnimeList([self._record_to_anime(r) for r in records])

    def _spec_for(self, provider: Any) -> ProviderSpec:
        """Build a `ProviderSpec` around a legacy provider wrapper."""
        provider_name = getattr(provider, "__name__", None) or type(provider).__name__

        def search(terms: str, limit: int) -> Iterable[Any]:
            if not hasattr(provider, "searchAnime"):
                return ()
            return provider.searchAnime(terms, limit=limit)

        def adapter(raw: Any) -> Optional[ProviderAnimePayload]:
            return self.project_provider_raw(raw, provider_name=provider_name)

        return ProviderSpec(name=provider_name, search=search, adapter=adapter)

    def project_provider_raw(
        self,
        raw: Any,
        *,
        provider_name: str = "",
    ) -> Optional[ProviderAnimePayload]:
        """Project a provider row into a neutral payload before identity resolution."""
        if raw is None:
            return None
        if isinstance(raw, ProviderAnimePayload):
            return raw
        payload = anime_to_provider_payload(
            raw,
            source_provider=_provider_name_from_spec(provider_name),
        )
        if not payload.external_ids:
            return None
        return payload

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
            index_repo=CatalogIndexRepository(db),
            merge_service=CatalogMergeService(
                CatalogMergeRepository(
                    db,
                    log_fn=lambda msg: self.log("API_COORDINATOR", msg),
                )
            ),
            batched_writes=_batched_writes,
            log_fn=lambda msg: self.log("API_COORDINATOR", msg),
        )
        return self._catalog_identity

    @staticmethod
    def _set_list_light_mode(providers: Iterable[Any], enabled: bool) -> None:
        for provider in providers:
            if hasattr(provider, "list_light"):
                provider.list_light = enabled
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

    def _assign_payloads_to_records(
        self, payloads: List[ProviderAnimePayload]
    ) -> List[AnimeRecord]:
        if not payloads:
            return []

        identity = self._ensure_catalog_identity()
        if identity is None:
            return []

        mapping_port = None
        db_manager = self._database_manager
        if db_manager is not None:
            mapping_port = getattr(db_manager, "_mapping_port", None)

        pending_payloads: List[ProviderAnimePayload] = []
        normalized_list: List[Dict[str, int]] = []
        mapping_cache: Dict[tuple[str, int], Dict[str, int]] = {}
        for payload in payloads:
            normalized = _normalize_external_ids(payload.external_ids or {})
            if not normalized:
                continue
            expanded = expand_external_ids_with_mapping(
                normalized,
                mapping_port,
                cache=mapping_cache,
            )
            pending_payloads.append(payload)
            normalized_list.append(expanded)

        if not normalized_list:
            return []

        try:
            resolved = identity.resolve_external_ids_batch(normalized_list)
        except Exception as exc:
            self.log(
                "API_COORDINATOR",
                f"Batch catalog resolve failed: {type(exc).__name__}: {exc}",
            )
            self._telemetry.increment("coordinator.batch_resolve_errors")
            return []

        records: List[AnimeRecord] = []
        for payload, entry in zip(pending_payloads, resolved):
            catalog_id = int(entry.catalog_id)
            if catalog_id <= 0:
                continue
            records.append(
                payload_to_anime_record(
                    payload,
                    catalog_id,
                    external_ids=entry.external_ids,
                )
            )

        deduped = deduplicate_records(records)
        kept = [record for record in deduped if int(record.id) > 0]
        dropped = len(deduped) - len(kept)
        if dropped:
            self._telemetry.increment("coordinator.provisional_dropped", dropped)
            self.log(
                "API_COORDINATOR",
                f"Dropped {dropped} provisional/unresolved catalogue row(s)",
            )
        return kept

    def _finalize_catalog_records(
        self, payloads: Sequence[ProviderAnimePayload]
    ) -> List[AnimeRecord]:
        """Resolve payload externals to catalogue ids, dedupe, and drop invalid rows."""
        return self._assign_payloads_to_records(list(payloads))

    @staticmethod
    def _record_to_anime(record: AnimeRecord) -> Anime:
        """Reconstruct a legacy `Anime` object from a normalized record."""
        return anime_record_to_legacy_anime(record)

    def _persist_catalog_records(
        self,
        records: List[AnimeRecord],
        *,
        enrich: bool = True,
        source: WriteSource = WriteSource.SEARCH,
    ) -> int:
        if not records:
            return 0
        try:
            write_service = self._write_service
            db_manager = self._database_manager
            if write_service is not None:
                result = write_service.persist_records(records, source=source)
                persisted = int(result.persisted)
                if result.errors:
                    self._telemetry.increment("coordinator.persist_errors")
            elif db_manager is not None:
                animes = [self._record_to_anime(r) for r in records]
                persisted = db_manager.upsert_anime_batch(animes)
            else:
                return 0
            if enrich and persisted and db_manager is not None:
                ids = [r.id for r in records if int(r.id) > 0]
                if ids:
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

    def _build_sink(
        self,
        *,
        enrich: bool = True,
        source: WriteSource = WriteSource.SEARCH,
    ):
        """Return a persistence sink bound to the configured DatabaseManager."""
        if self._database_manager is None:
            return None

        def sink(payloads: Sequence[ProviderAnimePayload]) -> int:
            records = self._finalize_catalog_records(list(payloads))
            if not records:
                return 0
            return self._persist_catalog_records(
                records,
                enrich=enrich,
                source=source,
            )

        return sink


def _provider_name_from_spec(provider_name: str) -> ProviderName:
    lowered = (provider_name or "").lower()
    if "jikan" in lowered or "mal" in lowered:
        return ProviderName.JIKAN
    if "anilist" in lowered:
        return ProviderName.ANILIST
    if "kitsu" in lowered:
        return ProviderName.KITSU
    if "anidb" in lowered:
        return ProviderName.ANIDB
    return ProviderName.UNKNOWN


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
