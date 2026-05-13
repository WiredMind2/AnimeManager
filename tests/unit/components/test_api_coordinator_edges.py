"""Edge-case unit tests for ``application.services.api_coordinator.APICoordinator``.

Pure unit-level: fakes the API facade, pipeline and DB manager.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def APICoordinator():
    from application.services.api_coordinator import APICoordinator as _C

    return _C


@pytest.fixture
def RateLimiter():
    from application.services.api_coordinator import RateLimiter as _R

    return _R


def _silent_logger(*_a, **_kw):
    return None


class _FakeAPI:
    """Minimal fake of `adapters.api.AnimeAPI`."""

    def __init__(self, providers=None, raises=False):
        self._providers = list(providers or [])
        self._raises = raises

    def get_providers(self):
        return list(self._providers)

    def searchAnime(self, terms, limit=50):
        if self._raises:
            raise RuntimeError("legacy boom")
        return SimpleNamespace(empty=lambda: False)


class _FakeProvider:
    def __init__(self, name, items=()):
        self.__name__ = name
        self._items = list(items)

    def searchAnime(self, terms, limit=50):
        for x in self._items[:limit]:
            yield x


def _coord(APICoordinator, api=None, db=None, max_workers=2):
    c = APICoordinator(max_workers=max_workers, provider_timeout_s=1.0)
    c.log = _silent_logger
    if api is not None:
        c.set_api(api)
    if db is not None:
        c.set_database_manager(db)
    return c


# ---------------------------------------------------------------------------
# RateLimiter edges
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_default_limit_is_60(self, RateLimiter):
        rl = RateLimiter()
        assert rl.requests_per_minute == 60

    def test_zero_rate_limits_immediately(self, RateLimiter):
        rl = RateLimiter(requests_per_minute=0)
        assert rl.allow_request() is False

    def test_low_rate_blocks_after_quota(self, RateLimiter):
        rl = RateLimiter(requests_per_minute=2)
        assert rl.allow_request() is True
        assert rl.allow_request() is True
        assert rl.allow_request() is False

    def test_stale_entries_are_pruned(self, RateLimiter):
        rl = RateLimiter(requests_per_minute=1)
        # Insert a stale entry from 5 minutes ago.
        rl.requests.append(time.time() - 300)
        assert rl.allow_request() is True


# ---------------------------------------------------------------------------
# Search guards
# ---------------------------------------------------------------------------


class TestSearchAnimeGuards:
    def test_no_api_returns_none(self, APICoordinator):
        c = _coord(APICoordinator)
        try:
            assert c.search_anime("naruto") is None
        finally:
            c.close()

    def test_short_terms_returns_none(self, APICoordinator):
        c = _coord(APICoordinator, api=_FakeAPI([]))
        try:
            assert c.search_anime("") is None
            assert c.search_anime("  ") is None
            assert c.search_anime("ab") is None
        finally:
            c.close()

    def test_rate_limit_returns_none(self, APICoordinator):
        c = _coord(APICoordinator, api=_FakeAPI([]))
        c._rate_limiter.allow_request = MagicMock(return_value=False)
        try:
            assert c.search_anime("naruto") is None
        finally:
            c.close()

    def test_search_exception_returns_none(self, APICoordinator):
        c = _coord(APICoordinator, api=_FakeAPI([], raises=False))
        with patch.object(c, "_perform_api_search", side_effect=RuntimeError("boom")):
            try:
                assert c.search_anime("naruto") is None
            finally:
                c.close()

    def test_legacy_branch_used_when_flag_off(self, APICoordinator):
        c = _coord(APICoordinator, api=_FakeAPI([]))
        c.configure({"new_ingestion_pipeline": False})
        try:
            with patch.object(c._api, "searchAnime", return_value=[1, 2, 3]) as m:
                result = c.search_anime("naruto")
                assert result is not None
                m.assert_called_once()
        finally:
            c.close()

    def test_legacy_branch_when_api_has_no_get_providers(self, APICoordinator):
        api = SimpleNamespace(
            searchAnime=lambda terms, limit=50: [1, 2],
        )
        c = _coord(APICoordinator, api=api)
        try:
            assert c.search_anime("naruto") is not None
        finally:
            c.close()


# ---------------------------------------------------------------------------
# Pipeline path
# ---------------------------------------------------------------------------


class TestPipelineSearch:
    def test_empty_providers_returns_none(self, APICoordinator):
        c = _coord(APICoordinator, api=_FakeAPI([]))
        try:
            result = c.search_anime("naruto")
            assert result is None
        finally:
            c.close()

    def test_pipeline_failed_status_returns_none(self, APICoordinator):
        c = _coord(APICoordinator, api=_FakeAPI([_FakeProvider("Jikan")]))

        from shared.contracts import IngestionResult, IngestionStatus

        bad_result = IngestionResult(
            status=IngestionStatus.FAILED,
            records=[],
            failed_providers=1,
            total_providers=1,
            elapsed_ms=10,
        )
        try:
            with patch.object(c._pipeline, "run", return_value=bad_result):
                assert c.search_anime("naruto") is None
        finally:
            c.close()

    def test_pipeline_success_no_records_returns_none(self, APICoordinator):
        c = _coord(APICoordinator, api=_FakeAPI([_FakeProvider("Jikan")]))

        from shared.contracts import IngestionResult, IngestionStatus

        ok_empty = IngestionResult(
            status=IngestionStatus.COMPLETE,
            records=[],
            failed_providers=0,
            total_providers=1,
            elapsed_ms=10,
        )
        try:
            with patch.object(c._pipeline, "run", return_value=ok_empty):
                assert c.search_anime("naruto") is None
        finally:
            c.close()

    def test_pipeline_success_with_records_returns_animelist(self, APICoordinator):
        """Regression: ``search_anime`` must not crash when the pipeline
        returns an ``AnimeList`` (which intentionally has no ``__len__``).

        Previously ``search_anime`` unconditionally called ``len(results)``
        for its summary log line and raised ``TypeError`` for any non-empty
        pipeline result. The fix logs without a count when the result
        container is not sized.
        """
        c = _coord(APICoordinator, api=_FakeAPI([_FakeProvider("Jikan")]))

        from shared.contracts import AnimeRecord, IngestionResult, IngestionStatus, ProviderName

        rec = AnimeRecord(id=1, title="Naruto", source_provider=ProviderName.UNKNOWN)
        ok = IngestionResult(
            status=IngestionStatus.COMPLETE,
            records=[rec],
            failed_providers=0,
            total_providers=1,
            elapsed_ms=10,
        )
        try:
            with patch.object(c._pipeline, "run", return_value=ok):
                animelist = c.search_anime("naruto")
                assert animelist is not None
        finally:
            c.close()

    def test_pipeline_logs_count_when_results_are_sized(self, APICoordinator):
        """If the legacy / sized result path is taken, the outer log line
        still surfaces the count. Regression-guards both branches of the
        ``len(results)`` fallback added for the AnimeList fix."""
        c = _coord(APICoordinator, api=_FakeAPI([]))
        c.configure({"new_ingestion_pipeline": False})
        messages: List[str] = []
        c.log = lambda _tag, msg: messages.append(msg)
        try:
            with patch.object(c._api, "searchAnime", return_value=[1, 2, 3]):
                result = c.search_anime("naruto")
            assert result == [1, 2, 3]
            assert any("Found 3 results" in m for m in messages), messages
        finally:
            c.close()

    def test_pipeline_logs_without_count_when_results_are_unsized(self, APICoordinator):
        """The non-sized branch of the new fallback must log a generic
        message rather than crash."""
        c = _coord(APICoordinator, api=_FakeAPI([]))
        c.configure({"new_ingestion_pipeline": False})
        messages: List[str] = []
        c.log = lambda _tag, msg: messages.append(msg)

        class _UnsizedTruthy:
            def __bool__(self):
                return True

        unsized = _UnsizedTruthy()
        try:
            with patch.object(c._api, "searchAnime", return_value=unsized):
                result = c.search_anime("naruto")
            assert result is unsized
            assert any("Search returned results" in m for m in messages), messages
        finally:
            c.close()

    def test_pipeline_success_returns_animelist_directly_through_internal(self, APICoordinator):
        """Verify the pipeline-internal path produces a valid AnimeList object.

        We avoid the buggy ``len(results)`` log call by exercising
        :meth:`_search_via_pipeline` directly.
        """
        c = _coord(APICoordinator, api=_FakeAPI([_FakeProvider("Jikan")]))

        from shared.contracts import AnimeRecord, IngestionResult, IngestionStatus, ProviderName

        rec = AnimeRecord(id=1, title="Naruto", source_provider=ProviderName.UNKNOWN)
        ok = IngestionResult(
            status=IngestionStatus.COMPLETE,
            records=[rec],
            failed_providers=0,
            total_providers=1,
            elapsed_ms=10,
        )
        try:
            with patch.object(c._pipeline, "run", return_value=ok):
                result = c._search_via_pipeline("naruto", 10)
                assert result is not None
        finally:
            c.close()

    def test_sink_disabled_when_flag_off(self, APICoordinator):
        c = _coord(APICoordinator, api=_FakeAPI([_FakeProvider("J")]))
        c.configure({"db_gateway_writes_only": False})

        captured = {}

        from shared.contracts import IngestionResult, IngestionStatus

        ok = IngestionResult(
            status=IngestionStatus.COMPLETE,
            records=[],
            failed_providers=0,
            total_providers=1,
            elapsed_ms=10,
        )

        def fake_run(specs, terms, limit, sink):
            captured["sink"] = sink
            return ok

        try:
            with patch.object(c._pipeline, "run", side_effect=fake_run):
                c.search_anime("naruto")
            assert captured["sink"] is None
        finally:
            c.close()

    def test_provider_is_none_is_skipped(self, APICoordinator):
        c = _coord(APICoordinator, api=_FakeAPI([None, _FakeProvider("J")]))

        from shared.contracts import IngestionResult, IngestionStatus

        ok = IngestionResult(
            status=IngestionStatus.COMPLETE,
            records=[],
            failed_providers=0,
            total_providers=1,
            elapsed_ms=10,
        )
        captured = {}

        def fake_run(specs, terms, limit, sink):
            captured["specs"] = list(specs)
            return ok

        try:
            with patch.object(c._pipeline, "run", side_effect=fake_run):
                c.search_anime("naruto")
            assert len(captured["specs"]) == 1
        finally:
            c.close()


# ---------------------------------------------------------------------------
# Adapter / record conversion
# ---------------------------------------------------------------------------


class TestLegacyAdapter:
    def test_none_returns_none(self, APICoordinator):
        assert APICoordinator._legacy_adapter(None) is None

    def test_missing_id_returns_none(self, APICoordinator):
        raw = SimpleNamespace(title="x")
        assert APICoordinator._legacy_adapter(raw) is None

    def test_non_int_id_returns_none(self, APICoordinator):
        raw = SimpleNamespace(id="not-int", title="x")
        assert APICoordinator._legacy_adapter(raw) is None

    def test_int_id_returns_record(self, APICoordinator):
        raw = SimpleNamespace(id=42, title="naruto")
        rec = APICoordinator._legacy_adapter(raw)
        assert rec is not None
        assert rec.id == 42
        assert rec.title == "naruto"

    def test_str_int_id_coerced(self, APICoordinator):
        raw = SimpleNamespace(id="42", title="naruto")
        rec = APICoordinator._legacy_adapter(raw)
        assert rec is not None
        assert rec.id == 42

    def test_no_title_uses_empty(self, APICoordinator):
        raw = SimpleNamespace(id=1)
        rec = APICoordinator._legacy_adapter(raw)
        assert rec is not None
        assert rec.title == ""

    def test_non_string_str_fields_cleaned(self, APICoordinator):
        raw = SimpleNamespace(
            id=1, title="x",
            status="     ", rating="OK",
            picture="", trailer="",
            broadcast="    air    ",
        )
        rec = APICoordinator._legacy_adapter(raw)
        assert rec is not None
        # _safe_str returns None for empty after strip.
        assert rec.status is None
        assert rec.rating == "OK"
        assert rec.picture is None
        assert rec.trailer is None
        # Whitespace stripped but content preserved.
        assert rec.broadcast == "air"

    def test_non_int_episodes_coerced_to_none(self, APICoordinator):
        raw = SimpleNamespace(id=1, title="x", episodes="abc")
        rec = APICoordinator._legacy_adapter(raw)
        assert rec is not None
        assert rec.episodes is None


class TestRecordToAnime:
    def test_skips_none_fields(self, APICoordinator):
        from shared.contracts import AnimeRecord, ProviderName

        rec = AnimeRecord(id=1, title="x", source_provider=ProviderName.UNKNOWN)
        anime = APICoordinator._record_to_anime(rec)
        # id and title should be set; other Nones not assigned.
        assert anime.id == 1
        assert anime.title == "x"


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_close_idempotent(self, APICoordinator):
        c = _coord(APICoordinator)
        c.close()
        c.close()

    def test_configure_with_none_falls_back_to_empty(self, APICoordinator):
        c = _coord(APICoordinator)
        try:
            c.configure(None)  # type: ignore[arg-type]
            assert c._feature_flags["new_ingestion_pipeline"] is True
        finally:
            c.close()

    def test_configure_ignores_unknown_keys_safely(self, APICoordinator):
        c = _coord(APICoordinator)
        try:
            c.configure({"unknown_flag": True})
            assert c._feature_flags.get("unknown_flag") is True
        finally:
            c.close()

    def test_set_api_db_overrides(self, APICoordinator):
        c = _coord(APICoordinator)
        try:
            c.set_api("api1")
            assert c._api == "api1"
            c.set_api("api2")
            assert c._api == "api2"
            c.set_database_manager("db1")
            assert c._database_manager == "db1"
        finally:
            c.close()


# ---------------------------------------------------------------------------
# Sink
# ---------------------------------------------------------------------------


class TestSink:
    def test_build_sink_no_db_returns_none(self, APICoordinator):
        c = _coord(APICoordinator)
        try:
            assert c._build_sink() is None
        finally:
            c.close()

    def test_build_sink_persists_via_db(self, APICoordinator):
        from shared.contracts import AnimeRecord, ProviderName

        db = MagicMock()
        db.upsert_anime_batch.return_value = 2
        c = _coord(APICoordinator, db=db)
        try:
            sink = c._build_sink()
            rec1 = AnimeRecord(id=1, title="a", source_provider=ProviderName.UNKNOWN)
            rec2 = AnimeRecord(id=2, title="b", source_provider=ProviderName.UNKNOWN)
            count = sink([rec1, rec2])
            assert count == 2
            db.upsert_anime_batch.assert_called_once()
        finally:
            c.close()

    def test_build_sink_swallows_db_exceptions(self, APICoordinator):
        from shared.contracts import AnimeRecord, ProviderName

        db = MagicMock()
        db.upsert_anime_batch.side_effect = RuntimeError("oops")
        c = _coord(APICoordinator, db=db)
        try:
            sink = c._build_sink()
            rec = AnimeRecord(id=1, title="x", source_provider=ProviderName.UNKNOWN)
            assert sink([rec]) == 0
        finally:
            c.close()


# ---------------------------------------------------------------------------
# Provider spec
# ---------------------------------------------------------------------------


class TestSpecFor:
    def test_provider_without_search_returns_empty(self, APICoordinator):
        provider = SimpleNamespace()
        c = _coord(APICoordinator)
        try:
            spec = c._spec_for(provider)
            assert list(spec.search("naruto", 5)) == []
        finally:
            c.close()

    def test_provider_with_search_returns_items(self, APICoordinator):
        provider = _FakeProvider("test", items=[1, 2, 3])
        c = _coord(APICoordinator)
        try:
            spec = c._spec_for(provider)
            out = list(spec.search("x", 5))
            assert out == [1, 2, 3]
            assert spec.name == "test"
        finally:
            c.close()

    def test_provider_without_name_falls_back_to_type_name(self, APICoordinator):
        class _NoName:
            def searchAnime(self, terms, limit=50):
                return []

        c = _coord(APICoordinator)
        try:
            spec = c._spec_for(_NoName())
            assert spec.name == "_NoName"
        finally:
            c.close()
