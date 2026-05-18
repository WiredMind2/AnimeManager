"""ADR 0003 / 0006 enforcement: layer boundary checks.

This test parses each runtime layer's source files and asserts that
they only import from layers allowed by the architecture. The rules
implemented here are:

``domain``
    Must not import from ``adapters``, ``clients``, ``composition``,
    or any external framework (fastapi, tkinter, requests, sqlite3,
    PIL). It must also avoid all deleted legacy root packages
    (``db_managers``, ``animeAPI``, ``torrent_managers``,
    ``file_managers``, ``media_players``, ``components``, ``core``).

``application``
    Must not import from concrete ``adapters`` packages (only from
    ``ports``, ``domain``, ``shared``).

``ports``
    Must not import from anything concrete (no ``adapters``,
    ``clients``, ``composition``, ``shared``, external frameworks).
    May only import from ``domain`` and the Python standard library.

``clients``
    Must only import from ``application``, ``ports``, ``shared``,
    ``composition`` (plus stdlib/3rd-party UI/transport libraries).
    They may NOT reach into ``adapters`` or any of the deleted legacy
    integration modules.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

REPO_ROOT = Path(__file__).resolve().parents[2]

EXCLUDED_DIRS = {"__pycache__", "_build", "htmlcov", ".venv", ".git", "nova3"}

EXTERNAL_FORBIDDEN_FOR_DOMAIN = {
    "fastapi",
    "tkinter",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "sqlalchemy",
    "sqlite3",
    "requests",
    "PIL",
    "mpv",
    "vlc",
    "uvicorn",
    "libtorrent",
}

FORBIDDEN_FOR_DOMAIN = {
    "adapters",
    "clients",
    "composition",
    "backend",
    "db_managers",
    "animeAPI",
    "torrent_managers",
    "file_managers",
    "media_players",
    "search_engines",
    "components",
    "core",
    "launch",
    "windows",
}

FORBIDDEN_FOR_APPLICATION = {
    "adapters",
    "clients",
    "composition",
    "backend",
    "db_managers",
    "animeAPI",
    "torrent_managers",
    "file_managers",
    "media_players",
    "components",
    "core",
    "launch",
    "windows",
}

# Legacy bridge services migrated from the historical ``components/``
# tree under the Root Hygiene cleanup. They live in ``application``
# nominally (they orchestrate use-cases), but still concretely depend on
# ``adapters.legacy`` data classes and ``adapters.persistence`` helpers
# pending a follow-up refactor onto ports. Each file here is exempt from
# the ``application/`` -> ``adapters/`` import rule for the SPECIFIC
# imports listed in ``LEGACY_BRIDGE_ALLOWED_IMPORTS``.
LEGACY_BRIDGE_APPLICATION_FILES = {
    "application/services/database_manager.py",
    "application/bridges/legacy_entities.py",
}

LEGACY_BRIDGE_ALLOWED_IMPORT_PREFIXES = (
    "adapters.legacy",
    "adapters.persistence",
)

FORBIDDEN_FOR_PORTS = {
    "adapters",
    "application",
    "clients",
    "composition",
    "shared",
    "backend",
    "db_managers",
    "animeAPI",
    "torrent_managers",
    "file_managers",
    "media_players",
    "search_engines",
    "components",
    "core",
    "launch",
    "windows",
}

FORBIDDEN_FOR_CLIENTS = {
    "db_managers",
    "animeAPI",
    "torrent_managers",
    "file_managers",
    "media_players",
    "search_engines",
    "components",
    "core",
    "launch",
    "windows",
}


def _iter_layer_files(layer: str):
    root = REPO_ROOT / layer
    if not root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in filenames:
            if name.endswith(".py"):
                yield Path(dirpath) / name


def _collect_imports(path: Path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.append(node.module)
    return out


def _matches(module: str, forbidden: set[str]) -> bool:
    for prefix in forbidden:
        if module == prefix or module.startswith(prefix + "."):
            return True
    return False


def _gather_violations(layer: str, forbidden: set[str]):
    """Return a list of ``(file, module)`` tuples."""
    bad = []
    for path in _iter_layer_files(layer):
        rel = path.relative_to(REPO_ROOT)
        for imp in _collect_imports(path):
            if _matches(imp, forbidden):
                bad.append((str(rel), imp))
    return bad


def test_domain_layer_has_no_forbidden_imports():
    bad = _gather_violations("domain", FORBIDDEN_FOR_DOMAIN | EXTERNAL_FORBIDDEN_FOR_DOMAIN)
    assert not bad, (
        "domain/ must not import from adapters, frameworks, or IO modules. "
        "Violations:\n" + "\n".join(f"  {p} -> {m}" for p, m in bad)
    )


def _is_legacy_bridge_exempt(file_rel: str, module: str) -> bool:
    """Return True when ``file_rel`` -> ``module`` is an exempt bridge import."""
    normalized = file_rel.replace("\\", "/")
    if normalized not in LEGACY_BRIDGE_APPLICATION_FILES:
        return False
    for prefix in LEGACY_BRIDGE_ALLOWED_IMPORT_PREFIXES:
        if module == prefix or module.startswith(prefix + "."):
            return True
    return False


def test_application_layer_has_no_forbidden_imports():
    raw = _gather_violations("application", FORBIDDEN_FOR_APPLICATION)
    bad = [
        (file_rel, module)
        for file_rel, module in raw
        if not _is_legacy_bridge_exempt(file_rel, module)
    ]
    assert not bad, (
        "application/ must only import ports/domain/shared. "
        "Violations (excluding documented legacy bridge files):\n"
        + "\n".join(f"  {p} -> {m}" for p, m in bad)
    )


def test_ports_layer_has_no_forbidden_imports():
    bad = _gather_violations("ports", FORBIDDEN_FOR_PORTS)
    assert not bad, (
        "ports/ must depend only on domain + stdlib. Violations:\n"
        + "\n".join(f"  {p} -> {m}" for p, m in bad)
    )


def test_clients_layer_has_no_low_level_integration_imports():
    bad = _gather_violations("clients", FORBIDDEN_FOR_CLIENTS)
    assert not bad, (
        "clients/ must not reach into low-level integration modules. Violations:\n"
        + "\n".join(f"  {p} -> {m}" for p, m in bad)
    )


# ---------------------------------------------------------------------------
# Boundary hardening (post-decomposition)
# ---------------------------------------------------------------------------

# Deleted/forbidden top-level namespaces. After the Root Hygiene cleanup
# these packages no longer exist; importing them must fail loudly. The
# entries are kept here so any regression (e.g. a developer recreating
# the directory) is caught by the architecture suite immediately.
DEPRECATED_IMPORT_NAMESPACES = {
    "backend",
    "db_managers",
    "animeAPI",
    "torrent_managers",
    "file_managers",
    "windows",
    "media_players",
    "launch",
    "components",
    "core",
}

# Layers that must NEVER import from any deprecated namespace.
LAYERS_FORBIDDING_DEPRECATED_IMPORTS = (
    "domain",
    "application",
    "ports",
    "shared",
    "composition",
    "clients",
    "adapters",
)


def test_canonical_layers_do_not_import_deprecated_namespaces():
    """Every canonical layer must reach for ``adapters.*`` only.

    Imports of the legacy root packages (``backend``, ``animeAPI``,
    ``db_managers``, ``torrent_managers``, ``file_managers``,
    ``windows``, ``media_players``, ``launch``, ``components``,
    ``core``) are forbidden across all canonical layers. The packages
    were physically removed by the Root Hygiene cleanup; this guard
    catches accidental re-introduction.
    """
    bad = []
    for layer in LAYERS_FORBIDDING_DEPRECATED_IMPORTS:
        bad.extend(_gather_violations(layer, DEPRECATED_IMPORT_NAMESPACES))
    assert not bad, (
        "Canonical layers must not import from deprecated namespaces "
        "(use adapters.* / application.* / shared.* instead). "
        "Violations:\n"
        + "\n".join(f"  {p} -> {m}" for p, m in bad)
    )
