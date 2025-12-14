from unittest.mock import MagicMock, patch

import pytest

from animeManager import Manager


@pytest.mark.timeout(30)
def test_manager_initialization_with_mocked_config():
    """Test Manager initialization with mocked configuration and dependencies."""
    with patch("animeManager.Constants.__init__", return_value=None), patch(
        "animeManager.Logger.__init__", return_value=None
    ), patch.object(Manager, "getDatabase") as mock_get_db, patch.object(
        Manager, "getFileManager"
    ) as mock_get_fm, patch.object(
        Manager, "getTorrentManager"
    ) as mock_get_tm, patch.object(
        Manager, "checkSettings"
    ) as mock_check_settings, patch.object(
        Manager, "late_startup"
    ) as mock_late_startup:

        # Mock database
        mock_db = MagicMock()
        mock_db.is_initialized.return_value = True
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = None

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
        mock_get_fm.assert_called_once()
        mock_get_db.assert_called_once()
        mock_check_settings.assert_not_called()  # Since db is initialized
        mock_late_startup.assert_called_once()


@pytest.mark.timeout(30)
def test_manager_initialization_database_not_initialized():
    """Test Manager initialization when database is not initialized."""
    with patch("animeManager.Constants.__init__", return_value=None), patch(
        "animeManager.Logger.__init__", return_value=None
    ), patch.object(Manager, "getDatabase") as mock_get_db, patch.object(
        Manager, "getFileManager"
    ) as mock_get_fm, patch.object(
        Manager, "checkSettings"
    ) as mock_check_settings, patch.object(
        Manager, "reloadAll"
    ) as mock_reload_all:

        # Mock database not initialized
        mock_db = MagicMock()
        mock_db.is_initialized.return_value = False
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_get_db.return_value.__exit__.return_value = None

        # Create manager instance
        manager = Manager(remote=True)

        # Verify calls when db not initialized
        mock_check_settings.assert_called_once()
        mock_reload_all.assert_called_once()


@pytest.mark.timeout(30)
def test_searchDb_with_valid_terms():
    """Test searchDb method with valid search terms."""
    with patch("animeManager.Constants.__init__", return_value=None), patch(
        "animeManager.Logger.__init__", return_value=None
    ), patch.object(Manager, "getDatabase") as mock_get_db:

        manager = Manager.__new__(Manager)  # Create without calling __init__

        # Mock database
        mock_db = MagicMock()
        mock_procedure = MagicMock()
        mock_procedure.return_value = ([], [("data1", "data2")])  # args, results
        mock_db.procedure = mock_procedure
        manager.database = mock_db

        # Mock AnimeList and Anime
        with patch("animeManager.AnimeList") as mock_anime_list, patch(
            "animeManager.Anime"
        ) as mock_anime:

            mock_anime_instance = MagicMock()
            mock_anime.return_value = mock_anime_instance
            mock_anime_list.return_value = MagicMock()

            result = manager.searchDb("test search")

            assert result is not None
            mock_procedure.assert_called_once_with(
                "search_anime_fast", "test search", 50
            )


@pytest.mark.timeout(30)
def test_searchDb_no_results():
    """Test searchDb method when no results are found."""
    with patch("animeManager.Constants.__init__", return_value=None), patch(
        "animeManager.Logger.__init__", return_value=None
    ):

        manager = Manager.__new__(Manager)

        # Mock database
        mock_db = MagicMock()
        mock_procedure = MagicMock()
        mock_procedure.return_value = ([], [])  # No results
        mock_db.procedure = mock_procedure
        manager.database = mock_db

        result = manager.searchDb("test search")

        assert result is False


@pytest.mark.timeout(30)
def test_getAnimelist_default_criteria():
    """Test getAnimelist method with DEFAULT criteria."""
    with patch("animeManager.Constants.__init__", return_value=None), patch(
        "animeManager.Logger.__init__", return_value=None
    ), patch.object(Manager, "getDatabase") as mock_get_db:

        manager = Manager.__new__(Manager)
        manager.hideRated = False

        # Mock database
        mock_db = MagicMock()
        mock_filter = MagicMock()
        mock_filter.empty.return_value = True
        mock_db.filter = mock_filter
        manager.database = mock_db

        result = manager.getAnimelist("DEFAULT")

        assert result is not None
        mock_filter.assert_called_once()


@pytest.mark.timeout(30)
def test_clearLogs():
    """Test clearLogs method."""
    import os

    with patch("animeManager.Constants.__init__", return_value=None), patch(
        "animeManager.Logger.__init__", return_value=None
    ), patch("os.listdir") as mock_listdir, patch("os.remove") as mock_remove:

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
    with patch("animeManager.Constants.__init__", return_value=None), patch(
        "animeManager.Logger.__init__", return_value=None
    ), patch.object(Manager, "log", return_value=None), patch.object(
        Manager, "RPC_stop"
    ) as mock_rpc_stop, patch.object(
        Manager, "updateAll"
    ) as mock_update_all, patch(
        "animeManager.time"
    ) as mock_time:

        manager = Manager.__new__(Manager)
        manager.closing = False
        manager.start = 100.0
        manager.root = None
        manager.initWindow = None
        mock_time.time.return_value = 110.0

        # Mock database
        mock_db = MagicMock()
        manager.database = mock_db

        manager.quit()

        assert manager.closing == True
        assert manager.stopSearch == True
        mock_rpc_stop.assert_called_once()
        mock_update_all.assert_called_once()
        mock_db.close.assert_called_once()
