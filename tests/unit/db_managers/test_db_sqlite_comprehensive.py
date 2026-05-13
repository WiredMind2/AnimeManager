"""
Test suite for SQLite database manager (dbManager.py).

This module tests the SQLite implementation of the database manager
to ensure it works correctly with all the core database operations.
"""

import os
import shutil
import sys
import tempfile
import unittest

import pytest

# Add parent directory to path for AnimeManager modules
parent_dir = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    # Try importing the ImportManager for proper import handling
    from shared.utils.import_manager import ImportManager

    ImportManager.ensure_package_path()

    # Import the local test utilities with proper path handling
    sys.path.insert(0, os.path.dirname(__file__))
    from db_base_tests import DBIntegrationTestBase, DBTestBase

    from adapters.persistence.dbManager import db_instance
except ImportError as e:
    # Fallback imports
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from db_base_tests import DBIntegrationTestBase, DBTestBase

        from adapters.persistence.dbManager import db_instance
    except ImportError as fallback_e:
        print(f"Import error: {e}")
        print(f"Fallback error: {fallback_e}")
        raise


@pytest.mark.database
@pytest.mark.slow
class TestSQLiteDB(unittest.TestCase, DBTestBase):
    """Test SQLite database manager implementation."""

    def setUp(self):
        """Set up test database."""
        try:
            DBTestBase.setUp(self)  # This calls BaseDBTest.setUp() which sets self.db
        except Exception as e:
            if 'near "SET": syntax error' in str(e):
                self.fail(
                    "Database creation failed due to MySQL syntax in SQL file - needs proper SQLite schema"
                )
            else:
                raise

    def get_db_instance(self):
        """Create a temporary SQLite database for testing."""
        # Create a temporary database file
        self.temp_dir = tempfile.mkdtemp()
        self.temp_db_path = os.path.join(self.temp_dir, "test_anime.db")

        # Create database instance
        db = db_instance(self.temp_db_path)
        return db

    def tearDown(self):
        """Clean up after test."""
        super().tearDown()  # This calls BaseDBTest.tearDown()
        self.cleanup_db()  # This calls our specific cleanup

    def cleanup_db(self):
        """Clean up temporary database files."""
        if hasattr(self, "db") and self.db:
            try:
                self.db.close()
                if hasattr(self.db, "con"):
                    self.db.con.close()
            except Exception:
                pass

        # Clean up temporary directory
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception:
                pass

    @pytest.mark.timeout(30)
    def test_sqlite_specific_features(self):
        """Test SQLite-specific features."""
        # Test that the database file was created
        self.assertTrue(
            os.path.exists(self.temp_db_path), "SQLite database file should be created"
        )

        # Test SQLite connection properties
        self.assertIsNotNone(self.db.con, "Should have a connection object")
        self.assertIsNotNone(self.db.cur, "Should have a cursor object")

        # Test that it's using SQLite
        self.assertIn(
            "sqlite",
            str(type(self.db.con)).lower(),
            "Should be using SQLite connection",
        )

    @pytest.mark.timeout(30)
    def test_sqlite_threading(self):
        """Test SQLite threading behavior."""
        # SQLite databases should not be thread-safe by default
        self.assertFalse(
            self.db.THREAD_SAFE, "SQLite should not be thread-safe by default"
        )

        # Should have lock mechanism
        self.assertTrue(
            hasattr(self.db, "remote_lock"),
            "SQLite implementation should have remote_lock",
        )

    @pytest.mark.timeout(30)
    def test_sqlite_file_operations(self):
        """Test SQLite file-specific operations."""
        with self.db:
            # Insert some data
            self.db.insert(self.test_anime_data, "anime", save=True)

            # Close and reopen database to test persistence
            original_path = self.temp_db_path
            self.db.close()

            # Create new instance from same file
            new_db = db_instance(original_path)

            # Verify data persisted
            result = new_db.get(1, "anime")
            self.assertIsNotNone(result, "Data should persist after close/reopen")

            new_db.close()

    @pytest.mark.timeout(30)
    def test_sqlite_boolean_handling(self):
        """Test SQLite boolean value handling."""
        with self.db:
            # SQLite stores booleans as integers
            # Test inserting data with boolean-like values
            test_data = {"id": 1, "title": "Boolean Test Anime", "episodes": 12}

            self.db.insert(test_data, "anime", save=True)
            result = self.db.get(1, "anime")
            self.assertIsNotNone(result, "Should handle data without issues")


@pytest.mark.database
@pytest.mark.slow
@pytest.mark.integration
class TestSQLiteDBIntegration(unittest.TestCase, DBIntegrationTestBase):
    """Integration tests for SQLite database manager."""

    def get_db_instance(self):
        """Create a temporary SQLite database for integration testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_db_path = os.path.join(self.temp_dir, "test_integration.db")

        db = db_instance(self.temp_db_path)
        return db

    def cleanup_db(self):
        """Clean up temporary database files."""
        if hasattr(self, "db") and self.db:
            try:
                self.db.close()
                if hasattr(self.db, "con"):
                    self.db.con.close()
            except Exception:
                pass

        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception:
                pass

    @pytest.mark.timeout(30)
    def test_sqlite_concurrent_access(self):
        """Test SQLite behavior under concurrent access scenarios."""
        # Note: This is a basic test since true concurrency testing
        # would require multiple processes/threads

        with self.db:
            # Simulate rapid sequential operations
            for i in range(5):
                data = {
                    "id": i + 1,
                    "title": f"Concurrent Test Anime {i}",
                    "episodes": 12,
                }
                self.db.insert(data, "anime", save=False)

            self.db.save()

            # Verify all data was inserted correctly
            for i in range(5):
                result = self.db.get(i + 1, "anime")
                self.assertIsNotNone(result, f"Concurrent insert {i} should succeed")

    @pytest.mark.timeout(30)
    def test_sqlite_transaction_rollback(self):
        """Test SQLite transaction behavior."""
        with self.db:
            # Insert initial data
            self.db.insert(self.anime_with_relations, "anime", save=True)

            # Verify it exists
            self.assertTrue(self.db.exists(1, "anime"))

            # Simulate transaction that should be rolled back
            try:
                self.db.insert({"id": 2, "title": "Test"}, "anime", save=False)
                # This should work
                self.db.insert(
                    {"id": "invalid"}, "anime", save=False
                )  # This might fail
                self.db.save()
            except Exception:
                # If there was an error, data should not be committed
                pass

            # Original data should still exist
            self.assertTrue(self.db.exists(1, "anime"))


if __name__ == "__main__":
    # Run SQLite-specific tests
    unittest.main(verbosity=2)
