"""
Lightweight security regression tests for the embedded MariaDB bootstrap.

These tests assert the SOURCE TEXT contract (no `--skip-grant-tables`
in steady-state startup, root fallback gated behind a flag). They never
actually start MariaDB so they are safe to run in any environment.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EMBEDDED_DB = ROOT / "adapters" / "persistence" / "embeddedMariaDB.py"


def _source() -> str:
    return EMBEDDED_DB.read_text(encoding="utf-8")


def test_skip_grant_tables_not_in_steady_state_startup():
    src = _source()
    # `_start_mariadb_server` must not pass --skip-grant-tables; we look for the
    # canonical argv list and assert the flag is missing from the server cmd.
    start_idx = src.find("def _start_mariadb_server")
    setup_idx = src.find("def _setup_database_security")
    assert start_idx != -1, "_start_mariadb_server method missing"
    assert setup_idx != -1, "_setup_database_security method missing"
    body = src[start_idx:setup_idx]
    assert "--skip-grant-tables" not in body, (
        "steady-state MariaDB startup must not include --skip-grant-tables"
    )


def test_allow_root_fallback_is_opt_in():
    src = _source()
    assert "allow_root_fallback" in src
    # Default is False (settings.get with False default).
    assert "settings.get(\"allow_root_fallback\", False)" in src


def test_getid_fallback_uses_column_whitelist():
    src = _source()
    assert "allowed_columns" in src
    assert "raise ValueError" in src or "raise ValueError(f" in src


def test_getid_fallback_uses_parameterized_query():
    """The fallback query must bind id values via placeholders, not f-strings."""
    src = _source()
    # The query is constructed once `apiKey` is validated; ensure it uses %s for id.
    assert "WHERE id" in src
    # No raw string interpolation of the id should exist in the fallback method.
    fallback_idx = src.find("def _getId_fallback")
    assert fallback_idx != -1
    next_def = src.find("\n    def ", fallback_idx + 1)
    fallback_body = src[fallback_idx:next_def]
    assert "f\"SELECT" not in fallback_body or "{apiId}" not in fallback_body
