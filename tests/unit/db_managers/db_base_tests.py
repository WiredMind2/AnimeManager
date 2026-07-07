"""
Base test class for database manager plugins.

This module provides a comprehensive test suite that can be used to test
any database manager plugin that inherits from BaseDB. It tests all the
core functionality that should be consistent across all implementations.
"""

import os
import sys
import tempfile
import unittest
from abc import ABC, abstractmethod
from typing import Any, Dict, List

import pytest

# Add parent directory to path to import AnimeManager modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

try:
    from adapters.persistence.models import Anime, AnimeList, Character, NoneDict
except ImportError:
    # If relative imports fail, try importing from parent module
    try:
        import sys

        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        from adapters.persistence.models import Anime, AnimeList, Character, NoneDict
    except ImportError:
        # Create mock classes for testing if imports fail
        class Anime:
            pass

        class Character:
            pass

        class NoneDict(dict):
            pass

        class AnimeList:
            pass


class DBTestBase(ABC):
    """
    Base test class for database manager plugins.

    This class should be mixed with unittest.TestCase to create tests for
    specific database implementations. It provides comprehensive tests for
    all the core database operations that should work consistently across
    all database manager plugins.
    """

    @abstractmethod
    def get_db_instance(self) -> "BaseDB":
        """
        Return a fresh database instance for testing.

        This method should be implemented by each specific database test class
        to return an instance of the database manager being tested.

        Returns:
            BaseDB: A fresh database instance ready for testing
        """
        pass

    @abstractmethod
    def cleanup_db(self):
        """
        Clean up database resources after testing.

        This method should be implemented to properly clean up any database
        resources, temporary files, or connections created during testing.
        """
        pass

    def setUp(self):
        """Set up test environment before each test."""
        self.db = self.get_db_instance()

        # Test data for various operations
        self.test_anime_data = {
            "id": 1,
            "title": "Test Anime",
            "synopsis": "A test anime for unit testing",
            "episodes": 12,
            "duration": 24,
            "rating": "PG-13",
            "status": "finished",
            "date_from": 1640995200,  # 2022-01-01
            "date_to": 1648771200,  # 2022-04-01
        }

        self.test_character_data = {
            "id": 1,
            "name": "Test Character",
            "description": "A test character for unit testing",
        }

        self.test_relation_data = {
            "id": 1,
            "type": "sequel",
            "name": "Test Sequel",
            "rel_id": 2,
        }

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(self, "db") and self.db:
            try:
                # Clean up test data
                with self.db:
                    self.db.sql("DELETE FROM anime WHERE id IN (1, 2, 3)", save=True)
                    self.db.sql(
                        "DELETE FROM characters WHERE id IN (1, 2, 3)", save=True
                    )
                    self.db.sql(
                        "DELETE FROM animeRelations WHERE id IN (1, 2, 3)", save=True
                    )
            except Exception:
                pass  # Ignore cleanup errors

            self.cleanup_db()

    @pytest.mark.timeout(30)
    def test_database_initialization(self):
        """Test that the database can be initialized properly."""
        self.assertIsNotNone(self.db, "Database instance should not be None")
        self.assertTrue(
            self.db.is_initialized(), "Database should be properly initialized"
        )

    @pytest.mark.timeout(30)
    def test_context_manager(self):
        """Test that the database can be used as a context manager."""
        with self.db as db_context:
            self.assertIsNotNone(
                db_context, "Context manager should return a valid object"
            )
            # Should be able to execute SQL within context
            result = db_context.sql("SELECT 1 as test_value")
            self.assertIsNotNone(
                result, "Should be able to execute SQL in context manager"
            )

    @pytest.mark.timeout(30)
    def test_sql_execution(self):
        """Test basic SQL execution functionality."""
        # Test simple query
        result = self.db.sql("SELECT 1 as test_value")
        self.assertIsNotNone(result, "SQL execution should return a result")

        # Test parameterized query (if supported)
        try:
            result = self.db.sql("SELECT ? as param_value", [42])
            self.assertIsNotNone(result, "Parameterized queries should work")
        except NotImplementedError:
            pass  # Some implementations might not support this syntax

    @pytest.mark.timeout(30)
    def test_insert_operations(self):
        """Test data insertion operations."""
        with self.db:
            # Insert anime data
            success = self.db.insert(self.test_anime_data, "anime", save=True)

            # Verify insertion
            result = self.db.get(1, "anime")
            self.assertIsNotNone(result, "Inserted anime should be retrievable")

            if result:
                # Check that key fields match
                self.assertEqual(result.get("id") or result.get("ID"), 1)
                self.assertEqual(
                    result.get("title") or result.get("TITLE"), "Test Anime"
                )

    @pytest.mark.timeout(30)
    def test_get_operations(self):
        """Test data retrieval operations."""
        with self.db:
            # Insert test data first
            self.db.insert(self.test_anime_data, "anime", save=True)

            # Test get by single ID
            result = self.db.get(1, "anime")
            self.assertIsNotNone(result, "Should be able to retrieve by single ID")

            # Test get by list of IDs
            try:
                results = self.db.get([1], "anime")
                self.assertIsNotNone(results, "Should be able to retrieve by ID list")
            except (NotImplementedError, Exception):
                pass  # Some implementations might not support this

    @pytest.mark.timeout(30)
    def test_exists_operations(self):
        """Test existence checking operations."""
        with self.db:
            # Insert test data first
            self.db.insert(self.test_anime_data, "anime", save=True)

            # Test exists for existing record
            exists = self.db.exists(1, "anime")
            self.assertTrue(exists, "Should detect existing record")

            # Test exists for non-existing record
            exists = self.db.exists(999, "anime")
            self.assertFalse(exists, "Should detect non-existing record")

    @pytest.mark.timeout(30)
    def test_update_operations(self):
        """Test data update operations."""
        with self.db:
            # Insert test data first
            self.db.insert(self.test_anime_data, "anime", save=True)

            # Update the data
            update_data = {"title": "Updated Test Anime", "episodes": 24}
            self.db.update(1, update_data, "anime", save=True)

            # Verify update
            result = self.db.get(1, "anime")
            self.assertIsNotNone(result, "Updated record should still exist")

            if result:
                updated_title = result.get("title") or result.get("TITLE")
                updated_episodes = result.get("episodes") or result.get("EPISODES")
                self.assertEqual(updated_title, "Updated Test Anime")
                self.assertEqual(updated_episodes, 24)

    @pytest.mark.timeout(30)
    def test_set_operations(self):
        """Test set operations (insert or update)."""
        with self.db:
            # Test set for new record (should insert)
            self.db.set(2, self.test_anime_data.copy(), "anime", save=True)

            # Verify insertion
            result = self.db.get(2, "anime")
            self.assertIsNotNone(result, "Set should insert new record")

            # Test set for existing record (should update)
            update_data = self.test_anime_data.copy()
            update_data["title"] = "Set Updated Anime"
            self.db.set(2, update_data, "anime", save=True)

            # Verify update
            result = self.db.get(2, "anime")
            if result:
                updated_title = result.get("title") or result.get("TITLE")
                self.assertEqual(updated_title, "Set Updated Anime")

    @pytest.mark.timeout(30)
    def test_remove_operations(self):
        """Test data removal operations."""
        with self.db:
            # Insert test data first
            self.db.insert(self.test_anime_data, "anime", save=True)

            # Verify it exists
            self.assertTrue(
                self.db.exists(1, "anime"), "Record should exist before removal"
            )

            # Remove the record
            self.db.remove(1, "anime", save=True)

            # Verify removal
            self.assertFalse(
                self.db.exists(1, "anime"), "Record should not exist after removal"
            )

    @pytest.mark.timeout(30)
    def test_transaction_behavior(self):
        """Test transaction behavior with save parameter."""
        with self.db:
            # Insert without save
            self.db.insert(self.test_anime_data, "anime", save=False)

            # Check if it's immediately available (depends on implementation)
            # Note: This test might behave differently for different databases
            try:
                result = self.db.get(1, "anime")
                # If auto-commit is on, it should be available
                # If transactions are used properly, it might not be
            except Exception:
                pass  # Acceptable, depending on transaction implementation

            # Save and verify
            self.db.save()
            result = self.db.get(1, "anime")
            self.assertIsNotNone(result, "Record should be available after save")

    @pytest.mark.timeout(30)
    def test_sql_to_dict_conversion(self):
        """Test SQL result to dictionary conversion."""
        with self.db:
            # Insert test data
            self.db.insert(self.test_anime_data, "anime", save=True)

            # Query with to_dict=True
            result = self.db.sql("SELECT * FROM anime WHERE id = ?", [1], to_dict=True)

            if result:
                self.assertIsInstance(result, list, "to_dict should return a list")
                if len(result) > 0:
                    row = result[0]
                    self.assertIsInstance(row, dict, "Each row should be a dictionary")
                    # Check that it has the expected keys
                    keys = [k.lower() for k in row.keys()]
                    self.assertIn("id", keys, "Should have id field")
                    self.assertIn("title", keys, "Should have title field")

    @pytest.mark.timeout(30)
    def test_error_handling(self):
        """Test error handling for invalid operations."""
        with self.db:
            # Test invalid table name
            with self.assertRaises(Exception):
                self.db.get(1, "invalid_table_name")

            # Test invalid SQL
            with self.assertRaises(Exception):
                self.db.sql("INVALID SQL SYNTAX")

    @pytest.mark.timeout(30)
    def test_thread_safety_basic(self):
        """Test basic thread safety properties."""
        # Check if database claims to be thread safe
        thread_safe = getattr(self.db, "THREAD_SAFE", False)

        if not thread_safe:
            # Should have a lock attribute
            self.assertTrue(
                hasattr(self.db, "lock"),
                "Non-thread-safe databases should have a lock attribute",
            )

        # Test context manager works (even if not thread safe)
        with self.db:
            result = self.db.sql("SELECT 1")
            self.assertIsNotNone(result)

    @pytest.mark.timeout(30)
    def test_procedures_if_supported(self):
        """Test stored procedures if the database supports them."""
        try:
            # Check if procedures are supported
            procedures_supported = getattr(self.db, "procedures_supported", False)

            if procedures_supported:
                # This is implementation-specific, so we just check the method exists
                self.assertTrue(
                    hasattr(self.db, "procedure"),
                    "Database claims to support procedures but has no procedure method",
                )
            else:
                # If not supported, procedure method should raise NotImplementedError
                with self.assertRaises(NotImplementedError):
                    self.db.procedure("test_proc")
        except AttributeError:
            # procedures_supported attribute doesn't exist, that's fine
            pass

    @pytest.mark.timeout(30)
    def test_metadata_operations_if_supported(self):
        """Test metadata operations if supported by the database."""
        try:
            # Insert test anime first
            with self.db:
                self.db.insert(self.test_anime_data, "anime", save=True)

                # Test metadata operations if they exist
                if hasattr(self.db, "get_metadata"):
                    # This might return None for non-existent metadata
                    metadata = self.db.get_metadata(1, "test_key")
                    # Just ensure it doesn't crash

                if hasattr(self.db, "save_metadata"):
                    # Test saving metadata
                    test_metadata = {"test_key": "test_value"}
                    self.db.save_metadata(1, test_metadata)
                    # Just ensure it doesn't crash

        except NotImplementedError:
            # Metadata operations not implemented, that's fine
            pass

    @pytest.mark.timeout(30)
    def test_filter_operations_if_supported(self):
        """Test filter operations if supported by the database."""
        try:
            with self.db:
                # Insert some test data
                for i in range(3):
                    data = self.test_anime_data.copy()
                    data["id"] = i + 1
                    data["title"] = f"Test Anime {i + 1}"
                    self.db.insert(data, "anime", save=True)

                # Test filter if it exists
                if hasattr(self.db, "filter"):
                    results = self.db.filter(table="anime", range=(0, 10))
                    # Just ensure it doesn't crash and returns something
                    self.assertIsNotNone(results)

        except NotImplementedError:
            # Filter operations not implemented, that's fine
            pass


