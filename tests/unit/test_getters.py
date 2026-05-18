from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from adapters.legacy.legacy_classes import Anime, Torrent
from shared.config.getters import Getters


class TestGettersStaticMethods:
    @pytest.mark.timeout(30)
    def test_getStatus_finished(self):
        """Test getStatus returns FINISHED for completed anime."""
        anime = Anime(
            {
                "status": None,
                "date_from": 1554508800,  # Past date
                "date_to": 1569628800,  # Past date
                "episodes": 12,
            }
        )
        result = Getters.getStatus(anime)
        assert result == "FINISHED"

    @pytest.mark.timeout(30)
    def test_getStatus_airing(self):
        """Test getStatus returns AIRING for ongoing anime."""
        anime = Anime(
            {
                "status": None,
                "date_from": 1554508800,  # Past date
                "date_to": None,
                "episodes": 12,
            }
        )
        result = Getters.getStatus(anime)
        assert result == "AIRING"

    @pytest.mark.timeout(30)
    def test_getStatus_upcoming(self):
        """Test getStatus returns UPCOMING for future anime."""
        future_timestamp = (
            datetime.now(timezone.utc).timestamp() + 86400 * 30
        )  # 30 days from now
        anime = Anime(
            {
                "status": None,
                "date_from": int(future_timestamp),
                "date_to": None,
                "episodes": 12,
            }
        )
        result = Getters.getStatus(anime)
        assert result == "UPCOMING"

    @pytest.mark.timeout(30)
    def test_getStatus_unknown_no_date(self):
        """Test getStatus returns UNKNOWN when no date_from."""
        anime = Anime(
            {"status": None, "date_from": None, "date_to": None, "episodes": 12}
        )
        result = Getters.getStatus(anime)
        assert result == "UNKNOWN"

    @pytest.mark.timeout(30)
    def test_getStatus_explicit_status(self):
        """Test getStatus returns explicit status when set."""
        anime = Anime(
            {
                "status": "FINISHED",
                "date_from": 1554508800,
                "date_to": 1569628800,
                "episodes": 12,
            }
        )
        result = Getters.getStatus(anime)
        assert result == "FINISHED"

    @pytest.mark.timeout(30)
    def test_getStatus_update_to_unknown(self):
        """Test getStatus converts UPDATE to UNKNOWN."""
        anime = Anime(
            {
                "status": "UPDATE",
                "date_from": 1554508800,
                "date_to": 1569628800,
                "episodes": 12,
            }
        )
        result = Getters.getStatus(anime)
        assert result == "UNKNOWN"

    @pytest.mark.timeout(30)
    def test_getMagnetHash_hex(self):
        """Test getMagnetHash with already hex hash."""
        url = "magnet:?xt=urn:btih:abcdef1234567890abcdef1234567890"
        result = Getters.getMagnetHash(url)
        assert result == "abcdef1234567890abcdef1234567890"

    @pytest.mark.timeout(30)
    def test_getMagnetHash_invalid(self):
        """Test getMagnetHash raises ValueError for invalid magnet."""
        url = "magnet:?xt=urn:btih:"
        with pytest.raises(ValueError):
            Getters.getMagnetHash(url)

    @pytest.mark.timeout(30)
    def test_getFolderFormat_basic(self):
        """Test getFolderFormat cleans title."""
        title = "Test: Anime - Special!"
        result = Getters.getFolderFormat(title)
        assert result == "Test Anime   Special"

    @pytest.mark.timeout(30)
    def test_getFolderFormat_none(self):
        """Test getFolderFormat with None title."""
        result = Getters.getFolderFormat(None)
        assert result == " "

    @pytest.mark.timeout(30)
    def test_getFolderFormat_spaces(self):
        """Test getFolderFormat handles multiple spaces."""
        title = "Test  Anime   Name"
        result = Getters.getFolderFormat(title)
        assert result == "Test  Anime   Name"


