import inspect
import os
import time
from unittest.mock import patch

import pytest

from animeAPI import AnilistCo, JikanMoe, KitsuIo, MyAnimeListNet
from tests.unit.animeAPI.test_common_api_suite import DummyDB

API_MODULES = [AnilistCo, JikanMoe, KitsuIo, MyAnimeListNet]


def get_wrapper_classes():
    wrappers = []
    for mod in API_MODULES:
        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if "Wrapper" in name:
                wrappers.append((name, obj))
    return wrappers


@pytest.mark.integration
@pytest.mark.timeout(30)
@pytest.mark.parametrize("name,cls", get_wrapper_classes())
def test_integration_common_methods_timings(name, cls):
    """Opt-in integration test: run against live APIs when RUN_LIVE_ANIMEAPI=1.

    This test only records and reports timings for calls; it uses DummyDB to avoid
    persisting anything. It will skip if the env var isn't set.
    """
    if os.environ.get("RUN_LIVE_ANIMEAPI", "") != "1":
        pytest.fail("Integration tests are opt-in. Set RUN_LIVE_ANIMEAPI=1 to enable.")

    # Instantiate wrapper and inject DummyDB
    try:
        api = cls()
    except NotImplementedError:
        pytest.fail(f"{name} not implemented (constructor raised NotImplementedError)")

    # Monkeypatch the API's database to DummyDB
    api.database = DummyDB()

    results = {}

    # Measure anime(id) if available
    if hasattr(api, "anime"):
        start = time.time()
        try:
            _ = api.anime(1)
        except Exception as e:
            results["anime"] = f"error: {e}"
        else:
            results["anime"] = f"{time.time()-start:.3f}s"

    # Measure searchAnime
    if hasattr(api, "searchAnime"):
        start = time.time()
        try:
            gen = api.searchAnime("naruto")
            # force iteration of a small number of items
            count = 0
            for _ in gen:
                count += 1
                if count >= 2:
                    break
        except Exception as e:
            results["searchAnime"] = f"error: {e}"
        else:
            results["searchAnime"] = f"{time.time()-start:.3f}s"

    # Measure schedule/season if present
    sched_callable = getattr(api, "schedule", None) or getattr(api, "season", None)
    if sched_callable is not None:
        start = time.time()
        try:
            gen = sched_callable()
            # iterate a single element
            try:
                next(gen)
            except StopIteration:
                pass
        except Exception as e:
            results["schedule"] = f"error: {e}"
        else:
            results["schedule"] = f"{time.time()-start:.3f}s"

    # Print a concise report (pytest will capture it)
    print(f"Integration timings for {name}: {results}")