class DBIntegrationTestBase(ABC):
    """
    Integration test class for database managers.

    This class tests how the database manager integrates with the broader
    application, including complex data relationships and real-world usage patterns.
    """

    @abstractmethod
    def get_db_instance(self) -> "BaseDB":
        """Return a database instance for integration testing."""
        pass

    @abstractmethod
    def cleanup_db(self):
        """Clean up database resources after testing."""
        pass

    def setUp(self):
        """Set up integration test environment."""
        self.db = self.get_db_instance()

        # More complex test data for integration testing
        self.anime_with_relations = {
            "id": 1,
            "title": "Main Anime",
            "synopsis": "Main anime for testing relations",
            "episodes": 12,
            "status": "finished",
        }

        self.related_anime = {
            "id": 2,
            "title": "Sequel Anime",
            "synopsis": "Sequel to main anime",
            "episodes": 12,
            "status": "finished",
        }

        self.character_data = {
            "id": 1,
            "name": "Main Character",
            "description": "Main character of the anime",
        }

    def tearDown(self):
        """Clean up after integration tests."""
        if hasattr(self, "db") and self.db:
            try:
                with self.db:
                    # Clean up all test data
                    self.db.sql(
                        "DELETE FROM characterRelations WHERE anime_id IN (1, 2)",
                        save=True,
                    )
                    self.db.sql(
                        "DELETE FROM animeRelations WHERE id IN (1, 2)", save=True
                    )
                    self.db.sql("DELETE FROM characters WHERE id IN (1, 2)", save=True)
                    self.db.sql("DELETE FROM anime WHERE id IN (1, 2)", save=True)
            except Exception:
                pass

            self.cleanup_db()

    @pytest.mark.timeout(30)
    def test_complex_data_insertion(self):
        """Test insertion of related data across multiple tables."""
        with self.db:
            # Insert main anime
            self.db.insert(self.anime_with_relations, "anime", save=True)

            # Insert related anime
            self.db.insert(self.related_anime, "anime", save=True)

            # Insert character
            self.db.insert(self.character_data, "characters", save=True)

            # Insert anime relation
            relation_data = {"id": 1, "type": "sequel", "name": "Sequel", "rel_id": 2}
            self.db.insert(relation_data, "animeRelations", save=True)

            # Insert character relation
            char_relation_data = {"id": 1, "anime_id": 1, "role": "main"}
            self.db.insert(char_relation_data, "characterRelations", save=True)

            # Verify all data was inserted correctly
            anime = self.db.get(1, "anime")
            self.assertIsNotNone(anime, "Main anime should be inserted")

            related = self.db.get(2, "anime")
            self.assertIsNotNone(related, "Related anime should be inserted")

            character = self.db.get(1, "characters")
            self.assertIsNotNone(character, "Character should be inserted")

    @pytest.mark.timeout(30)
    def test_data_consistency(self):
        """Test data consistency across operations."""
        with self.db:
            # Insert initial data
            self.db.insert(self.anime_with_relations, "anime", save=True)

            # Update and verify consistency
            update_data = {"title": "Updated Main Anime", "episodes": 24}
            self.db.update(1, update_data, "anime", save=True)

            # Retrieve and verify update
            result = self.db.get(1, "anime")
            self.assertIsNotNone(result)

            if result:
                title = result.get("title") or result.get("TITLE")
                episodes = result.get("episodes") or result.get("EPISODES")
                self.assertEqual(title, "Updated Main Anime")
                self.assertEqual(episodes, 24)

    @pytest.mark.timeout(30)
    def test_large_dataset_operations(self):
        """Test operations with a larger dataset."""
        with self.db:
            # Insert multiple records
            batch_size = 10

            for i in range(batch_size):
                anime_data = {
                    "id": i + 10,  # Start from 10 to avoid conflicts
                    "title": f"Batch Anime {i}",
                    "episodes": 12 + i,
                    "status": "finished" if i % 2 == 0 else "ongoing",
                }
                self.db.insert(anime_data, "anime", save=False)

            # Save all at once
            self.db.save()

            # Verify all records exist
            for i in range(batch_size):
                result = self.db.get(i + 10, "anime")
                self.assertIsNotNone(result, f"Batch record {i} should exist")

            # Clean up batch data
            for i in range(batch_size):
                self.db.remove(i + 10, "anime", save=False)
            self.db.save()