class TestGettersInstanceMethods:
    @pytest.mark.timeout(30)
    def test_getDatabase_with_settings(self):
        """Test getDatabase returns database instance."""
        mock_getters = MagicMock(spec=Getters)
        mock_getters.settings = {
            "database_managers": {
                "last_db_used": "sqlite",
                "sqlite": {"path": ":memory:"},
            }
        }

        with patch("shared.config.getters.db_managers") as mock_db_managers:
            mock_db_class = MagicMock()
            mock_db_managers.databases = {"sqlite": mock_db_class}
            mock_instance = MagicMock()
            mock_db_class.return_value = mock_instance

            result = Getters.getDatabase(mock_getters)

            mock_db_class.assert_called_once_with({"path": ":memory:"})
            assert result == mock_instance

    @pytest.mark.timeout(30)
    def test_getDatabase_no_self(self):
        """Test getDatabase with None self uses Constants."""
        with patch("shared.config.getters.Constants") as mock_constants:
            mock_constants_instance = MagicMock()
            mock_constants.return_value = mock_constants_instance
            mock_constants_instance.settings = {
                "database_managers": {"last_db_used": "sqlite", "sqlite": {}}
            }

            with patch("shared.config.getters.db_managers") as mock_db_managers:
                mock_db_class = MagicMock()
                mock_db_managers.databases = {"sqlite": mock_db_class}
                mock_instance = MagicMock()
                mock_db_class.return_value = mock_instance

                result = Getters.getDatabase(None)

                assert result == mock_instance

    @pytest.mark.timeout(30)
    def test_getFeatureFlag_reads_bool_and_string_values(self):
        mock_getters = MagicMock(spec=Getters)
        mock_getters.settings = {
            "feature_flags": {
                "anime_merge_backfill_enabled": "true",
                "other_flag": 0,
            }
        }
        assert Getters.getFeatureFlag(mock_getters, "anime_merge_backfill_enabled") is True
        assert Getters.getFeatureFlag(mock_getters, "other_flag") is False
        assert Getters.getFeatureFlag(mock_getters, "missing", default=True) is True

    @pytest.mark.timeout(30)
    def test_getTorrents_no_id(self):
        """Test getTorrents without id."""
        mock_getters = MagicMock(spec=Getters)
        mock_database = MagicMock()
        mock_getters.getDatabase.return_value = mock_database
        mock_database.sql.return_value = [
            ("hash1", "name1", '["tracker1"]'),
            ("hash2", "name2", '["tracker2"]'),
        ]

        result = Getters.getTorrents(mock_getters)

        expected = [
            Torrent(hash="hash1", name="name1", trackers=["tracker1"]),
            Torrent(hash="hash2", name="name2", trackers=["tracker2"]),
        ]
        assert len(result) == 2
        assert result[0].hash == "hash1"
        assert result[1].name == "name2"

    @pytest.mark.timeout(30)
    def test_getTorrents_with_id(self):
        """Test getTorrents with specific id."""
        mock_getters = MagicMock(spec=Getters)
        mock_database = MagicMock()
        mock_getters.getDatabase.return_value = mock_database
        mock_database.sql.return_value = [("hash1", "name1", '["tracker1"]')]

        result = Getters.getTorrents(mock_getters, id=123)

        mock_database.sql.assert_called_once()
        call_args = mock_database.sql.call_args[0]
        assert "WHERE i.id=?" in call_args[0]
        assert call_args[1] == (123,)

    @pytest.mark.timeout(30)
    def test_getDateText_finished(self):
        """Test getDateText for finished anime."""
        mock_getters = MagicMock(spec=Getters)
        mock_getters.getStatus = Getters.getStatus
        anime = Anime(
            {
                "status": "FINISHED",
                "date_from": 1554508800,
                "date_to": 1569628800,
                "episodes": 12,
            }
        )

        result = Getters.getDateText(mock_getters, anime)

        assert len(result) > 0
        assert "From" in result[0]

    @pytest.mark.timeout(30)
    def test_getDateText_airing(self):
        """Test getDateText for airing anime."""
        mock_getters = MagicMock(spec=Getters)
        mock_getters.getStatus = Getters.getStatus
        anime = Anime(
            {
                "status": "AIRING",
                "date_from": 1554508800,
                "date_to": None,
                "episodes": 12,
                "broadcast": "1-12-30",  # Monday 12:30
            }
        )

        result = Getters.getDateText(mock_getters, anime)

        assert len(result) >= 2
        assert "Since" in result[0]

    @pytest.mark.timeout(30)
    def test_scan_subdirectory_finds_nested_anime_folder(self):
        """Series folders nested under animePath (e.g. …/Animes/Title - id) resolve."""
        mock_self = MagicMock()
        fm = MagicMock()
        mock_self.fm = fm

        def norm(p: str) -> str:
            return str(p).replace("\\", "/")

        existing = {
            "/root",
            "/root/Animes",
            "/root/Animes/Classroom of Elite - 1090",
        }

        fm.exists.side_effect = lambda p: norm(p) in existing

        fm.isdir.side_effect = lambda p: norm(p) in existing

        def listdir(path: str):
            p = norm(path)
            if p == "/root":
                return ["Animes"]
            if p == "/root/Animes":
                return ["Classroom of Elite - 1090"]
            return []

        fm.list.side_effect = listdir

        result = Getters._scan_subdirectory_for_existing_anime_folder(
            mock_self, "/root", 1090
        )
        assert result == "/root/Animes/Classroom of Elite - 1090"

    @pytest.mark.timeout(30)
    def test_getDateText_unknown(self):
        """Test getDateText for unknown status."""
        mock_getters = MagicMock(spec=Getters)
        mock_getters.getStatus = Getters.getStatus
        anime = Anime(
            {"status": "UNKNOWN", "date_from": None, "date_to": None, "episodes": 12}
        )

        result = Getters.getDateText(mock_getters, anime)

        assert result == []
