"""ADR 0005 enforcement: no new multi-inheritance in runtime modules.

This test scans every Python file under the canonical runtime layers
(``domain``, ``application``, ``ports``, ``adapters``, ``clients``,
``shared``, ``composition``, ``search_engines``) and fails if any class
declares more than one non-allowlisted base class.

Allowlist categories
--------------------

A base class is *not* counted toward the inheritance limit if any of
the following is true:

* its name is ``Protocol`` or ends with ``Protocol``;
* its name is ``ABC`` or ``ABCMeta``;
* its name is an exception class (ends in ``Exception`` or ``Error``
  or is ``BaseException``);
* its name appears in ``ALLOWED_BASE_NAMES`` (mixins that the
  refactor classifies as architectural helpers, e.g. dataclasses);
* the *full class qualname* appears in ``LEGACY_CLASS_ALLOWLIST``
  (expected to stay empty after the final migration cutover).
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

REPO_ROOT = Path(__file__).resolve().parents[2]

# Layers that participate in the runtime. ``tests/`` is excluded
# deliberately: tests may use multiple base classes for fixture mixins.
RUNTIME_DIRS = (
    "domain",
    "application",
    "ports",
    "adapters",
    "clients",
    "shared",
    "composition",
    "search_engines",
)

# Vendored / generated trees that must not be scanned.
EXCLUDED_DIRS = {
    "__pycache__",
    "_build",
    "htmlcov",
    ".venv",
    ".git",
    "node_modules",
    "build",
    "dist",
    "nova3",  # vendored qBittorrent search-engine plugin tree.
}

ALLOWED_BASE_NAMES = {
    # stdlib / typing helpers
    "object",
    "type",
    "NamedTuple",
    "TypedDict",
    "Enum",
    "IntEnum",
    "StrEnum",
    "Flag",
    "IntFlag",
    "Generic",
    "Mapping",
    "MutableMapping",
    "Sequence",
    "MutableSequence",
    "Iterable",
    "Iterator",
    "Callable",
    "Awaitable",
    "Coroutine",
    "Container",
    "Collection",
    # dataclasses / pydantic style (not used yet, defensive)
    "BaseModel",
}

LEGACY_CLASS_ALLOWLIST: set[str] = set()


def _iter_runtime_files():
    for top in RUNTIME_DIRS:
        root = REPO_ROOT / top
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
            for name in filenames:
                if name.endswith(".py"):
                    yield Path(dirpath) / name


def _module_id(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    return ".".join(rel.parts)


def _is_allowlisted_base(base: ast.expr) -> bool:
    """Return True if the given base node should be ignored.

    Recognises plain names, dotted attribute access
    (``typing.Protocol``) and ``Generic[...]`` subscripts.
    """
    if isinstance(base, ast.Name):
        name = base.id
    elif isinstance(base, ast.Attribute):
        name = base.attr
    elif isinstance(base, ast.Subscript):
        return _is_allowlisted_base(base.value)
    else:
        return False

    if name in ALLOWED_BASE_NAMES:
        return True
    if name == "Protocol" or name.endswith("Protocol"):
        return True
    if name in {"ABC", "ABCMeta"}:
        return True
    if name in {"BaseException", "Exception"} or name.endswith("Error") or name.endswith("Exception"):
        return True
    return False


def _collect_violations():
    violations = []
    for path in _iter_runtime_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [b for b in node.bases if not _is_allowlisted_base(b)]
            if len(bases) <= 1:
                continue
            qualname = f"{_module_id(path)}:{node.name}"
            if qualname in LEGACY_CLASS_ALLOWLIST:
                continue
            base_names = []
            for b in bases:
                if isinstance(b, ast.Name):
                    base_names.append(b.id)
                elif isinstance(b, ast.Attribute):
                    base_names.append(b.attr)
                else:
                    base_names.append(ast.unparse(b) if hasattr(ast, "unparse") else "<expr>")
            violations.append((qualname, base_names))
    return violations


def test_no_new_multi_inheritance_in_runtime_modules():
    violations = _collect_violations()
    assert not violations, (
        "ADR 0005 violation: the following classes inherit from more than one "
        "non-Protocol/non-Exception base. Refactor them to composition, or add "
        "an explicit entry to LEGACY_CLASS_ALLOWLIST after updating an ADR:\n"
        + "\n".join(f"  - {qn}: {bases}" for qn, bases in violations)
    )


def test_legacy_allowlist_is_empty():
    assert not LEGACY_CLASS_ALLOWLIST, (
        "No runtime multi-inheritance allowlist entries are allowed after final cutover."
    )
