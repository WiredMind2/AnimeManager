"""
Test configuration and utilities for database manager tests.

This module provides configuration, mock data, and utility functions
that are shared across all database manager tests.
"""

import os
import shutil
import tempfile
from typing import Any, Dict, List


class TestConfig:
    """Configuration settings for database tests."""

    # SQLite test settings
    SQLITE_TEST_DB_NAME = "test_anime.db"

    # MySQL test settings (can be overridden by environment variables)
    MYSQL_TEST_SETTINGS = {
        "host": os.getenv("TEST_MYSQL_HOST", "localhost"),
        "user": os.getenv("TEST_MYSQL_USER", "test"),
        "password": os.getenv("TEST_MYSQL_PASSWORD", "test"),
        "database": os.getenv("TEST_MYSQL_DATABASE", "test_anime_manager"),
    }

    # Embedded MariaDB test settings
    MARIADB_TEST_SETTINGS = {
        "port": int(os.getenv("TEST_MARIADB_PORT", "3307")),
        "user": os.getenv("TEST_MARIADB_USER", "testuser"),
        "password": os.getenv("TEST_MARIADB_PASSWORD", "testpass"),
        "database": os.getenv("TEST_MARIADB_DATABASE", "test_anime_db"),
    }

    # Test timeouts (in seconds)
    CONNECTION_TIMEOUT = 30
    QUERY_TIMEOUT = 10
    BATCH_OPERATION_TIMEOUT = 60

    # Test data limits
    MAX_BATCH_SIZE = 100
    PERFORMANCE_TEST_SIZE = 50


class TestDataFactory:
    """Factory for creating test data objects."""

    @staticmethod
    def create_anime_data(id: int = 1, **overrides) -> Dict[str, Any]:
        """Create anime test data with optional overrides."""
        data = {
            "id": id,
            "title": f"Test Anime {id}",
            "synopsis": f"Test synopsis for anime {id}",
            "episodes": 12,
            "duration": 24,
            "rating": "PG-13",
            "status": "finished",
            "date_from": 1640995200,  # 2022-01-01
            "date_to": 1648771200,  # 2022-04-01
            "picture": f"https://example.com/anime{id}.jpg",
            "trailer": f"https://example.com/trailer{id}.mp4",
        }
        data.update(overrides)
        return data

    @staticmethod
    def create_character_data(id: int = 1, **overrides) -> Dict[str, Any]:
        """Create character test data with optional overrides."""
        data = {
            "id": id,
            "name": f"Test Character {id}",
            "description": f"Test description for character {id}",
            "picture": f"https://example.com/character{id}.jpg",
        }
        data.update(overrides)
        return data

    @staticmethod
    def create_anime_relation_data(
        id: int = 1, rel_id: int = 2, **overrides
    ) -> Dict[str, Any]:
        """Create anime relation test data with optional overrides."""
        data = {
            "id": id,
            "type": "sequel",
            "name": f"Test Relation {id}",
            "rel_id": rel_id,
        }
        data.update(overrides)
        return data

    @staticmethod
    def create_character_relation_data(
        char_id: int = 1, anime_id: int = 1, **overrides
    ) -> Dict[str, Any]:
        """Create character relation test data with optional overrides."""
        data = {"id": char_id, "anime_id": anime_id, "role": "main"}
        data.update(overrides)
        return data

    @staticmethod
    def create_batch_anime_data(
        count: int = 10, start_id: int = 1
    ) -> List[Dict[str, Any]]:
        """Create a batch of anime test data."""
        return [
            TestDataFactory.create_anime_data(
                id=start_id + i,
                title=f"Batch Anime {start_id + i}",
                episodes=12 + (i % 12),
                status="finished" if i % 2 == 0 else "ongoing",
            )
            for i in range(count)
        ]

    @staticmethod
    def create_complex_test_dataset() -> Dict[str, List[Dict[str, Any]]]:
        """Create a complex dataset with related data across multiple tables."""
        # Main anime
        anime_data = [
            TestDataFactory.create_anime_data(1, title="Main Anime", status="finished"),
            TestDataFactory.create_anime_data(
                2, title="Sequel Anime", status="ongoing"
            ),
            TestDataFactory.create_anime_data(
                3, title="Prequel Anime", status="finished"
            ),
        ]

        # Characters
        character_data = [
            TestDataFactory.create_character_data(1, name="Protagonist"),
            TestDataFactory.create_character_data(2, name="Antagonist"),
            TestDataFactory.create_character_data(3, name="Side Character"),
        ]

        # Anime relations
        anime_relations = [
            TestDataFactory.create_anime_relation_data(
                1, 2, type="sequel", name="Sequel"
            ),
            TestDataFactory.create_anime_relation_data(
                1, 3, type="prequel", name="Prequel"
            ),
        ]

        # Character relations
        character_relations = [
            TestDataFactory.create_character_relation_data(1, 1, role="main"),
            TestDataFactory.create_character_relation_data(2, 1, role="main"),
            TestDataFactory.create_character_relation_data(3, 1, role="supporting"),
            TestDataFactory.create_character_relation_data(1, 2, role="main"),
            TestDataFactory.create_character_relation_data(2, 2, role="main"),
        ]

        return {
            "anime": anime_data,
            "characters": character_data,
            "animeRelations": anime_relations,
            "characterRelations": character_relations,
        }


