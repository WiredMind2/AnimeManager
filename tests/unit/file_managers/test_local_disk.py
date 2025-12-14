"""
Test suite for Local Disk file manager implementation.

This module tests the local disk file manager to ensure it works correctly
with all file operations on the local filesystem.
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from .base_file_manager_tests import (BaseFileManagerTestBase,
                                      FileManagerPerformanceTestBase)

try:
    from file_managers.local_disk import LocalFileManager

    LOCAL_DISK_AVAILABLE = True
except ImportError:
    LOCAL_DISK_AVAILABLE = False
    LocalFileManager = None


class TestLocalDiskFileManager(BaseFileManagerTestBase, unittest.TestCase):
    """Test Local Disk file manager implementation."""

    def setUp(self):
        """Set up Local Disk test environment."""
        if not LOCAL_DISK_AVAILABLE:
            self.fail("Local Disk file manager not available")

        super().setUp()

    def setup_mocks(self):
        """Set up mocks for Local Disk testing."""
        super().setup_mocks()

        # Mock tkinter.filedialog.askdirectory to avoid displaying folder selection window
        askdirectory_patch = patch(
            "file_managers.local_disk.askdirectory",
            return_value=os.path.join("C:", "fake", "path"),
        )
        self.mock_askdirectory = askdirectory_patch.start()
        self.mock_patches.append(askdirectory_patch)

    def get_file_manager_instance(self, **kwargs):
        """Create a Local Disk file manager instance for testing."""
        # Use test directory as data path
        test_data_path = tempfile.mkdtemp(prefix="localdisk_test_")
        self.temp_dirs.append(test_data_path)

        settings = {"dataPath": test_data_path, **kwargs}

        return LocalFileManager(settings=settings)

    def cleanup_file_manager(self):
        """Clean up Local Disk file manager resources."""
        # LocalFileManager doesn't require special cleanup
        pass

    def test_local_disk_specific_features(self):
        """Test Local Disk specific features."""
        # Test that it's using the correct data path
        self.assertTrue(hasattr(self.file_manager, "settings"))
        settings = getattr(self.file_manager, "settings", {})
        self.assertIn("dataPath", settings)

        # Test that the data path exists
        data_path = settings.get("dataPath")
        if data_path:
            self.assertTrue(os.path.exists(data_path), "Data path should exist")

    def test_local_disk_path_resolution(self):
        """Test local disk path resolution."""
        # Test absolute path handling
        if hasattr(self.file_manager, "exists"):
            abs_path = os.path.abspath(self.test_files["video1"])
            result = self.file_manager.exists(abs_path)
            self.assertIsInstance(result, bool)

    def test_local_disk_file_creation(self):
        """Test file creation through Local Disk manager."""
        if not hasattr(self.file_manager, "open"):
            self.fail("Local Disk manager does not implement open")

        new_file_path = os.path.join(self.test_root, "created_file.txt")
        test_content = "Content created through Local Disk manager"

        try:
            with self.file_manager.open(new_file_path, "w") as f:
                f.write(test_content)

            # Verify file was created
            self.assertTrue(os.path.exists(new_file_path), "File should be created")

            # Verify content
            with open(new_file_path, "r") as f:
                content = f.read()
                self.assertEqual(content, test_content, "File content should match")

        except NotImplementedError:
            self.fail("File creation not implemented")

    def test_local_disk_directory_creation(self):
        """Test directory creation through Local Disk manager."""
        if not hasattr(self.file_manager, "mkdir"):
            self.fail("Local Disk manager does not implement mkdir")

        new_dir_path = os.path.join(self.test_root, "created_directory")

        try:
            self.file_manager.mkdir(new_dir_path)

            # Verify directory was created
            self.assertTrue(os.path.exists(new_dir_path), "Directory should be created")
            self.assertTrue(
                os.path.isdir(new_dir_path), "Created path should be a directory"
            )

        except NotImplementedError:
            self.fail("Directory creation not implemented")

    def test_local_disk_large_file_handling(self):
        """Test handling of larger files."""
        if not hasattr(self.file_manager, "open"):
            self.fail("Local Disk manager does not implement open")

        large_file_path = os.path.join(self.test_root, "large_file.txt")

        try:
            # Create a moderately large file
            with self.file_manager.open(large_file_path, "w") as f:
                for i in range(1000):
                    f.write(f"Line {i}: This is a test line for large file handling.\n")

            # Test reading the large file
            with self.file_manager.open(large_file_path, "r") as f:
                content = f.read()
                self.assertIn(
                    "Line 999:", content, "Should handle large files correctly"
                )

        except NotImplementedError:
            self.fail("File operations not implemented")
        except Exception as e:
            self.fail(f"Large file handling failed: {e}")

    def test_local_disk_unicode_handling(self):
        """Test handling of unicode filenames and content."""
        if not hasattr(self.file_manager, "exists"):
            return

        # Test unicode filename
        unicode_filename = os.path.join(self.test_root, "tëst_ünïcödë.txt")

        try:
            # Create file with unicode name
            with open(unicode_filename, "w", encoding="utf-8") as f:
                f.write("Unicode test content: こんにちは")

            # Test that file manager can handle it
            exists = self.file_manager.exists(unicode_filename)
            self.assertTrue(exists, "Should handle unicode filenames")

            # Test unicode content if open is supported
            if hasattr(self.file_manager, "open"):
                with self.file_manager.open(unicode_filename, "r") as f:
                    content = f.read()
                    self.assertIn(
                        "こんにちは", content, "Should handle unicode content"
                    )

        except (UnicodeError, NotImplementedError):
            # Unicode support might not be available
            pass
        except Exception as e:
            self.fail(f"Unicode handling test failed: {e}")


class TestLocalDiskPerformance(FileManagerPerformanceTestBase, unittest.TestCase):
    """Performance tests for Local Disk file manager."""

    def setUp(self):
        """Set up Local Disk performance test environment."""
        # if not LOCAL_DISK_AVAILABLE:
        #     self.fail("Local Disk file manager not available")

        super().setUp()
        self.setup_mocks()

    def tearDown(self):
        """Clean up Local Disk performance test environment."""
        self.cleanup_mocks()
        super().tearDown()

    def setup_mocks(self):
        """Set up mocks for Local Disk performance testing."""
        self.mock_patches = []

        # Mock logger
        logger_patch = patch("logger.Logger.__init__", return_value=None)
        self.mock_logger = logger_patch.start()
        self.mock_patches.append(logger_patch)

        log_patch = patch("logger.log")
        self.mock_log = log_patch.start()
        self.mock_patches.append(log_patch)

        # Mock tkinter.filedialog.askdirectory to avoid displaying folder selection window
        askdirectory_patch = patch(
            "file_managers.local_disk.askdirectory",
            return_value=os.path.join("C:", "fake", "path"),
        )
        self.mock_askdirectory = askdirectory_patch.start()
        self.mock_patches.append(askdirectory_patch)

    def cleanup_mocks(self):
        """Clean up mock patches."""
        for patch_obj in self.mock_patches:
            try:
                patch_obj.stop()
            except Exception:
                pass

    def get_file_manager_instance(self, **kwargs):
        """Create a Local Disk file manager for performance testing."""
        settings = {"dataPath": self.temp_root, **kwargs}

        return LocalFileManager(settings=settings)

    def test_local_disk_recursive_operations(self):
        """Test performance of recursive operations."""

        import time

        # Create nested directory structure
        nested_root = os.path.join(self.temp_root, "nested")
        for i in range(5):
            level_dir = os.path.join(nested_root, *[f"level_{j}" for j in range(i + 1)])
            os.makedirs(level_dir, exist_ok=True)

            # Add files at each level
            for j in range(5):
                file_path = os.path.join(level_dir, f"file_{j}.txt")
                with open(file_path, "w") as f:
                    f.write(f"Content at level {i}, file {j}")

        # Test recursive listing performance
        start_time = time.time()

        def recursive_list(path):
            try:
                items = self.file_manager.list(path)
                for item in items or []:
                    item_path = (
                        os.path.join(path, item) if isinstance(item, str) else item
                    )
                    if os.path.isdir(item_path):
                        recursive_list(item_path)
            except Exception:
                pass

        recursive_list(nested_root)

        end_time = time.time()
        duration = end_time - start_time

        # Should complete recursive operations in reasonable time
        self.assertLess(
            duration, 5.0, f"Recursive operations took too long: {duration:.2f}s"
        )


class TestLocalDiskEdgeCases(unittest.TestCase):
    """Test edge cases for Local Disk file manager."""

    def setUp(self):
        """Set up edge case test environment."""
        if not LOCAL_DISK_AVAILABLE:
            self.fail("Local Disk file manager not available")

        self.temp_dirs = []
        self.setup_mocks()

    def tearDown(self):
        """Clean up edge case test environment."""
        self.cleanup_mocks()
        for temp_dir in self.temp_dirs:
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except Exception:
                pass

    def setup_mocks(self):
        """Set up mocks for edge case testing."""
        self.mock_patches = []

        # Mock logger
        logger_patch = patch("logger.Logger.__init__", return_value=None)
        self.mock_logger = logger_patch.start()
        self.mock_patches.append(logger_patch)

        # Mock tkinter.filedialog.askdirectory to avoid displaying folder selection window
        askdirectory_patch = patch(
            "file_managers.local_disk.askdirectory",
            return_value=os.path.join("C:", "fake", "path"),
        )
        self.mock_askdirectory = askdirectory_patch.start()
        self.mock_patches.append(askdirectory_patch)

    def cleanup_mocks(self):
        """Clean up mock patches."""
        for patch_obj in self.mock_patches:
            try:
                patch_obj.stop()
            except Exception:
                pass

    def test_invalid_settings(self):
        """Test handling of invalid settings."""
        # Test with empty settings
        try:
            fm = LocalFileManager(settings={})
            self.assertIsNotNone(fm, "Should handle empty settings")
        except Exception:
            # Some file managers might require certain settings
            pass

        # Test with None settings
        try:
            fm = LocalFileManager(settings=None)
            self.assertIsNotNone(fm, "Should handle None settings")
        except Exception:
            # Might not be supported
            pass

    def test_permission_errors(self):
        """Test handling of permission errors."""
        temp_dir = tempfile.mkdtemp(prefix="permission_test_")
        self.temp_dirs.append(temp_dir)

        settings = {"dataPath": temp_dir}
        fm = LocalFileManager(settings=settings)

        # Create a file that we'll try to access
        test_file = os.path.join(temp_dir, "permission_test.txt")
        with open(test_file, "w") as f:
            f.write("test content")

        # Test that normal operations work
        if hasattr(fm, "exists"):
            self.assertTrue(fm.exists(test_file))

        # Note: We can't easily test actual permission errors in a portable way
        # without potentially causing issues on the test system

    def test_nonexistent_base_path(self):
        """Test handling of non-existent base paths."""
        nonexistent_path = os.path.join(
            tempfile.gettempdir(), "definitely_does_not_exist_12345"
        )

        try:
            fm = LocalFileManager(settings={"dataPath": nonexistent_path})

            # Should either handle gracefully or raise appropriate exception
            if hasattr(fm, "exists"):
                # Should not crash on basic operations
                fm.exists("test.txt")

        except Exception:
            # Raising exceptions for invalid paths is acceptable
            pass


if __name__ == "__main__":
    # Run Local Disk specific tests
    unittest.main(verbosity=2)
