"""
Base test classes for file manager modules.

This module provides test base classes that can be used to test any file manager
implementation that inherits from BaseFileManager. It ensures consistent behavior
across all file manager plugins.
"""

import os
import sys
import tempfile
import unittest
from abc import ABC, abstractmethod
from unittest.mock import MagicMock, patch

# Add project root to path
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from adapters.file.base import BaseFileManager
except ImportError:
    # Create mock if import fails
    class BaseFileManager:
        pass


class BaseFileManagerTestBase(ABC):
    """
    Base test class for file manager implementations.

    This class should be mixed with unittest.TestCase to create tests for
    specific file manager implementations.
    """

    @abstractmethod
    def get_file_manager_instance(self, **kwargs) -> BaseFileManager:
        """Return a file manager instance for testing."""
        pass

    @abstractmethod
    def cleanup_file_manager(self):
        """Clean up file manager resources."""
        pass

    def setUp(self):
        """Set up test environment."""
        self.temp_dirs = []
        self.test_files = {}
        self.file_manager = None

        # Set up mock logging
        self.setup_mocks()

        try:
            self.file_manager = self.get_file_manager_instance()
        except Exception as e:
            self.fail(f"Could not create file manager instance: {e}")

        # Create test file structure
        self.setup_test_filesystem()

    def tearDown(self):
        """Clean up test environment."""
        self.cleanup_file_manager()
        self.cleanup_test_filesystem()
        self.cleanup_mocks()

    def setup_mocks(self):
        """Set up common mocks for file manager testing."""
        self.mock_patches = []

        # Mock logger
        logger_patch = patch("shared.telemetry.logger.Logger.__init__", return_value=None)
        self.mock_logger = logger_patch.start()
        self.mock_patches.append(logger_patch)

        log_patch = patch("shared.telemetry.logger.log")
        self.mock_log = log_patch.start()
        self.mock_patches.append(log_patch)

    def cleanup_mocks(self):
        """Clean up mock patches."""
        for patch_obj in self.mock_patches:
            try:
                patch_obj.stop()
            except Exception:
                pass

    def setup_test_filesystem(self):
        """Create test filesystem structure."""
        self.test_root = tempfile.mkdtemp(prefix="filemanager_test_")
        self.temp_dirs.append(self.test_root)

        # Create test directories
        self.test_dirs = {
            "root": self.test_root,
            "videos": os.path.join(self.test_root, "videos"),
            "downloads": os.path.join(self.test_root, "downloads"),
            "nested": os.path.join(self.test_root, "videos", "season1"),
            "empty": os.path.join(self.test_root, "empty"),
        }

        for dir_path in self.test_dirs.values():
            os.makedirs(dir_path, exist_ok=True)

        # Create test files
        self.test_files = {
            "video1": os.path.join(self.test_dirs["videos"], "anime_episode_01.mkv"),
            "video2": os.path.join(self.test_dirs["videos"], "anime_episode_02.mp4"),
            "nested_video": os.path.join(self.test_dirs["nested"], "episode_03.mkv"),
            "text_file": os.path.join(self.test_dirs["downloads"], "readme.txt"),
            "config_file": os.path.join(self.test_root, "config.json"),
        }

        # Create actual test files
        for name, path in self.test_files.items():
            with open(path, "w") as f:
                if "video" in name:
                    f.write(f"# Fake video content for {name}")
                elif "config" in name:
                    f.write('{"test": "configuration"}')
                else:
                    f.write(f"Test content for {name}")

    def cleanup_test_filesystem(self):
        """Clean up test filesystem."""
        import shutil

        for temp_dir in self.temp_dirs:
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except Exception:
                pass

    def test_file_manager_inheritance(self):
        """Test that file manager inherits from BaseFileManager."""
        self.assertIsInstance(
            self.file_manager,
            BaseFileManager,
            "File manager should inherit from BaseFileManager",
        )

    def test_file_manager_name_attribute(self):
        """Test that file manager has a name attribute."""
        self.assertTrue(
            hasattr(self.file_manager, "name"),
            "File manager should have a name attribute",
        )
        name = getattr(self.file_manager, "name", "")
        self.assertIsInstance(name, str, "Name should be a string")

    def test_exists_method(self):
        """Test exists method functionality."""
        if not hasattr(self.file_manager, "exists"):
            self.fail("File manager does not implement exists method")

        # Test existing file
        self.assertTrue(
            self.file_manager.exists(self.test_files["video1"]),
            "Should detect existing file",
        )

        # Test existing directory
        self.assertTrue(
            self.file_manager.exists(self.test_dirs["videos"]),
            "Should detect existing directory",
        )

        # Test non-existing file
        non_existing = os.path.join(self.test_root, "non_existing.txt")
        self.assertFalse(
            self.file_manager.exists(non_existing),
            "Should not detect non-existing file",
        )

    def test_isfile_method(self):
        """Test isfile method functionality."""
        if not hasattr(self.file_manager, "isfile"):
            self.fail("File manager does not implement isfile method")

        # Test with actual file
        self.assertTrue(
            self.file_manager.isfile(self.test_files["video1"]),
            "Should identify file correctly",
        )

        # Test with directory
        self.assertFalse(
            self.file_manager.isfile(self.test_dirs["videos"]),
            "Should not identify directory as file",
        )

    def test_isdir_method(self):
        """Test isdir method functionality."""
        if not hasattr(self.file_manager, "isdir"):
            self.fail("File manager does not implement isdir method")

        # Test with actual directory
        self.assertTrue(
            self.file_manager.isdir(self.test_dirs["videos"]),
            "Should identify directory correctly",
        )

        # Test with file
        self.assertFalse(
            self.file_manager.isdir(self.test_files["video1"]),
            "Should not identify file as directory",
        )

    def test_list_method(self):
        """Test list method functionality."""
        if not hasattr(self.file_manager, "list"):
            self.fail("File manager does not implement list method")

        # Test listing directory with files
        files = self.file_manager.list(self.test_dirs["videos"])
        self.assertIsInstance(files, (list, tuple), "List should return list or tuple")

        # Should contain our test files
        file_names = [os.path.basename(f) for f in files] if files else []
        self.assertIn("anime_episode_01.mkv", file_names, "Should list existing files")

        # Test empty directory
        empty_files = self.file_manager.list(self.test_dirs["empty"])
        self.assertIsInstance(
            empty_files,
            (list, tuple),
            "Should return list/tuple even for empty directory",
        )

    def test_mkdir_method(self):
        """Test mkdir method functionality."""
        if not hasattr(self.file_manager, "mkdir"):
            self.fail("File manager does not implement mkdir method")

        new_dir = os.path.join(self.test_root, "new_directory")

        # Create directory
        try:
            self.file_manager.mkdir(new_dir)

            # Verify directory was created
            self.assertTrue(os.path.exists(new_dir), "Directory should be created")
            self.assertTrue(
                os.path.isdir(new_dir), "Created path should be a directory"
            )

        except NotImplementedError:
            self.fail("mkdir method not implemented")
        except Exception as e:
            self.fail(f"mkdir failed with exception: {e}")

    def test_open_method(self):
        """Test open method functionality."""
        if not hasattr(self.file_manager, "open"):
            self.fail("File manager does not implement open method")

        # Test reading existing file
        try:
            with self.file_manager.open(self.test_files["text_file"], "r") as f:
                content = f.read()
                self.assertIsInstance(
                    content, str, "Should read file content as string"
                )
                self.assertIn("Test content", content, "Should read correct content")

        except NotImplementedError:
            self.fail("open method not implemented")
        except Exception as e:
            self.fail(f"Reading file failed: {e}")

        # Test writing new file
        try:
            new_file = os.path.join(self.test_root, "new_file.txt")
            test_content = "Test write content"

            with self.file_manager.open(new_file, "w") as f:
                f.write(test_content)

            # Verify file was written
            if os.path.exists(new_file):
                with open(new_file, "r") as f:
                    written_content = f.read()
                    self.assertEqual(
                        written_content, test_content, "Written content should match"
                    )

        except Exception as e:
            # Writing might not be supported by all file managers
            pass

    def test_path_handling(self):
        """Test various path handling scenarios."""
        # Test absolute paths
        if hasattr(self.file_manager, "exists"):
            abs_path = os.path.abspath(self.test_files["video1"])
            self.assertTrue(
                self.file_manager.exists(abs_path), "Should handle absolute paths"
            )

        # Test relative paths (if supported)
        if hasattr(self.file_manager, "exists"):
            try:
                # This might not work for all file managers
                rel_path = os.path.relpath(self.test_files["video1"])
                self.file_manager.exists(rel_path)
            except Exception:
                # Relative paths might not be supported
                pass

    def test_error_handling(self):
        """Test error handling for invalid operations."""
        # Test with invalid path
        invalid_path = "/this/path/should/not/exist/anywhere"

        if hasattr(self.file_manager, "exists"):
            # Should not crash on invalid path
            try:
                result = self.file_manager.exists(invalid_path)
                self.assertIsInstance(
                    result, bool, "exists should return boolean even for invalid paths"
                )
                self.assertFalse(result, "Invalid path should not exist")
            except Exception:
                # Some implementations might raise exceptions, which is also acceptable
                pass

        if hasattr(self.file_manager, "list"):
            # Should handle listing non-existent directory gracefully
            try:
                result = self.file_manager.list(invalid_path)
                # Should either return empty list or raise exception
                if result is not None:
                    self.assertIsInstance(
                        result,
                        (list, tuple),
                        "list should return list/tuple or raise exception",
                    )
            except Exception:
                # Raising exception for invalid directory is acceptable
                pass

    def test_settings_handling(self):
        """Test file manager settings handling."""
        self.assertTrue(
            hasattr(self.file_manager, "settings"),
            "File manager should have settings attribute",
        )

        settings = getattr(self.file_manager, "settings", {})
        self.assertIsInstance(settings, dict, "Settings should be a dictionary")

    def test_initialization_method(self):
        """Test initialization method if present."""
        if hasattr(self.file_manager, "initialize"):
            try:
                # Should not crash when called
                self.file_manager.initialize()
            except NotImplementedError:
                # Optional method, NotImplementedError is acceptable
                pass
            except Exception as e:
                self.fail(f"initialize method failed: {e}")


