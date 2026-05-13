Anime Metadata
==============

AnimeManager treats anime metadata as a *cross-provider* concern: no single
public catalogue is authoritative, and any one of them can rate-limit,
return partial results, or disappear entirely. The metadata feature is
therefore designed as a fan-out / dedupe / persist pipeline rather than a
client of a single API. This page describes how the provider wrappers in
:mod:`animeAPI` are loaded, how :class:`animeAPI.AnimeAPI` orchestrates
them, how :class:`components.api_coordinator.APICoordinator` turns the
results into rows in the local database, and how the whole arrangement
degrades when an upstream provider misbehaves.

Pipeline at a glance
--------------------

::

    ┌───────────────────────────────────────────────────────────┐
    │ AnimeApplicationService.search(query)                     │
    └───────────────────────────────────────┬───────────────────┘
                                            │
                                            ▼
    ┌───────────────────────────────────────────────────────────┐
    │ LegacyMetadataProviderAdapter                             │
    │   (backend.adapters.legacy_runtime)                       │
    └───────────────────────────────────────┬───────────────────┘
                                            │ search_anime(terms)
                                            ▼
    ┌───────────────────────────────────────────────────────────┐
    │ APICoordinator                                            │
    │   • rate limiter (sliding-window, 60 req/min)             │
    │   • feature flag: new_ingestion_pipeline                  │
    │   • feature flag: db_gateway_writes_only                  │
    └───────────────────────────────────────┬───────────────────┘
                                            │ ProviderSpec list
                                            ▼
    ┌───────────────────────────────────────────────────────────┐
    │ IngestionPipeline (core.ingestion_pipeline)               │
    │   • bounded ThreadPoolExecutor                            │
    │   • per-provider timeout                                  │
    │   • partial / failed accounting                           │
    └───────────────┬───────────────────────────────┬───────────┘
                    │                               │
                    │ AniListCo / Jikan /           │ telemetry events
                    │ Kitsu.io / MyAnimeList.net    │
                    ▼                               ▼
    ┌──────────────────────────────┐    ┌──────────────────────┐
    │ AnimeAPI.get_providers()     │    │ TelemetryCollector   │
    │   • lazy load on first use   │    │   coordinator.*      │
    │   • daemon init thread       │    │   pipeline.*         │
    └───────────────┬──────────────┘    └──────────────────────┘
                    │ AnimeRecord (deduplicated by id)
                    ▼
    ┌───────────────────────────────────────────────────────────┐
    │ DatabaseManager.upsert_anime_batch(animes)                │
    │   (single persistence boundary)                           │
    └───────────────────────────────────────────────────────────┘

Each arrow corresponds to a single function call or a structured contract
in :mod:`core.contracts`. Concurrency exists at exactly one layer (the
ingestion pool); the rest of the pipeline is plain straight-line code.

Provider wrappers under ``animeAPI/``
-------------------------------------

The :mod:`animeAPI` package ships one wrapper module per supported
catalogue. Each wrapper subclasses :class:`animeAPI.APIUtils.APIUtils`
and is named ``<ProviderName>Wrapper`` so :class:`animeAPI.AnimeAPI` can
discover it by importing the module file and reading the class with the
``Wrapper`` suffix:

* :mod:`animeAPI.AnilistCo` — GraphQL client for the AniList catalogue.
  Builds queries from the small :class:`animeAPI.AnilistCo.QueryObject`
  helper to keep the request body readable, and translates AniList's
  status / season vocabulary into the project's internal vocabulary.
* :mod:`animeAPI.JikanMoe` — REST client for the public unofficial
  MyAnimeList mirror at jikan.moe. Used as the *default* fallback when
  the official MAL client is not configured.
* :mod:`animeAPI.KitsuIo` — REST client for kitsu.io. Useful because the
  Kitsu API returns rich poster art and broadcast metadata that the
  other providers omit.
* :mod:`animeAPI.MyAnimeListNet` — Official OAuth2 client for
  myanimelist.net. Disabled when ``api_credentials.myanimelist`` in
  :file:`settings.json` is empty. The wrapper raises
  ``NotImplementedError`` during construction in that case so the
  loader silently skips it.

Common machinery lives in :mod:`animeAPI.APIUtils`:

* :class:`animeAPI.APIUtils.EnhancedSession` — thin wrapper around
  ``requests.Session`` that adds per-host timeouts and retries.
* Conversion helpers that map provider-specific date / status / picture
  fields onto the legacy :class:`classes.Anime` shape.

A wrapper is expected to expose at least one method:

.. code-block:: python

   class FooBarWrapper(APIUtils):
       def searchAnime(self, terms: str, limit: int = 50):
           """Yield Anime objects matching ``terms``."""

Any wrapper may additionally expose ``anime(id)``, ``character(id)``,
``schedule(...)``, ``season(...)``, ``animeCharacters(...)`` and other
methods invoked through the legacy thread fan-out path described below.

Threaded fan-out via :class:`animeAPI.AnimeAPI`
-----------------------------------------------

:class:`animeAPI.AnimeAPI` is the single facade callers reach for. Its
construction is intentionally lightweight: only a daemon
``init_thread`` runs ``load_apis`` to import every wrapper module under
:mod:`animeAPI`, instantiate it, and route any SQL writes it produces
through a shared ``sql_queue``. Wrappers that raise
``NotImplementedError`` during construction (e.g. unconfigured
:mod:`animeAPI.MyAnimeListNet`) are skipped and never join the active
set.

When a caller invokes any attribute that is not explicitly defined on
``AnimeAPI``, ``__getattr__`` returns a closure that calls
:meth:`AnimeAPI.wrapper`. The closure:

1. Joins the ``init_thread`` if it is still running, so the call sees a
   fully loaded provider set.
