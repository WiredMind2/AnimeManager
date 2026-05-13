import tempfile
from unittest.mock import MagicMock, patch

import pytest

try:
    from adapters.file.base import BaseFileManager
except ImportError:
    # Mock if imports fail
    class BaseFileManager:
        def __init__(self, settings={}, update=False):
            pass


class TestBaseFileManager:
    def setup_method(self):
        self.settings = {"dataPath": tempfile.mkdtemp()}

    """Unit tests for BaseFileManager class."""

    @pytest.mark.timeout(30)
    def test_init_without_update(self):
        """Test initialization without update flag."""
        settings = {"test": "value", "dataPath": "/some/path"}
        with patch("shared.telemetry.logger.Logger.__init__", return_value=None):
            manager = BaseFileManager(settings=settings, update=False)

        assert manager.settings == settings
        assert hasattr(manager, "name")
        assert manager.name == ""

    @pytest.mark.timeout(30)
    def test_init_with_update_calls_change_path(self):
        """Test initialization with update flag calls change_path."""
        settings = {"test": "value"}
        with patch("shared.telemetry.logger.Logger.__init__", return_value=None):
            with pytest.raises(NotImplementedError):
                BaseFileManager(settings=settings, update=True)

    @pytest.mark.timeout(30)
    def test_init_with_empty_datapath_calls_change_path(self):
        """Test initialization with empty dataPath calls change_path."""
        settings = {"dataPath": ""}
        with patch("shared.telemetry.logger.Logger.__init__", return_value=None):
            with pytest.raises(NotImplementedError):
                BaseFileManager(settings=settings, update=False)

    @pytest.mark.timeout(30)
    def test_initialize_does_nothing(self):
        """Test that initialize method does nothing."""
        with patch("shared.telemetry.logger.Logger.__init__", return_value=None):
            manager = BaseFileManager(settings=self.settings)
        # Should not raise any exception
        manager.initialize()

    @pytest.mark.timeout(30)
    def test_isfile_uses_isdir(self):
        """Test that isfile returns not isdir(path)."""
        with patch("shared.telemetry.logger.Logger.__init__", return_value=None):
            manager = BaseFileManager(settings=self.settings)

        with patch.object(manager, "isdir", return_value=False) as mock_isdir:
            result = manager.isfile("/some/path")
            assert result is True
            mock_isdir.assert_called_once_with("/some/path")

        with patch.object(manager, "isdir", return_value=True) as mock_isdir:
            result = manager.isfile("/some/path")
            assert result is False
            mock_isdir.assert_called_once_with("/some/path")

    @pytest.mark.timeout(30)
    def test_delete_uses_shutil_rmtree(self):
        """Test that delete uses shutil.rmtree."""
        with patch("shared.telemetry.logger.Logger.__init__", return_value=None):
            manager = BaseFileManager(settings=self.settings)

        with patch("shutil.rmtree") as mock_rmtree:
            manager.delete("/some/path")
            mock_rmtree.assert_called_once_with("/some/path")

    @pytest.mark.timeout(30)
    def test_open_raises_not_implemented(self):
        """Test that open raises NotImplementedError."""
        with patch("shared.telemetry.logger.Logger.__init__", return_value=None):
            manager = BaseFileManager(settings=self.settings)

        with pytest.raises(NotImplementedError):
            manager.open("/some/path")

    @pytest.mark.timeout(30)
    def test_mkdir_raises_not_implemented(self):
        """Test that mkdir raises NotImplementedError."""
        with patch("shared.telemetry.logger.Logger.__init__", return_value=None):
            manager = BaseFileManager(settings=self.settings)

        with pytest.raises(NotImplementedError):
            manager.mkdir("/some/path")

    @pytest.mark.timeout(30)
    def test_list_raises_not_implemented(self):
        """Test that list raises NotImplementedError."""
        with patch("shared.telemetry.logger.Logger.__init__", return_value=None):
            manager = BaseFileManager(settings=self.settings)

        with pytest.raises(NotImplementedError):
            manager.list("/some/path")

    @pytest.mark.timeout(30)
    def test_exists_raises_not_implemented(self):
        """Test that exists raises NotImplementedError."""
        with patch("shared.telemetry.logger.Logger.__init__", return_value=None):
            manager = BaseFileManager(settings=self.settings)

        with pytest.raises(NotImplementedError):
            manager.exists("/some/path")

    @pytest.mark.timeout(30)
    def test_isdir_raises_not_implemented(self):
        """Test that isdir raises NotImplementedError."""
        with patch("shared.telemetry.logger.Logger.__init__", return_value=None):
            manager = BaseFileManager(settings=self.settings)

        with pytest.raises(NotImplementedError):
            manager.isdir("/some/path")

    @pytest.mark.timeout(30)
    def test_change_path_raises_not_implemented(self):
        """Test that change_path raises NotImplementedError."""
        with patch("shared.telemetry.logger.Logger.__init__", return_value=None):
            manager = BaseFileManager(settings=self.settings)

        with pytest.raises(NotImplementedError):
            manager.change_path({})
