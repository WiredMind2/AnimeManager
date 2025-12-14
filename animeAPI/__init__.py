import importlib
import json
import os
import queue
import sys
import threading
import time
import traceback

import requests

try:
    # Try package-relative imports first (when run as package)
    from ..classes import (Anime, AnimeList, Character, CharacterList,
                           ItemList, NoIdFound)
    from ..getters import Getters
    from ..logger import Logger, log
except ImportError:
    # Fallback to absolute imports (when run standalone)
    try:
        from import_manager import ImportManager

        ImportManager.ensure_package_path()
    except ImportError:
        # Add project root to path if ImportManager not available
        import os

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    from classes import (Anime, AnimeList, Character, CharacterList, ItemList,
                         NoIdFound)
    from getters import Getters
    from logger import Logger, log


class AnimeAPI(Getters, Logger):
    def __init__(self, apis="all", *args, **kwargs):
        super().__init__()  # logs="ALL")
        self.apis = []
        self.sql_queue = queue.Queue()
        self.init_thread = threading.Thread(
            target=self.load_apis, args=(apis, *args), kwargs=kwargs, daemon=True
        )
        self.init_thread.start()

    def __getattr__(self, name):
        if name in ("dbPath", "settings"):
            return getattr(super(), name)

        def f(*args, **kwargs):
            return self.wrapper(name, *args, **kwargs)

        return f

    def load_apis(self, apis="all", *args, **kwargs):
        if apis == "all":
            api_names = []
            # Ignore these files when loading APIs
            ignore = ("__init__.py", "APIUtils.py", "tests.py", "MyAnimeListNet.py")
            root = os.path.dirname(__file__)
            sys.path.append(root)  # TODO - Should use relative import
            for f in os.listdir(root):
                if f not in ignore and f[-3:] == ".py":
                    name = f[:-3]
                    api_names.append(name)
        else:
            api_names = apis

        for name in api_names:
            # Import the module using importlib so we can reliably get the wrapper
            # class. Try package-relative name first, then bare module name.
            module = None
            for mod_prefix in ("animeAPI", ""):
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
                    "ANIME_SEARCH", f"{cls_name} not found in module {module.__name__}"
                )
                continue

            try:
                f = cls(*args, **kwargs)
            except NotImplementedError:
                # Skip APIs that aren't implemented yet
                continue
            except Exception:
                self.log(
                    "ANIME_SEARCH",
                    f"Error while loading {name} API wrapper: \n{traceback.format_exc()}",
                )
                continue
            else:
                try:
                    f.reroute_sql_queue(self.sql_queue)
                except Exception:
                    # If the wrapper doesn't implement reroute_sql_queue, ignore
                    pass
                self.apis.append(f)

        if len(self.apis) == 0:
            self.log("ANIME_SEARCH", "No apis found!")
        else:
            self.log("ANIME_SEARCH", len(self.apis), "apis found")

    def wrapper(self, name, *args, **kwargs):
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
            except Exception as e:
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
                        "ANIME_SEARCH", "{}.{}() not found!".format(api.__name__, name)
                    )
            finally:
                if r:
                    self.log(
                        "ANIME_SEARCH",
                        "{}.{}(): {} ms".format(
                            api.__name__, name, int((time.time() - start) * 1000)
                        ),
                    )

        if self.init_thread is not None:
            self.init_thread.join()
            self.init_thread = None

        threads = []
        que = queue.Queue()
        for api in self.apis:
            t = threading.Thread(
                target=handler, args=(api, name, que, *args), kwargs=kwargs, daemon=True
            )
            t.start()
            threads.append(t)

        # for api in self.apis:
        # 	handler(api, name, que, *args, **kwargs)

        # if 'timeout' in kwargs: # Disabled
        #     delay = max(0, kwargs['timeout']) # Min 0 to loop at least once
        #     timeout = delay + time.time()
        # else:
        #     timeout = None
        #     delay = None

        out = ()
        if name in ("anime", "character"):
            if name == "anime":
                out = Anime()
            else:
                out = Character()
            r = None
            while not que.empty() or any(
                t.is_alive() for t in threads
            ):  # or (delay is not None and delay < 0):
                try:
                    r = que.get(block=True, timeout=1)  # , timeout=delay)
                except queue.Empty:
                    pass
                else:
                    out += r

                # if timeout is not None:
                #     delay = timeout - time.time()
                # else:
                #     delay = None

            if len(out) == 0:
                self.log(
                    "ANIME_SEARCH",
                    "No data - id:" + str(name) + " - args:" + ",".join(map(str, args)),
                )
        else:
            if name in ("schedule", "searchAnime", "season"):
                out = AnimeList((que, threads))
            elif name in ("animeCharacters",):
                out = CharacterList((que, threads))
            else:
                out = ItemList((que, threads))
        self.save(out)
        return out

    def save(self, data):
        database = self.getDatabase()
        if not data:
            return

        self.handle_sql_queue()

        if isinstance(data, Anime):

            data, meta = data.save_format()
            data = {k: v for k, v in data.items() if v is not None}
            args, out = database.procedure("save_anime", data["id"], json.dumps(data))

        elif isinstance(data, Character):
            table = "characters"
            raise NotImplementedError()

        elif isinstance(data, ItemList):
            data.add_callback(self.save)
            return
        else:
            raise TypeError("{} is an invalid type!".format(str(type(data))))

        # with database.get_lock():
        # 	database.set(data['id'], data, table=table)
        # 	database.save()

    def handle_sql_queue(self):
        while not self.sql_queue.empty():
            func, args, kwargs = self.sql_queue.get()
            func(*args, **kwargs)


# TODO - Add more APIs:
# nautiljon.com
# anisearch.com
