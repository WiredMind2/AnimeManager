"""Metadata provider API adapters.

This package is the **canonical** home of :class:`AnimeAPI` and the
per-provider wrappers (Anilist, Jikan, Kitsu, MyAnimeList). The
legacy ``animeAPI`` package is a thin compatibility shim that
re-exports from here and emits a ``DeprecationWarning`` on import.
"""

from __future__ import annotations

import importlib
import json
import os
import queue
import sys
import threading
import time
import traceback

import requests

_MISSING = object()

try:
    from adapters.persistence.models import (
        Anime,
        AnimeList,
        Character,
        CharacterList,
        ItemList,
        NoIdFound,
    )
    from shared.config.getters import Getters
    from shared.telemetry.logger import Logger, log
except ImportError:  # pragma: no cover - packaged install fallback
    try:
        from shared.utils.import_manager import ImportManager

        ImportManager.ensure_package_path()
    except ImportError:
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    from AnimeManager.adapters.persistence.models import (  # type: ignore
        Anime,
        AnimeList,
        Character,
        CharacterList,
        ItemList,
        NoIdFound,
    )
    from AnimeManager.shared.config.getters import Getters  # type: ignore
    from AnimeManager.shared.telemetry.logger import Logger, log  # type: ignore


class AnimeAPI:
    """Facade aggregating individual provider wrappers under
    ``adapters.api/``.

    ADR 0005 update: ``AnimeAPI`` no longer inherits from
    :class:`Getters` / :class:`Logger`. The legacy mixin methods are
    available through the composed ``self._getters`` and
    ``self._logger`` collaborators, with :meth:`log`, :meth:`getDatabase`
    and other commonly-used helpers forwarded for backwards-compatible
    call sites.

    The new code path exposes loaded providers via :meth:`get_providers`
    and lets :class:`components.api_coordinator.APICoordinator` drive
    the search fan-out. The legacy ``__getattr__`` -> :meth:`wrapper`
    thread-pool path is still used for non-search calls (``anime``,
    ``character``, ``schedule``, ``season``, etc.).
    """

    def __init__(
        self,
        apis="all",
        *args,
        getters=None,
        logger=None,
        **kwargs,
    ):
        self._getters = getters if getters is not None else Getters()
        self._logger = logger if logger is not None else Logger()
        self._write_service = None
        self.apis = []
        self.sql_queue = queue.Queue()
        self.init_thread = threading.Thread(
            target=self.load_apis,
            args=(apis, *args),
            kwargs=kwargs,
            daemon=True,
        )
        self.init_thread.start()

    # --- Composed collaborator forwarding -------------------------------
    def log(self, *args, **kwargs):
        """Forward to the composed :class:`Logger` collaborator."""
        return self._logger.log(*args, **kwargs)

    def getDatabase(self, *args, **kwargs):
        """Forward to the composed :class:`Getters` collaborator."""
        return self._getters.getDatabase(*args, **kwargs)

    @property
    def settings(self):
        return self._getters.settings

    @property
    def dbPath(self):
        return self._getters.dbPath

    def set_write_service(self, write_service):
        """Attach centralized anime write gateway used by ``save``."""
        self._write_service = write_service

    def __getattr__(self, name):
        # ``__getattr__`` is only consulted when normal lookup fails, so
        # this path also acts as a generic forwarder to the composed
        # ``Getters`` collaborator (for ``setSettings``, ``saveAnime``,
        # ``saveCharacter``, etc.) -- preserving the legacy API.
        if name.startswith("_"):
            raise AttributeError(name)

        getters = self.__dict__.get("_getters")
        if getters is not None:
            attr = getattr(getters, name, _MISSING)
            if attr is not _MISSING:
                return attr

        # Fallback: schedule the call against the provider fan-out
        # thread-pool (legacy ``self.foo(...)`` -> ``self.wrapper("foo")``)
        def f(*args, **kwargs):
            return self.wrapper(name, *args, **kwargs)

        return f

    def load_apis(self, apis="all", *args, **kwargs):
        if apis == "all":
            api_names = []
            ignore = (
                "__init__.py",
                "APIUtils.py",
                "provider_payload.py",
                "tests.py",
                "MyAnimeListNet.py",
            )
            root = os.path.dirname(__file__)
            sys.path.append(root)  # legacy fallback for bare-name imports
            for f in os.listdir(root):
                if f not in ignore and f[-3:] == ".py":
                    name = f[:-3]
                    api_names.append(name)
        else:
            api_names = apis

        for name in api_names:
            module = None
            for mod_prefix in ("adapters.api", "animeAPI", ""):
                mod_name = f"{mod_prefix}.{name}" if mod_prefix else name
                try:
                    module = importlib.import_module(mod_name)
                except Exception:
                    module = None
                    continue
                else:
                    break
            if module is None:
                self.log("ANIME_SEARCH", name, "module import failed")
                continue

            cls_name = name + "Wrapper"
            cls = getattr(module, cls_name, None)
            if cls is None:
                self.log(
                    "ANIME_SEARCH",
                    f"{cls_name} not found in module {module.__name__}",
                )
                continue

            try:
                instance = cls(*args, **kwargs)
            except NotImplementedError:
                continue
            except Exception:
                self.log(
                    "ANIME_SEARCH",
                    f"Error while loading {name} API wrapper: \n{traceback.format_exc()}",
                )
                continue
            else:
                try:
                    instance.reroute_sql_queue(self.sql_queue)
                except Exception:
                    pass
                self.apis.append(instance)

        if len(self.apis) == 0:
            self.log("ANIME_SEARCH", "No apis found!")
        else:
            self.log("ANIME_SEARCH", len(self.apis), "apis found")

    def wrapper(self, name, *args, **kwargs):
        persist = kwargs.pop("_persist", None)

        def handler(api, name, que, *args, **kwargs):
            try:
                f = getattr(api, name)
            except AttributeError as e:
                self.log(
                    "ANIME_SEARCH",
                    "{} has no attribute {}! - Error: \n{}".format(
                        api.__name__, name, e
                    ),
                )
                return

            start = time.time()
            r = None
            try:
                r = f(*args, **kwargs)
            except NoIdFound:
                pass
            except Exception:
                self.log(
                    "ANIME_SEARCH",
                    "Error on API - handler:",
                    api.__name__,
                    "\n",
                    traceback.format_exc(),
                )
            else:
                if r is not None:
                    que.put(r)
                else:
                    self.log(
                        "ANIME_SEARCH",
                        "{}.{}() not found!".format(api.__name__, name),
                    )
            finally:
                if r:
                    self.log(
                        "ANIME_SEARCH",
                        "{}.{}(): {} ms".format(
                            api.__name__,
                            name,
                            int((time.time() - start) * 1000),
                        ),
                    )

        if self.init_thread is not None:
            self.init_thread.join()
            self.init_thread = None

        threads = []
        que = queue.Queue()
        for api in self.apis:
            t = threading.Thread(
                target=handler,
                args=(api, name, que, *args),
                kwargs=kwargs,
                daemon=True,
            )
            t.start()
            threads.append(t)

        out = ()
        if name in ("anime", "character"):
            if name == "anime":
                out = Anime()
            else:
                out = Character()
            r = None
            while not que.empty() or any(t.is_alive() for t in threads):
                try:
                    r = que.get(block=True, timeout=1)
                except queue.Empty:
                    pass
                else:
                    out += r

            if len(out) == 0:
                self.log(
                    "ANIME_SEARCH",
                    "No data - id:"
                    + str(name)
                    + " - args:"
                    + ",".join(map(str, args)),
                )
        else:
            if name in ("schedule", "searchAnime", "season"):
                out = AnimeList((que, threads))
            elif name in ("animeCharacters",):
                out = CharacterList((que, threads))
            else:
                out = ItemList((que, threads))
        if persist is None:
            # Keep direct entity persistence (single anime/character
            # lookups) but never auto-persist streaming list responses;
            # the coordinator now owns that path through
            # DatabaseManager.
            persist = name in ("anime", "character")
        if persist:
            self.save(out)
        return out

    def get_providers(self):
        """Return loaded provider wrapper instances."""
        if self.init_thread is not None:
            self.init_thread.join()
            self.init_thread = None
        return tuple(self.apis)

    def search_provider(self, provider, terms, limit=50):
        """Execute search directly on one provider wrapper."""
        if not hasattr(provider, "searchAnime"):
            return iter(())
        return provider.searchAnime(terms, limit=limit)

    def save(self, data):
        if not data:
            return

        self.handle_sql_queue()

        if isinstance(data, Anime):
            write_service = getattr(self, "_write_service", None)
            if write_service is not None:
                from application.services.anime_write_service import WriteSource

                write_service.persist_legacy_anime(
                    data,
                    source=WriteSource.HYDRATION,
                    catalog_id=getattr(data, "id", None),
                )
                return

            database = self.getDatabase()
            data, meta = data.save_format()
            data = {k: v for k, v in data.items() if v is not None}
            args, out = database.procedure(
                "save_anime", data["id"], json.dumps(data)
            )
            if meta:
                database.save_metadata(data["id"], meta)

        elif isinstance(data, Character):
            raise NotImplementedError()

        elif isinstance(data, ItemList):
            data.add_callback(self.save)
            return
        else:
            raise TypeError("{} is an invalid type!".format(str(type(data))))

    def handle_sql_queue(self):
        while not self.sql_queue.empty():
            func, args, kwargs = self.sql_queue.get()
            func(*args, **kwargs)


# Future provider candidates: nautiljon.com, anisearch.com.

# Re-export the provider submodules at the package level so callers
# can write ``from adapters.api import AnilistCo, JikanMoe, KitsuIo,
# MyAnimeListNet`` (matching the legacy ``animeAPI`` surface).
from . import AnilistCo, APIUtils, JikanMoe, KitsuIo, MyAnimeListNet  # noqa: E402,F401

__all__ = [
    "AnimeAPI",
    "AnilistCo",
    "APIUtils",
    "JikanMoe",
    "KitsuIo",
    "MyAnimeListNet",
]
