"""Central configuration for the torrent search orchestration layer.

Defines profile-aware limits, timeouts, and feature flags. Keeping all
tunables in one place makes the runtime behavior auditable and lets the
GUI (interactive profile) and the REST API (strict profile) share the same
codebase with very different operational envelopes.

The values below are intentionally conservative defaults. Override them
through the public ``load_config`` helper or environment variables prefixed
with ``ANIME_SEARCH_``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Optional

DEFAULT_PROFILE = "interactive"


@dataclass(frozen=True)
class SearchLimits:
    """Hard limits enforced by the orchestration layer for a single request.

    Attributes:
        max_terms: Maximum number of distinct search terms accepted after
            normalization. Prevents combinatorial subprocess fan-out when a
            caller passes huge synonym lists.
        max_term_length: Upper bound on a single term length in characters.
        max_concurrent_jobs: Maximum subprocess workers allowed in flight at
            the same time across all terms.
        per_job_timeout_s: Wall-clock budget for one ``nova3.nova2`` job.
        request_deadline_s: Global budget for an entire search request.
        max_results: Maximum results returned to the caller (post dedupe).
        max_output_bytes: Maximum total stdout bytes read per worker. Guards
            against runaway children writing unbounded data.
        max_line_bytes: Maximum length of a single stdout line.
        queue_capacity: Maximum number of pending results buffered between
            workers and the caller. Enforces backpressure.
    """

    max_terms: int = 6
    max_term_length: int = 200
    max_concurrent_jobs: int = 4
    per_job_timeout_s: float = 45.0
    request_deadline_s: float = 90.0
    max_results: int = 500
    max_output_bytes: int = 8 * 1024 * 1024
    max_line_bytes: int = 16 * 1024
    queue_capacity: int = 256


@dataclass(frozen=True)
class SearchProfile:
    """Behavioral profile describing how a caller wants to run searches.

    Attributes:
        name: Human-readable identifier used in logs/metrics.
        limits: Hard limits applied to the request.
        allow_insecure_engines: When False, engines flagged as requiring
            insecure TLS are removed before scheduling.
        allow_no_timeout_engines: When False, engines flagged as missing
            HTTP timeouts are removed before scheduling.
        engines: Optional explicit allowlist. When ``None`` the policy
            file's default selection is used.
        category: nova2 category to forward (``anime`` for this app).
        rank_results: When True, results are emitted in deterministic rank
            order rather than as they arrive. Useful for the REST API.
    """

    name: str
    limits: SearchLimits = field(default_factory=SearchLimits)
    allow_insecure_engines: bool = False
    allow_no_timeout_engines: bool = False
    engines: Optional[tuple] = None
    category: str = "anime"
    rank_results: bool = False


INTERACTIVE_PROFILE = SearchProfile(
    name="interactive",
    limits=SearchLimits(
        max_terms=8,
        max_concurrent_jobs=6,
        per_job_timeout_s=45.0,
        request_deadline_s=120.0,
        max_results=750,
    ),
    allow_insecure_engines=False,
    allow_no_timeout_engines=True,
    rank_results=False,
)

STRICT_PROFILE = SearchProfile(
    name="strict",
    limits=SearchLimits(
        max_terms=4,
        max_concurrent_jobs=3,
        per_job_timeout_s=20.0,
        request_deadline_s=45.0,
        max_results=200,
    ),
    allow_insecure_engines=False,
    allow_no_timeout_engines=False,
    rank_results=True,
)

DEFAULT_PROFILES = {
    "interactive": INTERACTIVE_PROFILE,
    "strict": STRICT_PROFILE,
}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_profile(name: str = DEFAULT_PROFILE) -> SearchProfile:
    """Return a profile by name, applying environment overrides.

    Environment overrides use the prefix ``ANIME_SEARCH_<UPPER_PROFILE>_<KEY>``.
    Unknown profiles fall back to ``interactive``.
    """
    base = DEFAULT_PROFILES.get(name, INTERACTIVE_PROFILE)
    prefix = f"ANIME_SEARCH_{base.name.upper()}_"

    limits = base.limits
    overrides = {
        "max_terms": _env_int(prefix + "MAX_TERMS", limits.max_terms),
        "max_term_length": _env_int(prefix + "MAX_TERM_LENGTH", limits.max_term_length),
        "max_concurrent_jobs": _env_int(
            prefix + "MAX_CONCURRENT_JOBS", limits.max_concurrent_jobs
        ),
        "per_job_timeout_s": _env_float(
            prefix + "PER_JOB_TIMEOUT_S", limits.per_job_timeout_s
        ),
        "request_deadline_s": _env_float(
            prefix + "REQUEST_DEADLINE_S", limits.request_deadline_s
        ),
        "max_results": _env_int(prefix + "MAX_RESULTS", limits.max_results),
        "max_output_bytes": _env_int(
            prefix + "MAX_OUTPUT_BYTES", limits.max_output_bytes
        ),
        "max_line_bytes": _env_int(prefix + "MAX_LINE_BYTES", limits.max_line_bytes),
        "queue_capacity": _env_int(prefix + "QUEUE_CAPACITY", limits.queue_capacity),
    }
    return replace(base, limits=SearchLimits(**overrides))