class TestEnvironmentManager:
    """Manager for setting up and tearing down test environments."""

    def __init__(self):
        self.temp_dirs = []
        self.db_connections = []

    def create_temp_dir(self, prefix: str = "animemanager_test_") -> str:
        """Create a temporary directory for testing."""
        temp_dir = tempfile.mkdtemp(prefix=prefix)
        self.temp_dirs.append(temp_dir)
        return temp_dir

    def create_temp_db_file(self, filename: str = None) -> str:
        """Create a temporary database file."""
        if filename is None:
            filename = TestConfig.SQLITE_TEST_DB_NAME

        temp_dir = self.create_temp_dir()
        return os.path.join(temp_dir, filename)

    def register_db_connection(self, db_instance):
        """Register a database connection for cleanup."""
        self.db_connections.append(db_instance)

    def cleanup(self):
        """Clean up all test resources."""
        # Close database connections
        for db in self.db_connections:
            try:
                if hasattr(db, "close"):
                    db.close()
                if hasattr(db, "con") and db.con:
                    db.con.close()
                if hasattr(db, "db") and db.db:
                    db.db.close()
                if hasattr(db, "cur") and db.cur:
                    db.cur.close()
                # Stop embedded processes
                if hasattr(db, "process") and db.process:
                    db.process.terminate()
            except Exception:
                pass  # Ignore cleanup errors

        # Remove temporary directories
        for temp_dir in self.temp_dirs:
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except Exception:
                pass  # Ignore cleanup errors

        self.temp_dirs.clear()
        self.db_connections.clear()


class DatabaseTestUtils:
    """Utility functions for database testing."""

    @staticmethod
    def validate_anime_data(result: Dict[str, Any], expected: Dict[str, Any]) -> bool:
        """Validate that anime data matches expected values."""
        if not result:
            return False

        # Handle case-insensitive column names
        result_normalized = {k.lower(): v for k, v in result.items()}

        for key, expected_value in expected.items():
            result_value = result_normalized.get(key.lower())
            if result_value != expected_value:
                return False

        return True

    @staticmethod
    def validate_character_data(
        result: Dict[str, Any], expected: Dict[str, Any]
    ) -> bool:
        """Validate that character data matches expected values."""
        if not result:
            return False

        result_normalized = {k.lower(): v for k, v in result.items()}

        for key, expected_value in expected.items():
            result_value = result_normalized.get(key.lower())
            if result_value != expected_value:
                return False

        return True

    @staticmethod
    def check_database_tables_exist(db_instance, required_tables: List[str]) -> bool:
        """Check that all required tables exist in the database."""
        try:
            with db_instance:
                for table in required_tables:
                    # Try to query each table
                    db_instance.sql(f"SELECT 1 FROM {table} LIMIT 1")
            return True
        except Exception:
            return False

    @staticmethod
    def get_table_record_count(db_instance, table: str) -> int:
        """Get the number of records in a table."""
        try:
            with db_instance:
                result = db_instance.sql(f"SELECT COUNT(*) FROM {table}")
                if result and len(result) > 0:
                    return result[0][0]
            return 0
        except Exception:
            return -1  # Error occurred

    @staticmethod
    def clear_test_data(db_instance, test_ids: List[int]):
        """Clear test data from all tables."""
        tables = ["characterRelations", "animeRelations", "characters", "anime"]

        try:
            with db_instance:
                for table in tables:
                    if table in ["characterRelations"]:
                        # Handle tables with different ID column names
                        for test_id in test_ids:
                            db_instance.sql(
                                f"DELETE FROM {table} WHERE anime_id = ?", [test_id]
                            )
                    else:
                        # Standard id column
                        for test_id in test_ids:
                            db_instance.sql(
                                f"DELETE FROM {table} WHERE id = ?", [test_id]
                            )

                db_instance.save()
        except Exception:
            pass  # Ignore cleanup errors


# Predefined test datasets
STANDARD_TEST_IDS = list(range(1, 11))  # IDs 1-10 for standard tests
BATCH_TEST_IDS = list(range(100, 200))  # IDs 100-199 for batch tests
PERFORMANCE_TEST_IDS = list(range(1000, 1100))  # IDs 1000-1099 for performance tests

# Required database tables for testing
REQUIRED_TABLES = [
    "anime",
    "characters",
    "animeRelations",
    "characterRelations",
    "genres",
    "genresIndex",
    "pictures",
    "title_synonyms",
    "broadcasts",
    "torrents",
    "torrentsIndex",
    "indexList",
]

# Test data validation schemas
ANIME_REQUIRED_FIELDS = ["id", "title"]
CHARACTER_REQUIRED_FIELDS = ["id", "name"]
RELATION_REQUIRED_FIELDS = ["id", "type", "rel_id"]
# Test data validation schemas
ANIME_REQUIRED_FIELDS = ["id", "title"]
CHARACTER_REQUIRED_FIELDS = ["id", "name"]
RELATION_REQUIRED_FIELDS = ["id", "type", "rel_id"]


def get_config():
    """Get test configuration instance."""
    return TestConfig()
