Search Pipeline
===============

The torrent search subsystem turns a list of candidate anime titles into
a stream of validated torrent records. It lives entirely under
:mod:`search_engines` and is the *only* surface that talks to the
vendored ``nova3`` qBittorrent search plug-ins. The pipeline replaces
the legacy "single ``search_engines.search(terms)`` generator that built
shell command strings" implementation with an explicit composition of
planner, policy, worker pool, parser, dedupe and ranking stages.

This document is a short architectural tour aimed at backend
contributors. The exhaustive developer guide -- including security
posture, performance budgets, telemetry catalogue, engine policy file
format, and the test layout -- lives in
:file:`search_engines/README.md`. Read it before extending the
pipeline.

Where the pipeline fits
-----------------------

Search is invoked from two call sites:

* The Tk GUI uses :func:`search_engines.search`, which mirrors the
  legacy streaming generator signature. Results are yielded as plain
  dictionaries so the existing GUI rendering code keeps working
  unchanged.
* The HTTP client (``clients.http``) calls
  :func:`search_engines.search_strict`, which returns a fully
  materialised, ranked list suitable for a JSON response body.

Both functions are thin wrappers around
:class:`search_engines.facade.SearchFacade`, which is the orchestrator
proper. Tests and advanced callers can construct
``SearchFacade.for_profile("strict")`` or supply a custom
:class:`search_engines.config.SearchProfile` directly.

Stages and modules
------------------

::

    raw terms ──> planner ──> engine policy ──> worker pool ──┐
                                                              │
                                                              ▼
                       ranked / streamed <── dedupe <── parser
                                                              │
                                                              ▼
                                                       telemetry

Each stage maps to exactly one module so that the boundaries can be
unit-tested in isolation.

* :mod:`search_engines.config` declares :class:`SearchLimits` and
  :class:`SearchProfile`, plus the two shipped profiles
  ``interactive`` and ``strict``. Both profiles can be tuned at
  runtime through environment variables prefixed
  ``ANIME_SEARCH_<PROFILE>_<FIELD>`` -- e.g.
  ``ANIME_SEARCH_STRICT_MAX_RESULTS=50``. The profile is the single
  source of truth for *every* tunable knob.
* :mod:`search_engines.planner` exposes
  :class:`search_engines.planner.QueryPlanner`. The planner normalises
  raw input through NFKC, strips control characters, drops degenerate
  terms, scores the remainder for discriminative power (rewarding
  alphanumerically rich and script-mixed terms), and caps the result
  to ``limits.max_terms``. The planner is pure; the tests in
  ``tests/unit/search_engines/test_planner.py`` pin the heuristics.
* :mod:`search_engines.engine_policy` reads the declarative
  :file:`search_engines/engine_policy.json` and filters candidate
  engines for the active profile. Engines flagged as
  ``requires_insecure_tls``, ``missing_timeout`` or ``nsfw`` are
  silently dropped when the active profile forbids them, and a
  structured ``engine_filtered`` log entry is emitted for every
  drop with a ``reason=`` code. The same module exposes
  :func:`search_engines.engine_policy.get_default_policy` and
  :func:`search_engines.engine_policy.reset_default_policy` for tests.
* :mod:`search_engines.worker` runs one
  :class:`search_engines.worker.SearchJob` per planned term using
  :class:`search_engines.worker.NovaWorker`. The worker spawns
  ``[sys.executable, "-m", "nova3.nova2", engines, category, term]``
  with ``shell=False`` and enforces a per-job timeout, an output cap
  (``limits.max_output_bytes``), a per-line cap
  (``limits.max_line_bytes``), and a cooperative cancellation event.
  Processes that overshoot their deadline are escalated through
  ``terminate`` and then ``kill``.
* :mod:`search_engines.parser` produces immutable
  :class:`search_engines.parser.TorrentResult` records out of the
  legacy pipe-delimited nova3 output. The parser validates the magnet
  URI shape, extracts an infohash, normalises text fields, coerces
  numeric fields safely, and increments fine-grained counters
  (``parser_dropped_non_magnet``, ``parser_dropped_oversize``,
  ``parser_size_coerced``, …) for anything it has to drop.
* :mod:`search_engines.dedupe` keeps a thread-safe ``set`` of stable
  fingerprints. Infohashes are used when present; otherwise a
  case-folded tuple of normalised name, size, engine URL and
  description URL is used. This replaces the legacy
  ``hash(dict.values())`` codepath that silently collapsed distinct
  records onto ``None``.
* :mod:`search_engines.ranking` exposes
  :func:`search_engines.ranking.sort_results`, used only when the
  active profile sets ``rank_results=True``. The ordering is
  ``(-seeds, -size, name.casefold(), engine_url)`` so REST responses
  are byte-stable across runs.
* :mod:`search_engines.facade` glues everything together via
  :class:`search_engines.facade.SearchFacade`. The facade owns the
  bounded ``threading.BoundedSemaphore`` that enforces
  ``limits.max_concurrent_jobs`` across worker threads, the bounded
  :class:`queue.Queue` that backpressures the streaming consumer, the
  per-request deadline, and the assembly of the per-request
  :class:`search_engines.facade.SearchSummary` for operational logs.

How the stages interact
-----------------------

The facade drives the pipeline as follows:

1. Generate a request id and run the planner over the caller's terms.
2. Filter the engine universe (``policy.known_engines()``) through the
   active profile's policy and explicit allowlist.
3. Short-circuit with an empty stream when no terms or no engines
   survived. Both outcomes are recorded via the
   ``request_empty`` structured log.
4. Spawn the pool thread, which schedules one
   :class:`search_engines.worker.SearchJob` per planned term inside
   the bounded semaphore.
5. For each result produced by a worker, the
   :class:`search_engines.dedupe.ResultDeduper` decides whether to
   forward it to the bounded :class:`queue.Queue` stream. The first
   ``limits.max_results`` accepted hits cause a cancellation event
   that interrupts the remaining workers.
6. The caller either iterates the stream as it arrives
   (``rank_results=False`` profile) or buffers everything until the
   deadline and yields it sorted
   (``rank_results=True`` profile).
7. On completion the facade emits a ``request_done`` log entry that
   includes the per-job :class:`search_engines.worker.JobOutcome`
   records (timeouts, exit reasons, byte counts), so operational
   dashboards can spot misbehaving engines quickly.

The legacy callers therefore see exactly the same dict shape as before
(``link``, ``name``, ``size``, ``seeds``, ``leech``, ``engine_url``,
``desc_link``) plus an extra ``infohash`` field that enables further
client-side dedupe.

Extending the pipeline
----------------------

The pipeline is intentionally extensible at boundaries rather than
internals:

* **New engine**: drop the vendor file under :file:`search_engines/nova3/engines/`
  and add an entry in :file:`search_engines/engine_policy.json`. No
  Python change is required.
* **New profile**: build a :class:`search_engines.config.SearchProfile`
  in :mod:`search_engines.config` and re-export it through
  :file:`search_engines/__init__.py`.
* **Different ranking**: replace
  :func:`search_engines.ranking.sort_results`. The facade calls it
  exactly once per request when the active profile asks for ranking.
* **New metric**: call
  :func:`search_engines.telemetry.get_metrics` and increment a
  counter or accumulate a timing. The metrics object is global and
  thread-safe.

For the long-form developer guide -- security posture, performance
budgets, telemetry catalogue, engine policy file format, and the test
matrix -- see :file:`search_engines/README.md` in the repository
checkout. Treat that document as the source of truth; this page is the
short architectural index intended for navigation.
