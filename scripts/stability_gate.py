#!/usr/bin/env python3
"""Mandatory refactor stability gate.

Runs architecture boundary checks and the critical metadata-pipeline unit
suite. Exit code 0 means the gate passed.

Usage:
    python scripts/stability_gate.py
    python scripts/stability_gate.py --verbose
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

GATE_PATHS = [
    "tests/unit/components/test_api_coordinator_edges.py",
    "tests/unit/components/test_api_coordinator_stream_fetch.py",
    "tests/unit/core/test_ingestion_pipeline.py",
    "tests/unit/core/test_ingestion_pipeline_edges.py",
    "tests/unit/application/test_provider_health.py",
    "tests/unit/adapters/api/test_provider_contract.py",
    "tests/unit/animeAPI/test_anilist_edges.py",
    "tests/unit/animeAPI/test_jikan_edges.py",
    "tests/unit/animeAPI/test_kitsu_edges.py",
    "tests/unit/animeAPI/test_mal_edges.py",
    "tests/unit/animeAPI/test_conversion_methods.py",
]


def _run(cmd: list[str], *, verbose: bool) -> int:
    if verbose:
        print("+", " ".join(cmd), flush=True)
    env = dict(os.environ)
    env["PYTEST_ADDOPTS"] = ""
    root = str(REPO_ROOT)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = root if not existing else f"{root}{os.pathsep}{existing}"
    proc = subprocess.run(cmd, cwd=REPO_ROOT, env=env)
    return int(proc.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AnimeManager stability gate")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    py = sys.executable
    pytest_base = [py, "-m", "pytest", "-o", "addopts=", "-q", "--tb=short"]

    arch_cmd = [*pytest_base, "-m", "architecture", "tests/architecture"]
    code = _run(arch_cmd, verbose=args.verbose)
    if code != 0:
        print("STABILITY GATE FAILED: architecture boundaries", file=sys.stderr)
        return code

    unit_cmd = [*pytest_base, *GATE_PATHS]
    code = _run(unit_cmd, verbose=args.verbose)
    if code != 0:
        print("STABILITY GATE FAILED: metadata pipeline unit suite", file=sys.stderr)
        return code

    print("STABILITY GATE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
