"""Engine trust policy.

Loads the static policy file shipped alongside this module and filters a
candidate engine list down to the entries that satisfy a given
``SearchProfile``. The policy is the *only* place where decisions about
which third-party engines to invoke should live - the worker just runs
whatever the policy hands it.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .config import SearchProfile
from .telemetry import structured_log

_POLICY_FILE = os.path.join(os.path.dirname(__file__), "engine_policy.json")


@dataclass(frozen=True)
class EngineRecord:
    """Static metadata about a single nova3 engine."""

    name: str
    enabled: bool
    risk_level: str
    anime_relevant: bool
    requires_insecure_tls: bool
    missing_timeout: bool
    nsfw: bool = False
    notes: str = ""


class EnginePolicy:
    """Read-only view over the engine policy file.

    The policy file is loaded lazily on first use and cached. Tests can
    inject an alternative file path with ``EnginePolicy.load``.
    """

    _DEFAULT_RECORD = EngineRecord(
        name="",
        enabled=False,
        risk_level="unknown",
        anime_relevant=False,
        requires_insecure_tls=False,
        missing_timeout=False,
    )

    def __init__(self, records: Dict[str, EngineRecord], default_action: str):
        self._records = records
        self._default_action = default_action

    @classmethod
    def load(cls, path: Optional[str] = None) -> "EnginePolicy":
        """Load the policy from disk."""
        target = path or _POLICY_FILE
        with open(target, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        records: Dict[str, EngineRecord] = {}
        for name, raw in (data.get("engines") or {}).items():
            records[name] = EngineRecord(
                name=name,
                enabled=bool(raw.get("enabled", False)),
                risk_level=str(raw.get("risk_level", "unknown")),
                anime_relevant=bool(raw.get("anime_relevant", False)),
                requires_insecure_tls=bool(raw.get("requires_insecure_tls", False)),
                missing_timeout=bool(raw.get("missing_timeout", False)),
                nsfw=bool(raw.get("nsfw", False)),
                notes=str(raw.get("notes", "")),
            )
        default_action = str(data.get("default_action", "deny"))
        return cls(records, default_action)

    def record_for(self, engine: str) -> EngineRecord:
        return self._records.get(engine, self._DEFAULT_RECORD)

    def known_engines(self) -> Tuple[str, ...]:
        return tuple(sorted(self._records.keys()))

    def filter(
        self,
        candidates: Iterable[str],
        profile: SearchProfile,
        request_id: Optional[str] = None,
    ) -> List[str]:
        """Return the subset of ``candidates`` allowed for ``profile``."""
        explicit_allowlist = (
            set(name.lower() for name in profile.engines) if profile.engines else None
        )
        kept: List[str] = []
        for engine in candidates:
            decision, reason = self._evaluate(engine, profile, explicit_allowlist)
            if decision:
                kept.append(engine)
            else:
                structured_log(
                    "engine_filtered",
                    request_id=request_id,
                    engine=engine,
                    profile=profile.name,
                    reason=reason,
                )
        return kept

    def _evaluate(
        self,
        engine: str,
        profile: SearchProfile,
        allowlist: Optional[set],
    ) -> Tuple[bool, str]:
        if allowlist is not None and engine.lower() not in allowlist:
            return False, "not_in_explicit_allowlist"

        record = self._records.get(engine)
        if record is None:
            if self._default_action == "allow":
                return True, "unknown_engine_default_allow"
            return False, "unknown_engine_default_deny"

        if not record.enabled:
            return False, "policy_disabled"
        if record.requires_insecure_tls and not profile.allow_insecure_engines:
            return False, "requires_insecure_tls"
        if record.missing_timeout and not profile.allow_no_timeout_engines:
            return False, "missing_timeout"
        if record.nsfw and not profile.allow_nsfw:
            return False, "nsfw_blocked"
        return True, "ok"


_lock = threading.Lock()
_cached_policy: Optional[EnginePolicy] = None


def get_default_policy() -> EnginePolicy:
    """Return a process-wide cached policy."""
    global _cached_policy
    with _lock:
        if _cached_policy is None:
            _cached_policy = EnginePolicy.load()
        return _cached_policy


def reset_default_policy() -> None:
    """Clear the cached policy. Intended for tests that mutate the file."""
    global _cached_policy
    with _lock:
        _cached_policy = None