2. Spawns one daemon thread per loaded wrapper, each invoking the named
   method (``anime``, ``character``, ``schedule``, ``season``,
   ``searchAnime`` …) with the caller's positional and keyword
   arguments.
3. Collates results through a :class:`queue.Queue`. For single-entity
   lookups (``anime``, ``character``) the queue is drained into a
   merged :class:`classes.Anime` / :class:`classes.Character` instance.
   For list-shaped calls (``searchAnime``, ``schedule``, ``season``)
   the queue is wrapped in an :class:`classes.AnimeList` /
   :class:`classes.CharacterList` / :class:`classes.ItemList` that
   exposes results lazily as they arrive.
4. Calls :meth:`AnimeAPI.save` for single-entity results so newly
   merged data lands in the local catalogue. List responses are *not*
   auto-persisted: the coordinator owns that path through
   :class:`components.database_manager.DatabaseManager`.

The legacy fan-out path remains the default for ``anime``,
``character``, ``schedule`` and ``season``. Search is handled by the
new pipeline described below.

Search orchestration via :class:`components.api_coordinator.APICoordinator`
---------------------------------------------------------------------------

For the search use-case, :class:`AnimeAPI` exposes a structured handle
to its loaded providers through :meth:`AnimeAPI.get_providers`. The
search entry point is :meth:`APICoordinator.search_anime`, which:

1. Refuses queries shorter than three characters and queries that
   exceed the sliding-window rate limit
   (:class:`components.api_coordinator.RateLimiter`).
2. Decides between the new pipeline and the legacy fan-out based on
   the ``new_ingestion_pipeline`` feature flag. When the flag is on
   (the default) and :class:`AnimeAPI` exposes ``get_providers``, the
   coordinator builds one :class:`core.ingestion_pipeline.ProviderSpec`
   per wrapper.
3. Hands the specs to a single
   :class:`core.ingestion_pipeline.IngestionPipeline` instance, which
   runs each provider on its own thread inside a bounded
   :class:`concurrent.futures.ThreadPoolExecutor`. The executor is
   owned by the coordinator; callers do not need to drive a lifecycle.
4. Normalises every raw provider response into
   :class:`core.contracts.AnimeRecord` via
   :meth:`APICoordinator._legacy_adapter`. The adapter is defensive:
   missing ids, non-numeric ids, or completely empty rows are dropped
   silently rather than raising.
5. Optionally attaches a *persistence sink* bound to the configured
   :class:`components.database_manager.DatabaseManager`. The sink
   collapses the per-provider streams into a single batched upsert
   through :meth:`DatabaseManager.upsert_anime_batch`. This is the
   sole writer path when the ``db_gateway_writes_only`` flag is on
   (the default).
6. Translates :class:`core.contracts.IngestionResult` records back
   into legacy :class:`classes.Anime` instances so the rest of the
   codebase keeps working unchanged.

Telemetry is emitted at every stage through
:func:`core.telemetry.get_telemetry`. The notable counters and gauges
are:

* ``coordinator.search_errors`` — search invocations that raised.
* ``coordinator.last_search_records`` — gauge for the last search.
* ``coordinator.last_search_failed`` — gauge for the number of
  providers that failed during the last search.
* ``coordinator.persist_errors`` — sink failures swallowed by the
  pipeline.

Failure tolerance
-----------------

Failures are isolated at every boundary, so no single provider can
take the search subsystem down with it:

* **Wrapper construction failure.** Unhandled exceptions during
  :meth:`AnimeAPI.load_apis` are logged via ``ANIME_SEARCH`` and the
  wrapper is excluded from the active set. The remaining wrappers are
  loaded normally.
* **Per-call exception.** The legacy fan-out in :meth:`AnimeAPI.wrapper`
  wraps each provider call in ``try / except``. A failing provider is
  logged and its thread exits; the queue is still drained from the
  others.
* **Per-search exception.** :meth:`APICoordinator.search_anime` wraps
  the whole pipeline in ``try / except`` and returns ``None`` on
  failure after incrementing ``coordinator.search_errors``. The
  caller sees an empty result, not a stack trace.
* **Partial pipeline failure.** The
  :class:`core.ingestion_pipeline.IngestionResult` carries
  ``failed_providers`` and ``total_providers`` counters. When at
  least one provider produced records the coordinator returns the
  surviving subset; only :class:`core.contracts.IngestionStatus.FAILED`
  or a completely empty record set yields ``None``.
* **Sink failure.** The persistence sink built by
  :meth:`APICoordinator._build_sink` swallows database errors and
  increments ``coordinator.persist_errors``. The records are still
  returned to the caller, so a transient database fault never
  silently loses the search UI's results.
* **Rate limiting.** The sliding-window
  :class:`components.api_coordinator.RateLimiter` caps the
  coordinator at 60 search invocations per minute. Excess calls
  short-circuit before any provider thread is spawned.

Feature flags and operational knobs
-----------------------------------

The behaviour above is governed by a small set of flags configurable
through :meth:`APICoordinator.configure`:

* ``new_ingestion_pipeline`` (default ``True``). When ``False`` the
  coordinator falls back to ``self._api.searchAnime(...)`` -- the
  legacy thread fan-out path -- and the persistence sink is bypassed.
  Useful as a kill-switch during rollout.
* ``db_gateway_writes_only`` (default ``True``). When ``False`` the
  sink is not attached and writes are left to callers. Used by tests
  and as a safety knob during database migrations.

Constructor parameters tune the bounded concurrency: ``max_workers``
(default 4) sizes the executor inside
:class:`core.ingestion_pipeline.IngestionPipeline`, and
``provider_timeout_s`` (default 20 seconds) bounds each individual
provider call. See :doc:`../developer/api_db_pipeline` for the
operational runbook and end-to-end metric catalogue.
