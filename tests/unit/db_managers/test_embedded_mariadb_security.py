"""
Lightweight security regression tests for the embedded MariaDB bootstrap.

These tests assert the SOURCE TEXT contract (no `--skip-grant-tables`
in steady-state startup, root fallback gated behind a flag). They never
actually start MariaDB so they are safe to run in any environment.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


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


def test_embedded_mariadb_assigns_port_before_pool_init():
    """Pool warm-up reads ``self.port``; credentials must precede ``super().__init__``."""
    src = _source()
    init_idx = src.find("def __init__(self, settings=None)")
    assert init_idx != -1
    super_idx = src.find("super().__init__(settings=self.settings)", init_idx)
    port_idx = src.find("self.port =", init_idx)
    assert port_idx != -1 and super_idx != -1
    assert port_idx < super_idx, "self.port must be assigned before BaseDB.__init__"


def test_embedded_mariadb_start_is_serialized():
    src = _source()
    assert "_MARIADB_START_LOCK" in src
    start_idx = src.find("def _start_mariadb_server")
    body = src[start_idx : start_idx + 400]
    assert "with _MARIADB_START_LOCK" in body


def test_create_connection_does_not_use_mysql_connector_pool_args():
    """Custom ConnectionPool must not nest mysql-connector's global pool (max 5)."""
    src = _source()
    create_idx = src.find("def _create_connection")
    assert create_idx != -1
    next_def = src.find("\n    def ", create_idx + 1)
    body = src[create_idx:next_def]
    for arg in ("pool_name", "pool_size", "pool_reset_session"):
        assert f"{arg}=" not in body, (
            f"_create_connection must not pass {arg}= (triggers mysql-connector pooling)"
        )


def test_create_connection_runtime_kwargs_exclude_pool_args(monkeypatch):
    """Regression: factory must create plain connections, not pooled ones."""
    from adapters.persistence.embeddedMariaDB import EmbeddedMariaDB

    captured: dict = {}

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            ping=lambda **_kw: None,
            close=lambda: None,
            is_connected=lambda: True,
        )

    monkeypatch.setattr(
        "adapters.persistence.embeddedMariaDB.mysql.connector.connect",
        fake_connect,
    )

    db = EmbeddedMariaDB.__new__(EmbeddedMariaDB)
    db.port = 3307
    db.user = "animemanager"
    db.password = "animemanager"
    db.database = "anime_manager"
    db.log = lambda *_args, **_kwargs: None

    db._create_connection()

    for key in ("pool_name", "pool_size", "pool_reset_session"):
        assert key not in captured
    assert captured.get("host") == "127.0.0.1"
    assert captured.get("port") == 3307
