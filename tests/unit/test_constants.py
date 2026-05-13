import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from shared.config.constants import Constants


class TestConstants:
    @pytest.mark.timeout(30)
    def test_initialization(self):
        """Test Constants initialization sets correct attributes."""
        c = Constants()

        assert c.logs == [
            "DB_ERROR",
            "MAIN_STATE",
            "NETWORK",
            "SERVER",
            "SETTINGS",
            "TIME",
            "THREAD",
            "DISK_ERROR",
            "NETWORK_DATA",
            "DB_UPDATE",
        ]
        assert c.hostName == "0.0.0.0"
        assert c.serverPort == 8081
        assert c.players_order == ["mpv_player", "vlc_player", "ff_player"]
        assert c.RPC_client_id == "930139147803459695"
        assert isinstance(c.allLogs, list)
        assert len(c.allLogs) == 19
        assert c.websitesViewUrls["mal_id"] == "https://myanimeList.net/anime/{}"
        assert c.seasons["winter"]["start"] == 1
        assert c.filterOptions["Liked"]["color"] == "Red"
        assert c.status["airing"] == "AIRING"
        assert c.tag_options["Seen"]["filter"] == "SEEN"
        assert c.pathSettings == ["iconPath", "cache", "dbPath", "logsPath"]

    @pytest.mark.timeout(30)
    def test_getAppdata_win32(self):
        """Test getAppdata on Windows."""
        with patch("sys.platform", "win32"), patch.dict(
            os.environ, {"APPDATA": "C:\\Users\\Test\\AppData\\Roaming"}
        ):
            path = Constants.getAppdata()
            assert path == "C:\\Users\\Test\\AppData\\Roaming\\Anime Manager"

    @pytest.mark.timeout(30)
    def test_getAppdata_linux(self):
        """Test getAppdata on Linux."""
        with patch("sys.platform", "linux"):
            path = Constants.getAppdata()
            assert path == "/srv/Anime Manager/"

    @pytest.mark.timeout(30)
    def test_getAppdata_win32_no_appdata(self):
        """Test getAppdata raises error when APPDATA not set on Windows."""
        with patch("sys.platform", "win32"), patch.dict(os.environ, {}, clear=True):
            with pytest.raises(EnvironmentError):
                Constants.getAppdata()

    @pytest.mark.timeout(30)
    def test_checkSettings_existing_file(self):
        """Test checkSettings loads existing settings file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = os.path.join(tmpdir, "settings.json")
            test_settings = {"category": {"var": "value"}}
            with open(settings_path, "w") as f:
                json.dump(test_settings, f)

            c = Constants()
            c.settingsPath = settings_path
            c.checkSettings()

            assert c.settings == test_settings

    @pytest.mark.timeout(30)
    def test_checkSettings_creates_default(self):
        """Test checkSettings creates default settings if file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = os.path.join(tmpdir, "settings.json")
            default_settings_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "..", "settings.json"
            )

            # Assume default exists
            assert os.path.exists(default_settings_path)

            c = Constants()
            c.settingsPath = settings_path
            c.checkSettings()

            assert os.path.exists(settings_path)
            with open(settings_path, "r") as f:
                data = json.load(f)
            assert "UI" in data

    @pytest.mark.timeout(30)
    def test_log_no_super(self):
        """Test log method when no super log exists."""
        c = Constants()
        result = c.log("test")
        assert result is None
