"""Tests for ``APIUtils`` collaborator wiring and database helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from adapters.api.APIUtils import APIUtils, APICache
from adapters.legacy.legacy_classes import NoIdFound


class _FakeGetters:
  def __init__(self, database=None):
    self.settings = {}
    self._database = database or MagicMock()

  def getDatabase(self, *args, **kwargs):
    return self._database


class _FakeLogger:
  def __init__(self):
    self.calls = []

  def log(self, *args, **kwargs):
    self.calls.append((args, kwargs))


def _make_apiutils(**kwargs):
    database = kwargs.pop("database", MagicMock())
    getters = _FakeGetters(database=database)
    logger = _FakeLogger()
    u = APIUtils(getters=getters, logger=logger)
    u.apiKey = kwargs.get("api_key", "mal_id")
    if "database" in kwargs:
        u.database = kwargs["database"]
    return u


class TestAPIUtilsCollaborators:
    def test_log_delegates_to_logger(self):
        u = _make_apiutils()
        u.log("TAG", "message")
        assert u._logger.calls == [(("TAG", "message"), {})]

    def test_get_database_delegates_to_getters(self):
        u = _make_apiutils()
        db = u.getDatabase(reload=True)
        assert db is u._getters._database

    def test_getattr_forwards_settings(self):
        u = _make_apiutils()
        u._getters.settings = {"k": "v"}
        assert u.settings == {"k": "v"}

    def test_getattr_private_raises(self):
        u = _make_apiutils()
        with pytest.raises(AttributeError):
            _ = u._nonexistent_private

    def test_getattr_unknown_raises(self):
        u = _make_apiutils()
        with pytest.raises(AttributeError):
            _ = u.totally_unknown_attribute_xyz

    def test_name_property(self):
        u = _make_apiutils()
        assert u.__name__ == "APIUtils"


class TestAPIUtilsGetId:
    def test_returns_external_id(self):
        db = MagicMock()
        lock = MagicMock()
        lock.__enter__ = MagicMock(return_value=None)
        lock.__exit__ = MagicMock(return_value=False)
        db.get_lock.return_value = lock
        db.sql.return_value = [(99,)]
        u = _make_apiutils(database=db)
        assert u.getId(1) == 99
        db.sql.assert_called_once()

    def test_raises_when_not_found(self):
        db = MagicMock()
        lock = MagicMock()
        lock.__enter__ = MagicMock(return_value=None)
        lock.__exit__ = MagicMock(return_value=False)
        db.get_lock.return_value = lock
        db.sql.return_value = []
        u = _make_apiutils(database=db)
        with pytest.raises(NoIdFound):
            u.getId(404)


class TestAPIUtilsRates:
    def test_get_rates_returns_value(self):
        db = MagicMock()
        lock = MagicMock()
        lock.__enter__ = MagicMock(return_value=None)
        lock.__exit__ = MagicMock(return_value=False)
        db.get_lock.return_value = lock
        db.sql.return_value = [(1.5,)]
        u = _make_apiutils(database=db)
        assert u.getRates("search") == 1.5

    def test_get_rates_returns_none_when_missing(self):
        db = MagicMock()
        lock = MagicMock()
        lock.__enter__ = MagicMock(return_value=None)
        lock.__exit__ = MagicMock(return_value=False)
        db.get_lock.return_value = lock
        db.sql.return_value = []
        u = _make_apiutils(database=db)
        assert u.getRates("search") is None

    def test_set_rates_persists(self):
        db = MagicMock()
        lock = MagicMock()
        lock.__enter__ = MagicMock(return_value=None)
        lock.__exit__ = MagicMock(return_value=False)
        db.get_lock.return_value = lock
        u = _make_apiutils(database=db)
        u.setRates("search", 42.0)
        db.sql.assert_called_once()


class TestAPIUtilsSaveHelpers:
    def test_save_relations_empty_list_returns(self):
        u = _make_apiutils()
        u.save_relations(1, [])

    def test_save_relations_inserts_new_anime_relation(self):
        db = MagicMock()
        lock = MagicMock()
        lock.__enter__ = MagicMock(return_value=None)
        lock.__exit__ = MagicMock(return_value=False)
        db.get_lock.return_value = lock
        db.getId.return_value = 5
        u = _make_apiutils(database=db)
        u.get_relations = MagicMock(return_value=[])
        rel = {"type": "anime", "name": "Sequel", "rel_id": 10}
        u.save_relations(1, [rel])
        db.execute.assert_called_once()

    def test_save_mapped_empty_returns_same_id(self):
        u = _make_apiutils()
        assert u.save_mapped(7, []) == 7

    def test_save_pictures_skips_invalid_sizes(self):
        db = MagicMock()
        db.procedure.return_value = ((), [])
        u = _make_apiutils(database=db)
        u.save_pictures(
            1,
            [
                {"url": "http://x", "size": "invalid"},
                {"url": None, "size": "small"},
                {"url": "http://ok", "size": "small"},
            ],
        )
        db.procedure.assert_called_once()

    def test_save_genres_empty_returns(self):
        u = _make_apiutils()
        u.save_genres(1, [])

    def test_save_broadcast_calls_procedure(self):
        db = MagicMock()
        db.procedure.return_value = ((), [])
        lock = MagicMock()
        lock.__enter__ = MagicMock(return_value=None)
        lock.__exit__ = MagicMock(return_value=False)
        db.get_lock.return_value = lock
        u = _make_apiutils(database=db)
        u.save_broadcast(1, 0, 12, 30)
        db.procedure.assert_called_once_with("save_broadcast", 1, 0, 12, 30)


class TestAPICacheKeyWithBody:
    def test_data_included_in_cache_key(self):
        cache = APICache()
        cache.set("http://x", "a", method="POST", data={"q": 1})
        cache.set("http://x", "b", method="POST", data={"q": 2})
        assert cache.get("http://x", method="POST", data={"q": 1}) == "a"
        assert cache.get("http://x", method="POST", data={"q": 2}) == "b"
