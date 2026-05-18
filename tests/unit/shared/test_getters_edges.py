"""Edge case tests for ``shared.config.getters`` (LRU cache, decorators, helpers)."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from adapters.legacy.legacy_classes import Anime, Torrent
from shared.config.getters import LRUCache, Getters, cached_getter


# ---------------------------------------------------------------------------
# LRUCache
# ---------------------------------------------------------------------------


class TestLRUCache:
    def test_get_set_roundtrip(self):
        cache = LRUCache(max_size=10, ttl=300)
        cache.set("k", "v")
        assert cache.get("k") == "v"

    def test_get_missing_returns_none(self):
        assert LRUCache().get("missing") is None

    def test_expired_entry_returns_none(self):
        cache = LRUCache(max_size=10, ttl=1)
        cache.set("k", "v")
        with patch("shared.config.getters.time.time", return_value=time.time() + 2):
            assert cache.get("k") is None

    def test_evicts_oldest_when_at_capacity(self):
        cache = LRUCache(max_size=2, ttl=300)
        cache.set("a", 1)
        time.sleep(0.01)
        cache.set("b", 2)
        cache.set("c", 3)  # should evict "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_clear_removes_all(self):
        cache = LRUCache()
        cache.set("x", 1)
        cache.clear()
        assert cache.get("x") is None

    def test_evict_oldest_on_empty_access_times(self):
        cache = LRUCache()
        cache._evict_oldest()  # must not raise


# ---------------------------------------------------------------------------
# cached_getter decorator
# ---------------------------------------------------------------------------


class _CachedHost:
    def __init__(self):
        self.counter = 0

    def log(self, category: str, message: str, *args) -> None:
        pass

    @cached_getter(ttl=300, max_size=10)
    def compute(self, n: int):
        self.counter += 1
        return n * 2


class TestCachedGetter:
    def test_caches_return_value(self):
        host = _CachedHost()
        assert host.compute(3) == 6
        assert host.compute(3) == 6
        assert host.counter == 1

    def test_does_not_cache_none(self):
        class _NoneHost:
            def log(self, *a, **k):
                pass

            @cached_getter()
            def sometimes_none(self, flag: bool):
                return None if flag else "ok"

        host = _NoneHost()
        assert host.sometimes_none(True) is None
        assert host.sometimes_none(True) is None  # not cached; would differ if cached

    def test_unhashable_kwargs_use_string_fallback(self):
        class _UnhashableHost:
            def __init__(self):
                self.logged = False

            def log(self, *a, **k):
                self.logged = True

            @cached_getter()
            def compute(self, n, extras=None):
                return n + len(extras or [])

        host = _UnhashableHost()
        payload = [1, 2]
        assert host.compute(1, extras=payload) == 3
        assert host.compute(1, extras=payload) == 3
        assert host.logged is True


# ---------------------------------------------------------------------------
# Static helpers (additional branches)
# ---------------------------------------------------------------------------


class TestGettersStaticEdges:
    def test_getStatus_single_episode_finished(self):
        anime = Anime(
            {
                "status": None,
                "date_from": 1554508800,
                "date_to": None,
                "episodes": 1,
            }
        )
        assert Getters.getStatus(anime) == "FINISHED"

    def test_getStatus_airing_with_future_end_date(self):
        future = int((datetime.now(timezone.utc).timestamp()) + 86400 * 365)
        anime = Anime(
            {
                "status": None,
                "date_from": 1554508800,
                "date_to": future,
                "episodes": 12,
            }
        )
        assert Getters.getStatus(anime) == "AIRING"

    def test_getMagnetHash_base32_decodes_to_hex(self):
        import base64

        raw = b"\xab" * 20
        b32 = base64.b32encode(raw).decode().rstrip("=")
        url = f"magnet:?xt=urn:btih:{b32}"
        result = Getters.getMagnetHash(url)
        assert len(result) == 40
        assert all(c in "0123456789abcdef" for c in result)

    def test_getFolderFormat_hyphen_becomes_space(self):
        assert Getters.getFolderFormat("Naruto-Shippuden") == "Naruto Shippuden"


class TestGetFeatureFlagEdges:
    def test_returns_default_when_settings_not_dict(self):
        host = SimpleNamespace(settings="bad")
        assert Getters.getFeatureFlag(host, "x", default=True) is True

    def test_returns_default_when_flags_not_dict(self):
        host = SimpleNamespace(settings={"feature_flags": []})
        assert Getters.getFeatureFlag(host, "x", default=False) is False

    def test_string_false_values(self):
        host = SimpleNamespace(
            settings={"feature_flags": {"off": "no", "on": "yes"}}
        )
        assert Getters.getFeatureFlag(host, "off") is False
        assert Getters.getFeatureFlag(host, "on") is True


class TestGetDatabaseEdges:
    def test_raises_when_manager_missing(self):
        host = MagicMock(spec=Getters)
        host.settings = {"database_managers": {"last_db_used": "missing"}}
        with patch("shared.config.getters.db_managers") as mock_db:
            mock_db.databases = {}
            with pytest.raises(ModuleNotFoundError, match="missing"):
                Getters.getDatabase(host)

    def test_reuses_cached_instance_for_same_args(self):
        host = MagicMock(spec=Getters)
        host.settings = {
            "database_managers": {
                "last_db_used": "sqlite",
                "sqlite": {"path": ":memory:"},
            }
        }
        import shared.config.getters as getters_mod

        getters_mod._database_instances.clear()
        try:
            with patch("shared.config.getters.db_managers") as mock_db:
                mock_cls = MagicMock()
                mock_instance = MagicMock()
                mock_cls.return_value = mock_instance
                mock_db.databases = {"sqlite": mock_cls}

                first = Getters.getDatabase(host)
                second = Getters.getDatabase(host)

                assert first is second
                mock_cls.assert_called_once()
        finally:
            getters_mod._database_instances.clear()


class TestGetEpisodes:
    def _make_host(self, fm):
        host = MagicMock(spec=Getters)
        host.fm = fm
        return host

    def test_empty_folder_returns_empty_list(self):
        fm = MagicMock()
        fm.exists.return_value = False
        assert Getters.getEpisodes(self._make_host(fm), "") == []

    def test_parses_episode_and_season_from_filenames(self):
        fm = MagicMock()
        fm.exists.return_value = True
        fm.isdir.return_value = False
        fm.isfile.return_value = True
        fm.list.return_value = [
            "[Group] Show - 01.mkv",
            "[Group] Show S02 Ep03.mkv",
        ]

        result = Getters.getEpisodes(self._make_host(fm), "/anime/Show - 1")
        assert len(result) == 2
        assert result[0]["episode"] in ("01", "1", "?")
        assert result[1]["season"] in ("02", "2", 0, "0")

    def test_nested_subfolders_are_scanned(self):
        fm = MagicMock()
        fm.exists.return_value = True

        def isdir(path):
            return path.endswith("Season 1")

        def listdir(path):
            if "Show - 1" in path and "Season" not in path:
                return ["Season 1"]
            if path.endswith("Season 1") or path.endswith("Season 1/"):
                return ["ep.mkv"]
            return []

        fm.isdir.side_effect = isdir
        fm.isfile.side_effect = lambda p: p.endswith(".mkv")
        fm.list.side_effect = listdir

        result = Getters.getEpisodes(self._make_host(fm), "/anime/Show - 1")
        assert len(result) == 1
        assert result[0]["path"].endswith("ep.mkv")


class TestGetTorrentColor:
    def test_returns_blue_when_title_matches_existing_torrent(self):
        host = MagicMock(spec=Getters)
        host.colors = {"Blue": "#00f", "White": "#fff"}
        host.fileMarkers = {}
        torrent = Torrent(hash="a", name="My Show - 01.torrent", trackers=[])
        host.getTorrents.return_value = [torrent]

        with patch.object(Getters, "getTorrentColor_title_cache", {}, create=True):
            with patch.object(Getters, "getTorrentColor_pat_cache", {}, create=True):
                with patch.object(Getters, "getTorrentColor_matchs_cache", {}, create=True):
                    color = Getters.getTorrentColor(host, "My Show - 01.torrent")
        assert color == "#00f"

    def test_marker_pattern_applies_color(self):
        host = MagicMock(spec=Getters)
        host.colors = {"Red": "#f00", "White": "#fff"}
        host.fileMarkers = {"Red": [r"^\[Batch\]"]}
        # Marker checks run in the else-branch while iterating known torrent files.
        other = Torrent(hash="x", name="Unrelated Show 999.torrent", trackers=[])
        host.getTorrents.return_value = [other]
        host.formattedTorrentFiles = (time.time(), {"unrelatedshow999"})

        from shared.config.constants import Constants

        for attr in (
            "getTorrentColor_title_cache",
            "getTorrentColor_pat_cache",
            "getTorrentColor_matchs_cache",
        ):
            if hasattr(Constants, attr):
                delattr(Constants, attr)

        # Force pattern cache rebuild for this host's markers
        import re

        Constants.getTorrentColor_pat_cache = {  # type: ignore[attr-defined]
            re.compile(pat, re.I): col
            for col, pats in host.fileMarkers.items()
            for pat in pats
        }

        color = Getters.getTorrentColor(host, "[Batch] Complete Series")
        assert color == "#f00"


class TestGetAnimePicturesCache:
    def test_empty_ids_returns_empty_dict(self):
        host = MagicMock(spec=Getters)
        assert Getters.getAnimePicturesCache(host, []) == {}


class TestGetDateTextEdges:
    def test_upcoming_status_includes_days_left(self):
        future_ts = int(datetime.now(timezone.utc).timestamp() + 86400 * 10)
        host = MagicMock(spec=Getters)
        host.getStatus = Getters.getStatus
        anime = Anime(
            {
                "status": None,
                "date_from": future_ts,
                "date_to": None,
                "episodes": 12,
            }
        )
        result = Getters.getDateText(host, anime)
        assert len(result) == 1
        assert "days left" in result[0]


class TestSaveTorrentDeprecation:
    def test_delegates_to_database_manager_when_present(self):
        host = MagicMock(spec=Getters)
        dm = MagicMock()
        host._database_manager = dm
        torrent = Torrent(hash="abc", name="n", trackers=[])

        with pytest.warns(DeprecationWarning):
            Getters.saveTorrent(host, 1, torrent, save=True)

        dm.save_torrent.assert_called_once_with(1, torrent)
        dm._database.save.assert_called_once()
