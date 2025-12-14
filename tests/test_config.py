"""
Test Configuration and Utilities

This module provides test configuration and utility functions for the AnimeManager test suite.
"""

import os
import tempfile
import pytest
from pathlib import Path


# Test configuration
class TestConfig:
    """Global test configuration."""

    # Test data directories
    TEST_DATA_DIR = Path(__file__).parent / "test_data"
    FIXTURES_DIR = Path(__file__).parent / "fixtures"

    # Test timeouts (seconds)
    UNIT_TEST_TIMEOUT = 30
    INTEGRATION_TEST_TIMEOUT = 60
    E2E_TEST_TIMEOUT = 300
    PERFORMANCE_TEST_TIMEOUT = 120

    # Coverage requirements
    MIN_COVERAGE_PERCENT = 85

    # Performance thresholds
    MAX_RESPONSE_TIME_MS = 1000
    MAX_MEMORY_USAGE_MB = 500
    MAX_CPU_USAGE_PERCENT = 80

    # Security test settings
    SECURITY_SCAN_TIMEOUT = 300
    VULNERABILITY_THRESHOLD = 5  # Max acceptable vulnerabilities

    # GUI test settings
    GUI_TEST_TIMEOUT = 60
    SCREENSHOT_DIFF_THRESHOLD = 0.99

    # Database test settings
    DB_TEST_TIMEOUT = 30
    MAX_DB_CONNECTIONS = 10

    # API test settings
    API_TEST_TIMEOUT = 30
    MAX_API_RETRIES = 3


@pytest.fixture(scope="session")
def test_config():
    """Provide test configuration to all tests."""
    return TestConfig()


@pytest.fixture(scope="function")
def temp_directory():
    """Create a temporary directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def mock_database():
    """Provide a mock database for testing."""
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    mock_db.is_initialized.return_value = True
    mock_db.connect.return_value = True
    mock_db.close.return_value = True

    # Mock common database operations
    mock_db.get_anime.return_value = {"id": 1, "title": "Test Anime"}
    mock_db.save_anime.return_value = 1
    mock_db.search.return_value = [{"id": 1, "title": "Test Anime"}]

    return mock_db


@pytest.fixture(scope="function")
def mock_api_client():
    """Provide a mock API client for testing."""
    from unittest.mock import AsyncMock

    mock_api = AsyncMock()
    mock_api.search.return_value = [{"id": 1, "title": "Test Anime"}]
    mock_api.get_details.return_value = {
        "id": 1,
        "title": "Test Anime",
        "episodes": 12,
        "status": "finished"
    }

    return mock_api


@pytest.fixture(scope="function")
def mock_file_manager():
    """Provide a mock file manager for testing."""
    from unittest.mock import MagicMock

    mock_fm = MagicMock()
    mock_fm.exists.return_value = True
    mock_fm.list.return_value = ["file1.mp4", "file2.mp4"]
    mock_fm.mkdir.return_value = True

    return mock_fm


@pytest.fixture(scope="function")
def mock_torrent_manager():
    """Provide a mock torrent manager for testing."""
    from unittest.mock import AsyncMock

    mock_tm = AsyncMock()
    mock_tm.download.return_value = True
    mock_tm.get_status.return_value = {"progress": 100, "status": "completed"}

    return mock_tm


@pytest.fixture(scope="function")
def sample_anime_data():
    """Provide sample anime data for testing."""
    return {
        "id": 1,
        "title": "Test Anime",
        "synopsis": "A test anime for testing purposes",
        "episodes": 12,
        "status": "finished",
        "score": 8.5,
        "genres": ["Action", "Adventure"],
        "studios": ["Test Studio"]
    }


@pytest.fixture(scope="function")
def sample_user_data():
    """Provide sample user data for testing."""
    return {
        "id": 1,
        "username": "testuser",
        "email": "test@example.com",
        "password_hash": "hashed_password",
        "preferences": {
            "theme": "dark",
            "notifications": True
        }
    }


# Test utilities
class TestUtils:
    """Utility functions for tests."""

    @staticmethod
    def create_test_file(directory, filename, content="test content"):
        """Create a test file with specified content."""
        filepath = os.path.join(directory, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return filepath

    @staticmethod
    def create_test_directory(base_dir, dirname):
        """Create a test directory."""
        dirpath = os.path.join(base_dir, dirname)
        os.makedirs(dirpath, exist_ok=True)
        return dirpath

    @staticmethod
    def assert_file_exists(filepath):
        """Assert that a file exists."""
        assert os.path.exists(filepath), f"File does not exist: {filepath}"

    @staticmethod
    def assert_directory_exists(dirpath):
        """Assert that a directory exists."""
        assert os.path.exists(dirpath), f"Directory does not exist: {dirpath}"
        assert os.path.isdir(dirpath), f"Path is not a directory: {dirpath}"

    @staticmethod
    def assert_performance_threshold(actual_time, max_time, operation_name="operation"):
        """Assert that operation completes within time threshold."""
        assert actual_time <= max_time, (
            f"{operation_name} took {actual_time:.3f}s, exceeding limit of {max_time:.3f}s"
        )

    @staticmethod
    def assert_memory_usage(max_mb=100):
        """Assert that memory usage is within limits."""
        import psutil
        process = psutil.Process()
        memory_mb = process.memory_info().rss / (1024 * 1024)
        assert memory_mb <= max_mb, f"Memory usage {memory_mb:.1f}MB exceeds limit of {max_mb}MB"

    @staticmethod
    def assert_no_exceptions(func, *args, **kwargs):
        """Assert that function executes without exceptions."""
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            pytest.fail(f"Function raised unexpected exception: {e}")


# Export utilities
__all__ = [
    'TestConfig',
    'TestUtils',
    'test_config',
    'temp_directory',
    'mock_database',
    'mock_api_client',
    'mock_file_manager',
    'mock_torrent_manager',
    'sample_anime_data',
    'sample_user_data'
]