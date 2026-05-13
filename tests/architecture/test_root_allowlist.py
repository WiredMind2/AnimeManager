"""Root directory hygiene (ADR 0006 enforcement).

The repository root is reserved for startup/packaging glue. This test
fails if a new Python module is added at the root without being
explicitly approved.

``ROOT_REQUIRED``
    Modules that must exist for the application to start (``run.py``,
    ``bootstrap.py``, ``setup.py``, ``__init__.py``,
    ``sitecustomize.py``).

``ROOT_SHIMS``
    Previously held deprecated re-export shims. The cleanup landed under
    the Root Hygiene plan; the set is now empty and any test that
    iterates over it simply has no work to do.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

REPO_ROOT = Path(__file__).resolve().parents[2]


ROOT_REQUIRED = {
    "__init__.py",
    "bootstrap.py",
    "run.py",
    "setup.py",
    "sitecustomize.py",
}

ROOT_SHIMS: set[str] = set()


def _list_root_python_files() -> set[str]:
    out = set()
    for name in os.listdir(REPO_ROOT):
        full = REPO_ROOT / name
        if full.is_file() and name.endswith(".py"):
            out.add(name)
    return out


def test_repository_root_has_only_allowlisted_python_files():
    actual = _list_root_python_files()
    expected = ROOT_REQUIRED

    unexpected = actual - expected
    missing_required = ROOT_REQUIRED - actual

    assert not unexpected, (
        "Unexpected Python files at the repository root. Either move "
        "them into a layered package or add them to ROOT_REQUIRED with "
        "a justification: " + ", ".join(sorted(unexpected))
    )
    assert not missing_required, (
        "Required root-level module(s) are missing: "
        + ", ".join(sorted(missing_required))
    )
