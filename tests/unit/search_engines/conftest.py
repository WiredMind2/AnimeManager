"""Shared fixtures for the new search_engines test suite."""

from __future__ import annotations

import json
import os
import sys

# Make the project root importable when tests are run directly.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from search_engines.engine_policy import EnginePolicy
from search_engines.telemetry import get_metrics


@pytest.fixture
def reset_metrics():
    """Reset the process-wide metrics aggregator before/after each test."""
    get_metrics().reset()
    yield
    get_metrics().reset()


@pytest.fixture
def policy_factory(tmp_path):
    """Build a custom EnginePolicy from inline dict data."""

    def _build(engines: dict, default_action: str = "deny") -> EnginePolicy:
        path = tmp_path / "policy.json"
        path.write_text(
            json.dumps({"default_action": default_action, "engines": engines}),
            encoding="utf-8",
        )
        return EnginePolicy.load(str(path))

    return _build
