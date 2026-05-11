from unittest.mock import MagicMock, patch

import pytest

from ...animeManager import Manager


@pytest.mark.timeout(30)
def test_manager_initialization_with_mocked_config():
    """Test Manager initialization with mocked configuration and dependencies."""
    with patch.object(Manager, "checkSettings") as mock_check_settings:

        # Create manager instance
        manager = Manager(remote=True)

        # Verify initialization calls
        assert manager.remote == True
        assert hasattr(manager, "animeFolder")
        assert hasattr(manager, "searchQueue")
        assert hasattr(manager, "relationIds")
        assert hasattr(manager, "characterIds")
        assert hasattr(manager, "animeHashes")
        assert manager.stopSearch == False
        assert manager.closing == False

        # Verify mocked methods were called
        mock_check_settings.assert_called_once()  # Always called


@pytest.mark.timeout(30)
def test_manager_initialization_database_not_initialized():
    """Test Manager initialization when database is not initialized."""
    with patch.object(Manager, "checkSettings") as mock_check_settings:

        # Create manager instance
        manager = Manager(remote=True)

        # Verify calls when db not initialized
        mock_check_settings.assert_called_once()


@pytest.mark.timeout(30)
def test_searchDb_with_valid_terms():
    """Test searchDb method with valid search terms."""
    manager = Manager.__new__(Manager)  # Create without calling __init__

    # Mock database manager
    mock_db_manager = MagicMock()
    mock_db_manager.search_anime.return_value = ([], [("data1", "data2")])  # args, results
    manager._database_manager = mock_db_manager

    result = manager.searchDb("test search")

    assert result is not None
    mock_db_manager.search_anime.assert_called_once_with("test search")


@pytest.mark.timeout(30)
def test_searchDb_no_results():
    """Test searchDb method when no results are found."""
    manager = Manager.__new__(Manager)

    # Mock database manager
    mock_db_manager = MagicMock()
    mock_db_manager.search_anime.return_value = False  # No results
    manager._database_manager = mock_db_manager

    result = manager.searchDb("test search")

    assert result is False


@pytest.mark.timeout(30)
def test_getAnimelist_default_criteria():
    """Test getAnimelist method with DEFAULT criteria."""
    manager = Manager.__new__(Manager)
    manager.hideRated = False

    # Mock database manager
    mock_db_manager = MagicMock()
    mock_db_manager.get_anime_list.return_value = []  # Some result
    manager._database_manager = mock_db_manager

    result = manager.getAnimelist("DEFAULT")

    assert result is not None
    mock_db_manager.get_anime_list.assert_called_once()


@pytest.mark.timeout(30)
def test_clearLogs():
    """Test clearLogs method."""
    import os

    with patch("os.listdir") as mock_listdir, patch("os.remove") as mock_remove:

        manager = Manager.__new__(Manager)
        manager.logsPath = "/fake/logs"
        manager.logFile = os.path.join("/fake/logs", "current.log")

        mock_listdir.return_value = ["log1.txt", "log2.txt", "current.log"]

        manager.clearLogs()

        # Should remove all files except current.log
        expected_path1 = os.path.join("/fake/logs", "log1.txt")
        expected_path2 = os.path.join("/fake/logs", "log2.txt")
        mock_remove.assert_any_call(expected_path1)
        mock_remove.assert_any_call(expected_path2)
        assert mock_remove.call_count == 2


@pytest.mark.timeout(30)
def test_quit_method():
    """Test quit method functionality."""
    with patch.object(Manager, "log", return_value=None), patch.object(
        Manager, "updateAll"
    ) as mock_update_all, patch(
        "time.time", return_value=110.0
    ):

        manager = Manager.__new__(Manager)
        manager.closing = False
        manager.start = 100.0
        manager.root = None
        manager.initWindow = None

        # Mock components
        mock_db_manager = MagicMock()
        manager.database = mock_db_manager
        manager._application_controller = MagicMock()

        manager.quit()

        assert manager.closing == True
        assert manager.stopSearch == True
