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
from typing import Any, Dict, Iterable, List, Optional

from shared.base_component import BaseComponent
from shared.contracts import AnimeRecord, IngestionResult, IngestionStatus, ProviderName
from application.services.ingestion_pipeline import IngestionPipeline, ProviderSpec
from shared.telemetry import get_telemetry
from adapters.legacy.legacy_classes import Anime, AnimeList


class APICoordinator(BaseComponent):
    """Bounded-concurrency, gateway-only multi-provider search coordinator."""

    def __init__(self, *, max_workers: int = 4, provider_timeout_s: float = 20.0):
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
            self._build_sink()
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

    def fetch_latest(self, limit: int = 50) -> Optional[IngestionResult]:
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
        specs = [
            self._schedule_spec_for(provider)
            for provider in providers
            if hasattr(provider, "schedule")
        ]
        if not specs:
            return None

        sink = (
            self._build_sink()
            if self._feature_flags.get("db_gateway_writes_only", True)
            else None
        )
        result: IngestionResult = self._pipeline.run(
            specs,
            "",
            limit=limit,
            sink=sink,
        )
        self._telemetry.set_gauge(
            "coordinator.last_schedule_records", float(len(result.records))
        )
        self._telemetry.set_gauge(
            "coordinator.last_schedule_failed", float(result.failed_providers)
        )
        self.log(
            "API_COORDINATOR",
            f"Schedule fetch completion={result.status.value} "
            f"records={len(result.records)} failed={result.failed_providers}/"
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

        return ProviderSpec(
            name=provider_name,
            search=schedule_search,
            adapter=self._legacy_adapter,
        )

    def _search_via_pipeline(self, terms: str, limit: int) -> Optional[AnimeList]:
        """Run providers through the canonical ingestion pipeline."""
        providers = list(self._api.get_providers())
        if not providers:
            return None
        specs = [self._spec_for(provider) for provider in providers if provider is not None]
        sink = (
            self._build_sink()
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

        return ProviderSpec(name=provider_name, search=search, adapter=self._legacy_adapter)

    @staticmethod
    def _legacy_adapter(raw: Any) -> Optional[AnimeRecord]:
        """Project a legacy `Anime`-like object into the canonical record."""
        if raw is None:
            return None
        rid = getattr(raw, "id", None)
        if rid is None:
            return None
        try:
            rid = int(rid)
        except (TypeError, ValueError):
            return None
        title = getattr(raw, "title", None) or ""
        return AnimeRecord(
            id=rid,
            title=str(title),
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
            source_provider=ProviderName.UNKNOWN,
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
        return anime

    def _build_sink(self):
        """Return a persistence sink bound to the configured DatabaseManager."""
        db_manager = self._database_manager
        if db_manager is None:
            return None

        def sink(records: List[AnimeRecord]) -> int:
            try:
                animes = [self._record_to_anime(r) for r in records]
                return db_manager.upsert_anime_batch(animes)
            except Exception as exc:
                self.log("API_COORDINATOR", f"Failed persisting search results: {exc}")
                self._telemetry.increment("coordinator.persist_errors")
                return 0

        return sink


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