class FileManagerPerformanceTestBase(ABC):
    """Performance tests for file manager implementations."""

    @abstractmethod
    def get_file_manager_instance(self, **kwargs) -> BaseFileManager:
        """Return a file manager instance for performance testing."""
        pass

    def setUp(self):
        """Set up performance test environment."""
        self.temp_root = tempfile.mkdtemp(prefix="filemanager_perf_")
        self.file_manager = self.get_file_manager_instance()
        self.create_large_test_structure()

    def tearDown(self):
        """Clean up performance test environment."""
        import shutil

        try:
            if os.path.exists(self.temp_root):
                shutil.rmtree(self.temp_root)
        except Exception:
            pass

    def create_large_test_structure(self):
        """Create a larger test structure for performance testing."""
        import time

        # Create multiple directories
        for i in range(10):
            dir_path = os.path.join(self.temp_root, f"dir_{i}")
            os.makedirs(dir_path, exist_ok=True)

            # Create files in each directory
            for j in range(20):
                file_path = os.path.join(dir_path, f"file_{j}.txt")
                with open(file_path, "w") as f:
                    f.write(f"Content of file {j} in directory {i}")

    def test_large_directory_listing_performance(self):
        """Test performance of listing large directories."""
        if not hasattr(self.file_manager, "list"):
            self.fail("File manager does not implement list method")

        import time

        start_time = time.time()

        # List all directories
        for i in range(10):
            dir_path = os.path.join(self.temp_root, f"dir_{i}")
            files = self.file_manager.list(dir_path)
            self.assertIsInstance(files, (list, tuple))

        end_time = time.time()
        duration = end_time - start_time

        # Performance should be reasonable (adjust threshold as needed)
        self.assertLess(
            duration, 5.0, f"Large directory listing took too long: {duration:.2f}s"
        )

    def test_batch_existence_check_performance(self):
        """Test performance of batch existence checks."""
        if not hasattr(self.file_manager, "exists"):
            self.fail("File manager does not implement exists method")

        import time

        # Create list of paths to check
        paths_to_check = []
        for i in range(10):
            for j in range(20):
                paths_to_check.append(
                    os.path.join(self.temp_root, f"dir_{i}", f"file_{j}.txt")
                )

        start_time = time.time()

        # Check existence of all files
        for path in paths_to_check:
            exists = self.file_manager.exists(path)
            self.assertTrue(exists, f"File should exist: {path}")

        end_time = time.time()
        duration = end_time - start_time

        # Performance should be reasonable
        self.assertLess(
            duration, 10.0, f"Batch existence check took too long: {duration:.2f}s"
        )

        print(f"Checked {len(paths_to_check)} files in {duration:.3f}s")


if __name__ == "__main__":
    # This module provides base classes, not runnable tests
    print("This module provides base test classes for file managers.")
    print("Use specific test files for each file manager implementation.")
