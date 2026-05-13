"""Shared pytest configuration for AnimeManager.

The legacy ``Manager`` monolith was removed during the client/server
refactor, so this file no longer ships a ``manager`` fixture. New tests
should either:

* depend directly on the backend services through
  :func:`AnimeManager.backend.build_embedded_facade` (and inject fakes for
  the ports), or
* exercise the public client adapters via the SDK (``AnimeManager.clients.sdk``).
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest


def pytest_configure(config):
    """Configure pytest for AnimeManager testing."""
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

    os.environ["ANIME_MANAGER_TESTING"] = "1"
    # Tests should never spin up the desktop UI; the refactored backend
    # honors this flag in its adapters.
    os.environ["ANIME_MANAGER_REMOTE"] = "1"

    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line(
        "markers", "external: marks tests that require external services"
    )
    config.addinivalue_line("markers", "database: marks tests that require database")


def pytest_collection_modifyitems(config, items):
    """Annotate integration tests as slow to keep the default suite fast."""
    for item in items:
        if "integration" in item.nodeid.lower():
            item.add_marker(pytest.mark.slow)


@pytest.fixture(scope="session")
def temp_dir():
    """Yield a temporary directory shared across a test session."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture(scope="function")
def mock_database():
    """Provide a throwaway SQLite database for tests that need a real file."""
    import sqlite3

    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_db.close()

    conn = sqlite3.connect(temp_db.name)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS anime (
            id INTEGER PRIMARY KEY,
            title TEXT,
            status TEXT,
            episodes INTEGER,
            rating TEXT,
            like INTEGER DEFAULT 0,
            tag TEXT DEFAULT 'NONE'
        )
        """
    )
    conn.commit()
    conn.close()

    yield temp_db.name

    os.unlink(temp_db.name)


pytest_plugins = []
