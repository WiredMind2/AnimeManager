from unittest.mock import MagicMock, patch

import pytest

try:
    from adapters.torrent.base import (
        BaseTorrentManager,
        TorrentException,
        TorrentListFilter,
    )
except ImportError:
    # Mock if imports fail
    class BaseTorrentManager:
        def __init__(self, settings={}, update=False):
            pass

    class TorrentException(Exception):
        pass

    class TorrentListFilter:
        pass


class TestBaseTorrentManager:
    """Unit tests for BaseTorrentManager class."""

    @pytest.mark.timeout(30)
    def test_init_without_update(self):
        """Test initialization without update flag."""
        settings = {"test": "value"}
        manager = BaseTorrentManager(settings=settings, update=False)

        assert manager.settings == settings
        assert hasattr(manager, "name")
        assert manager.name == ""

    @pytest.mark.timeout(30)
    def test_init_with_update_calls_login_dialog(self):
        """Test initialization with update flag calls login_dialog."""
        settings = {"test": "value"}

        with pytest.raises(NotImplementedError):
            BaseTorrentManager(settings=settings, update=True)

    @pytest.mark.timeout(30)
    def test_initialize_does_nothing(self):
        """Test that initialize method does nothing."""
        manager = BaseTorrentManager()
        # Should not raise any exception
        manager.initialize()

    @pytest.mark.timeout(30)
    def test_connect_raises_not_implemented(self):
        """Test that connect raises NotImplementedError."""
        manager = BaseTorrentManager()

        with pytest.raises(NotImplementedError):
            manager.connect()

    @pytest.mark.timeout(30)
    def test_login_dialog_raises_not_implemented(self):
        """Test that login_dialog raises NotImplementedError."""
        manager = BaseTorrentManager()

        with pytest.raises(NotImplementedError):
            manager.login_dialog()

    @pytest.mark.timeout(30)
    def test_add_raises_not_implemented(self):
        """Test that add raises NotImplementedError."""
        manager = BaseTorrentManager()

        with pytest.raises(NotImplementedError):
            manager.add(["hash1"])

    @pytest.mark.timeout(30)
    def test_list_raises_not_implemented(self):
        """Test that list raises NotImplementedError."""
        manager = BaseTorrentManager()

        with pytest.raises(NotImplementedError):
            manager.list()

    @pytest.mark.timeout(30)
    def test_move_raises_not_implemented(self):
        """Test that move raises NotImplementedError."""
        manager = BaseTorrentManager()

        with pytest.raises(NotImplementedError):
            manager.move(["hash1"], ["path1"])

    @pytest.mark.timeout(30)
    def test_delete_raises_not_implemented(self):
        """Test that delete raises NotImplementedError."""
        manager = BaseTorrentManager()

        with pytest.raises(NotImplementedError):
            manager.delete(["hash1"])

    @pytest.mark.timeout(30)
    def test_error_wrapper_catches_exceptions(self):
        """Test that error_wrapper catches exceptions and raises TorrentException."""
        manager = BaseTorrentManager()

        def dummy_function(self):
            raise ValueError("Test error")

        wrapped_function = BaseTorrentManager.error_wrapper(dummy_function)

        with pytest.raises(TorrentException):
            wrapped_function(manager)

    @pytest.mark.timeout(30)
    def test_error_wrapper_preserves_function_result(self):
        """Test that error_wrapper preserves function result when no exception."""
        manager = BaseTorrentManager()

        def dummy_function(self):
            return "success"

        wrapped_function = BaseTorrentManager.error_wrapper(dummy_function)

        result = wrapped_function(manager)
        assert result == "success"
