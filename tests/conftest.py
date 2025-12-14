# pytest configuration for AnimeManager
import os
import sys
import tempfile
from pathlib import Path

import pytest


def pytest_configure(config):
    """Configure pytest for AnimeManager testing."""
    # Add project root to Python path
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

    # Set environment variables for testing
    os.environ["ANIME_MANAGER_TESTING"] = "1"
    os.environ["ANIME_MANAGER_REMOTE"] = "1"  # Use remote mode for tests

    # Add custom markers
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line(
        "markers", "external: marks tests that require external services"
    )
    config.addinivalue_line("markers", "database: marks tests that require database")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle import issues."""
    import pytest

    for item in items:
        # Add slow marker for integration tests
        if "integration" in item.nodeid.lower():
            item.add_marker(pytest.mark.slow)


# Test fixtures
@pytest.fixture(scope="session")
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture(scope="function")
def manager():
    """Create a Manager instance for testing."""
    # Import here to avoid import issues during collection
    try:
        from animeManager import Manager
    except ImportError:
        pytest.fail("Manager import failed - dependencies not available")

    return Manager(remote=True)


@pytest.fixture(scope="function")
def mock_database():
    """Create a mock database for testing."""
    import sqlite3
    import tempfile

    # Create temporary database
    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_db.close()

    conn = sqlite3.connect(temp_db.name)
    # Create basic anime table structure
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

    # Cleanup
    os.unlink(temp_db.name)


# Pytest plugins
pytest_plugins = []
