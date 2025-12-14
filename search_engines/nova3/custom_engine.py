import glob
import multiprocessing
import os
import queue
import sys
import threading
import urllib.parse
from os import path

try:
    from . import engines
except ImportError:
    sys.path.append(os.path.dirname(__file__))
    import engines

import novaprinter

try:
    from ...classes import Magnet, Torrent
except ImportError:
    from classes import Magnet, Torrent

THREADED = False
try:
    MAX_THREADS = multiprocessing.cpu_count()
except NotImplementedError:
    MAX_THREADS = 1


def initialize_engines():
    """Import available engines

    Return list of available engines
    """
    supported_engines = []

    engines_list = glob.glob(path.join(path.dirname(__file__), "engines", "*.py"))
    for engine in engines_list:
        engi = path.basename(engine).split(".")[0].strip()
        if len(engi) == 0 or engi.startswith("_"):
            continue
        try:
            # import engines.[engine]
            # engine_module = getattr(engines, engi) -> Doesn't work with pyinstaller
            exec(f"from engines import {engi}")
            engine_module = locals()[engi]

            # get low-level module
            engine_class = getattr(engine_module, engi)
            # bind class name
            globals()[engi] = engine_class
            supported_engines.append(engi)
        except Exception as e:
            # TODO - Logging
            pass

    return supported_engines


def engines_to_xml(supported_engines):
    """Generates xml for supported engines"""
    tab = " " * 4

    for short_name in supported_engines:
        search_engine = globals()[short_name]()

        supported_categories = ""
        if hasattr(search_engine, "supported_categories"):
            supported_categories = " ".join(
                (
                    key
                    for key in search_engine.supported_categories.keys()
                    if key != "all"
                )
            )

        # data = "".join((tab, "<", short_name, ">\n",
        #                tab, tab, "<name>", search_engine.name, "</name>\n",
        #                tab, tab, "<url>", search_engine.url, "</url>\n",
        #                tab, tab, "<categories>", supported_categories, "</categories>\n",
        #                tab, "</", short_name, ">\n"))

        data = {
            "short_name": short_name,
            "name": search_engine.name,
            "url": search_engine.url,
            "categories": supported_categories,
        }
        yield data


def displayCapabilities(supported_engines):
    return [e for e in engines_to_xml(supported_engines)]


def run_search(engine_list):
    """Run search in engine

    @param engine_list List with engine, query and category

    @retval False if any exceptions occurred
    @retval True  otherwise
    """
    name, engine_class, what = engine_list
    cat = "anime"  # {'all', 'movies', 'tv', 'music', 'games', 'anime', 'software', 'pictures', 'books'}
    try:
        novaprinter.prettyPrinter.output = run_search.out
        engine = engine_class()

        # avoid exceptions due to invalid category
        if hasattr(engine, "supported_categories"):
            if cat in engine.supported_categories:
                engine.search(what, cat)
        else:
            engine.search(what)

        run_search.out({"search_done": True, "engine": name, "error": None})
        return True
    except Exception as e:
        run_search.out({"search_done": True, "engine": name, "error": str(e)})
        return False


def f_init(search_id, out):
    run_search.out = lambda torrent: out.put((search_id, torrent))


def search(terms, engines=None):
    supported_engines = initialize_engines()
    # terms = terms[-1:]

    # capabilities = displayCapabilities(supported_engines)

    if engines is None:
        engines_list = supported_engines
    else:
        engines_list = [
            engine
            for engine in set(e.strip().lower() for e in engines)
            if engine in supported_engines
        ]

    if not engines_list:
        # engine list is empty. Nothing to do here
        return None, engines_list

    m = multiprocessing.Manager()
    out = m.Queue()

    terms = [urllib.parse.quote(term) for term in terms if len(term) > 5]

    def search_thread(search_id):
        if THREADED:
            pool = multiprocessing.Pool
        else:
            pool = multiprocessing.pool.ThreadPool

        with pool(
            min(len(engines_list), MAX_THREADS), f_init, [search_id, out]
        ) as pool:
            args = (
                [engine, globals()[engine], term]
                for engine in engines_list
                for term in terms
            )
            pool.map(run_search, args)

    engines_pool = {engine: len(terms) for engine in engines_list}

    search_id = hash(
        "\n".join(map(str, sorted(terms)))
    )  # Should be unique for any list of terms

    t = threading.Thread(target=search_thread, args=(search_id,))
    t.start()

    # f = lambda e, l: str(e)[:l].ljust(l)

    while True:
        try:
            s_id, torrent = out.get()
        except EOFError:
            break
        else:
            if s_id != search_id:
                print("Invalid search id:", s_id, search_id)
                out.put((s_id, torrent))

                if len(engines_pool) == 0:
                    # This should avoid infinite loops
                    # But we might have a VERY fast loop sometimes, might want to fix that too
                    break
                else:
                    continue

            if torrent.get("search_done") == True:
                engine = torrent["engine"]
                if engines_pool.get(engine, 0) > 0:
                    try:
                        # print('Done:', engine, '- Error:', a.get('error'))
                        # print(sum(engines_pool.values()), list(engines_pool.items())[:2])
                        engines_pool[engine] -= 1
                        if engines_pool[engine] <= 0:
                            del engines_pool[engine]
                    except ValueError:
                        # Value probably already deleted by another process
                        pass

                # print(engine)
                if len(engines_pool) == 0:
                    break

            else:
                torrent["link"] = Magnet(
                    torrent["link"], torrent["engine_url"], download_torrent
                )
                try:
                    torrent["seeds"] = int(torrent["seeds"] or 0)
                    torrent["leech"] = int(torrent["leech"] or 0)
                except Exception as e:
                    # a['seeds'], a['leech'] = 0, 0
                    pass
                else:
                    # l = (f(a.get('name','Nan'),75), f(a.get('size','Nan'),10), f(a.get('seeds','Nan'),5), f(a.get('leech','Nan'),5), f(a['engine_url'], 50))
                    # file.write(";".join(l) + "\n")

                    try:
                        torrent = Torrent(**torrent)
                    except Exception as e:
                        print(e)

                    yield torrent
    print("Done all")


def download_torrent(engine_url, url):
    engines_list = glob.glob(os.path.join(os.path.dirname(__file__), "engines", "*.py"))

    for engine in engines_list:
        e = engine.split(os.sep)[-1][:-3]
        if len(e.strip()) == 0:
            continue
        if e.startswith("_"):
            continue
        try:
            engine_module = getattr(engines, e)
            engine_class = getattr(engine_module, e)

            if engine_class.url == engine_url:
                que = queue.Queue()  # Redirect print inside of module
                engine_module.print = lambda *args, **kwargs: que.put(args)

                engine = engine_class()
                try:
                    engine.download_torrent(url)

                    url = que.get_nowait()
                    return " ".join(url)
                except (
                    queue.Empty
                ) as e:  # Memorial pour les 2h+ passées a trouver les p*** de ()
                    return None
                except Exception as e:
                    return None

        except Exception as e:
            pass


if __name__ == "__main__":
    titles = [
        "東京リベンジャーズ 聖夜決戦編",
        "Tokyo Revengers: Christmas Showdown",
        "Tokyo Revengers Season 2",
    ]
    titles = [
        "Summoned to Another World... Again?!",
        "異世界召喚は二度目です",
        "Isekai Shoukan wa Nidome desu",
        "Isekai Shoukan wa Nidome desu",
    ]
    for data in search(titles):
        print(data)
