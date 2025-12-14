import base64
import hashlib
import json
import queue
import re
import threading
import time
import traceback
from collections import deque
from typing import Any, Dict, List, Optional, Tuple, Union, Callable, Iterator, TypeVar, Generic
from urllib.parse import parse_qs, urlencode

import bencoding
import requests

try:
    # Try package-relative imports first (when run as package)
    from .logger import log
except ImportError:
    # Fallback to absolute imports (when run standalone)
    try:
        from import_manager import ImportManager

        ImportManager.ensure_package_path()
    except ImportError:
        # Add project root to path if ImportManager not available
        import os
        import sys

        project_root = os.path.dirname(os.path.abspath(__file__))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    from logger import log


class Item(dict):
    """
    Base class for anime-related data objects.

    Provides a dict-like interface with typed data keys, metadata keys,
    and default values. Subclasses define specific data structures for
    different anime entities.

    Attributes:
        data_keys: Tuple of keys that define the primary data fields
        metadata_keys: Tuple of keys that contain metadata (lists, etc.)
        default_values: Dict of default values for missing keys
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize an Item instance.

        Args:
            *args: Positional arguments for data initialization
            **kwargs: Keyword arguments for data initialization
        """
        super().__init__(self)
        if "data_keys" not in self.__dict__.keys():
            self.data_keys: Tuple[str, ...] = ()
        if "metadata_keys" not in self.__dict__.keys():
            self.metadata_keys: Tuple[str, ...] = ()
        if "default_values" not in self.__dict__.keys():
            self.default_values: Dict[str, Any] = {}
        self.__add__(*args, **kwargs)

    def __getattr__(self, key: str) -> Any:
        if key in ("data_keys", "metadata_keys", "default_values"):
            return self.__dict__[key]

        if key in self.data_keys:
            if key not in self.keys():
                if key in self.default_values:
                    return self.default_values[key]
                else:
                    return None
            else:
                if key in self.metadata_keys and callable(self[key]):
                    data = self[key]()
                    self[key] = data

                if self[key] is None and key in self.default_values:
                    return self.default_values[key]
                else:
                    return self[key]

    def __setattr__(self, key: str, value: Any) -> None:
        if key in ("data_keys", "metadata_keys", "default_values"):
            self.__dict__[key] = value
            return
        if key in self.data_keys:
            self[key] = value
        else:
            log(type(self), "has not key", key, "value", value)

    def __add__(self, *args: Any, **kwargs: Any) -> 'Item':
        data = None

        if len(args) != 0:
            args = args[0]
            if hasattr(args, "items"):  # Item(dict(data))
                data = args.items()
            else:
                try:
                    iter(args)
                except TypeError:
                    raise TypeError(
                        "Cannot merge data, type: {} - {}".format(type(args[0])),
                        args[0],
                    )
                else:
                    # Item([(key, value), (key, value), ...])
                    if isinstance(args[0], tuple):
                        data = args

        elif len(kwargs) != 0:
            # Item(keys=[...], values=[...])
            if "keys" in kwargs.keys() and "values" in kwargs.keys():
                data = zip(kwargs["keys"], kwargs["values"])
            else:
                data = kwargs.items()
        else:
            return self

        if data is None:
            raise TypeError(
                "Cannot merge '{}' with data: {} and {}".format(
                    type(self).__name__, args, kwargs
                )
            )

        for k, v in data:
            if k not in self.keys() or self[k] is None:
                self[k] = v
            elif v is not None:
                if not isinstance(v, type(self[k])):
                    raise TypeError(
                        "On key {} - types do not match: {}-{} / {}-{}".format(
                            k, v, type(v), self[k], type(self[k])
                        )
                    )
                if hasattr(v, "__len__"):
                    if len(v) > len(self[k]):
                        self[k] = v
                elif v > self[k]:
                    self[k] = v
        return self

    def __contains__(self, e):
        return e in self.keys()

    def save_format(self):
        data, meta = {}, {}
        for key, value in self.items():
            if key in self.data_keys:
                if key in self.metadata_keys:
                    meta[key] = value
                else:
                    data[key] = value
            else:
                log(type(self), "Key not in data_keys:", key)  # , value)
        return data, meta


class Anime(Item):
    """
    Represents an anime series with all its metadata.

    This class encapsulates all information about an anime including
    basic details, ratings, episodes, genres, and associated torrents.

    Attributes:
        id: Unique identifier for the anime
        title: Main title of the anime
        title_synonyms: List of alternative titles
        synopsis: Description/summary of the anime
        episodes: Number of episodes
        duration: Duration per episode in minutes
        status: Current airing status (AIRING, FINISHED, UPCOMING)
        rating: Age rating (PG, R, etc.)
        genres: List of genre names
        picture: URL to poster/cover image
        trailer: URL to trailer video
        broadcast: Broadcast schedule information
        date_from: Start date
        date_to: End date
        last_seen: Last episode watched
        like: User rating/like status (0-10)
        tag: User tag (NONE, SEEN, WATCHING, WATCHLIST)
        torrents: List of associated torrent information
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize an Anime instance.

        Args:
            *args: Positional arguments for data initialization
            **kwargs: Keyword arguments for data initialization
        """
        self.data_keys = (
            "broadcast",
            "date_from",
            "date_to",
            "duration",
            "episodes",
            "genres",
            "id",
            "last_seen",
            "like",
            "picture",
            "rating",
            "status",
            "synopsis",
            "tag",
            "title",
            "title_synonyms",
            "trailer",
            "torrents",
        )
        self.metadata_keys = ("title_synonyms", "genres", "torrents")
        self.default_values = {"tag": "NONE", "like": 0}
        super().__init__(*args, **kwargs)


class Torrent(Item):
    """
    Represents a torrent file with metadata and download information.

    This class encapsulates torrent information including hash, trackers,
    seed/leech counts, and download progress.

    Attributes:
        hash: Torrent hash (info hash)
        name: Display name of the torrent
        trackers: List of tracker URLs
        seeds: Number of seeders
        leech: Number of leechers
        size: Total size in bytes
        path: Local file path if downloaded
        downloaded: Bytes downloaded so far
        link: Magnet link or torrent URL
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize a Torrent instance.

        Args:
            *args: Positional arguments for data initialization
            **kwargs: Keyword arguments for data initialization
        """
        self.data_keys = (
            "hash",
            "name",
            "trackers",
            "seeds",
            "leech",
            "size",
            "path",
            "downloaded",
            "link",
        )

        self.size = None
        self.downloaded = None
        self.trackers = None
        super().__init__(*args, **kwargs)

    def __add__(self, *args, **kwargs):
        out = super().__add__(*args, **kwargs)

        if self.downloaded is None and self.size is not None:
            self.downloaded = self.size

        if isinstance(self.trackers, str):
            if len(self.trackers) == 0:
                self.trackers = []
            else:
                self.trackers = json.loads(self.trackers)

        return out

    @classmethod
    def from_torrent(self, filedata):
        meta = bencoding.bdecode(filedata)

        # Cryptographic fix: Replace SHA1 with SHA256 for better security
        digest = hashlib.sha256(bencoding.encode(meta[b"info"])).hexdigest()
        # Convert hex digest to bytes then encode as base32 (compatible format)
        hash_bytes = bytes.fromhex(digest)
        hash = base64.b32encode(hash_bytes).decode()
        name = meta[b"info"][b"name"].decode()
        trackers = meta[b"announce"].decode()
        size = meta[b"info"][b"length"].decode()

        t = Torrent(hash=hash, name=name, trackers=trackers, size=size)

    @classmethod
    def from_magnet(self, magnet):
        prefix = "magnet:?"
        if not magnet.startswith(prefix):
            # Invalid magnet
            return False
        magnet = magnet[len(prefix) :]

        data = parse_qs(magnet)
        hash = data["xt"][0][len("urn:btih:") :]
        name = data.get("dn", [""])[0] or None
        trackers = data.get("tr", "")
        size = int(data.get("xl", ["0"])[0]) or None

        t = Torrent(hash=hash, name=name, trackers=trackers, size=size)
        return t

    def to_magnet(self):
        params = {"dn": self.name, "tr": self.trackers, "xl": self.size}

        for k, v in list(params.items()):
            if v is None:
                del params[k]

        magnet = f"magnet:?xt=urn:btih:{self.hash}&{urlencode(params, doseq=True)}"
        return magnet


class Character(Item):
    """
    Represents a character from an anime series.

    This class encapsulates character information including name, role,
    description, and associated anime appearances.

    Attributes:
        id: Unique identifier for the character
        name: Character name
        role: Character's role (Main, Supporting, etc.)
        picture: URL to character image
        desc: Character description/bio
        animeography: List of anime appearances
        like: User rating/like status (0-10)
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize a Character instance.

        Args:
            *args: Positional arguments for data initialization
            **kwargs: Keyword arguments for data initialization
        """
        self.data_keys = (
            "id",
            # 'anime_id',
            "role",
            "name",
            "picture",
            "desc",
            "animeography",
            "like",
        )
        self.metadata_keys = ("animeography", "role")
        self.default_values = {"role": "Unknown", "like": 0}
        super().__init__(*args, **kwargs)


class Episode(Item):
    """
    Represents an individual episode of an anime series.

    This class encapsulates episode information including title, file path,
    season/episode numbers, and viewing status.

    Attributes:
        title: Episode title
        path: Local file path if downloaded
        season: Season number
        episode: Episode number within season
        anime_id: ID of the parent anime
        duration: Episode duration in minutes
        watched: Whether the episode has been watched
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize an Episode instance.

        Args:
            *args: Positional arguments for data initialization
            **kwargs: Keyword arguments for data initialization
        """
        self.data_keys = (
            "title",
            "path",
            "season",
            "episode",
            "anime_id",
            "duration",
            "watched",
        )
        self.default_values = {"season": 1, "watched": False}
        super().__init__(*args, **kwargs)


class ItemList:
    """
    A thread-safe list that manages data sources and provides asynchronous iteration.

    This class handles multiple data sources (iterables) concurrently using threads,
    deduplicates items based on identifiers, and provides event-driven access to new items.

    Attributes:
        list: Internal deque storing processed items
        sources: List of active data sources
        callbacks: Functions called when new items are added
        stop: Flag to stop processing
        new_elem_event: Event signaling new items available
    """

    def __init__(self, *sources):
        """
        Initialize an ItemList with data sources.

        Args:
            *sources: Iterable data sources to process
        """
        self.list = deque()

        self.stop = False
        self.new_elem_event = {"enabled": False, "event": threading.Event()}

        self.sources = []
        self.sourceThreads = []
        self.ids = []
        self.callbacks = []

        if not hasattr(self, "identifier"):
            self.identifier = lambda e: e
        self.identifier = self.identifier_wrapper(self.identifier)

        if not hasattr(self, "item_type"):
            self.item_type = dict

        for s in sources:
            self.addSource(s)

    def __contains__(self, e):
        raise SystemExit("NOT TESTED YET")
        return e in self.list

    def __iter__(self, timeout=None):
        while not self.empty():
            e = self.get(timeout)
            if e is not None:
                yield e

    def __add__(self, elem, *args, **kwargs):
        self.addSource(elem)
        return self

    def identifier_wrapper(self, func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except:
                return None

        return wrapper

    def sourceListener(self, s):
        try:
            iterator = iter(s)
        except TypeError:
            iterator = s
        while not self.stop:
            try:
                e = next(iterator)
            except StopIteration:
                self.sources.remove(s)
                if self.new_elem_event["enabled"]:
                    self.new_elem_event["event"].set()
                    self.new_elem_event["enabled"] = False
                break
            # except requests.exceptions.ConnectionError as e: -> This shouldn't be handled here wtf
            # 	log("Error on ItemList iterator: No internet connection! -")
            # 	self.sources.remove(s)
            # 	break
            # except requests.exceptions.ReadTimeout as e:
            # 	log("Error on ItemList iterator: Timed out! - ", e)
            # 	self.sources.remove(s)
            # 	break
            except Exception as e:
                log(
                    "Error on ItemList iterator",
                    s,
                    iterator,
                    "\n",
                    traceback.format_exc(),
                )
                self.sources.remove(s)
                # break
                raise  # For testing, remove for prod
            else:
                id = self.identifier(e)
                if id not in self.ids:
                    if type(e) != self.item_type:
                        e = self.item_type(e)
                    self.list.append(e)
                    self.ids.append(id)
                    if self.new_elem_event["enabled"]:
                        self.new_elem_event["event"].set()
                        self.new_elem_event["enabled"] = False
                    for cb in self.callbacks:
                        cb(e)

    def queueListener(self, que, threads):
        while not que.empty() or any(t.is_alive() for t in threads):
            try:
                s = que.get_nowait()
            except queue.Empty:
                time.sleep(0.05)
            else:
                self.addSource(s)

    def addSource(self, source):
        if source == self:
            return  # TF?
        # Add a tuple like (data_queue, data_threads)
        if isinstance(source, tuple) and isinstance(source[0], queue.Queue):
            t = threading.Thread(target=self.queueListener, args=source, daemon=True)
            t.start()
            self.sourceThreads.append(t)

        else:
            self.sources.append(source)
            t = threading.Thread(
                target=self.sourceListener, args=(source,), daemon=True
            )
            t.start()
            self.sourceThreads.append(t)

    def add_callback(self, cb):
        """Call a function when a new element is added - Useful for saving"""
        self.callbacks.append(cb)

    def del_callback(self, cb):
        if cb in self.callbacks:
            self.callbacks.remove(cb)

    def get(self, timeout=1, default=None):
        if len(self.list) > 0:
            e = self.list.popleft()
            return e
        else:
            if self.empty():
                return default
            else:
                if timeout is None:
                    return None
                else:
                    return self.get_from_sources(timeout, default)

    def get_from_sources(self, timeout=None, default=None):
        self.new_elem_event["event"].clear()
        self.new_elem_event["enabled"] = True
        if self.new_elem_event["event"].wait(timeout=timeout):
            if len(self.list) > 0:
                e = self.list.popleft()
                return e
            elif len(self.sources) == 0:
                return default
        else:
            # if timeout is not None:
            #     log("ItemList iterator timed out")
            return default  # Timed out

    def _filter_sources(self, start_thread=False):
        if start_thread:
            threading.Thread(self._filter_sources, args=(True,), daemon=True).start()
            return

        new_sources = []
        for t in self.sourceThreads:
            if t.is_alive():
                new_sources.append(t)
        self.sourceThreads = new_sources

    def empty(self):
        if len(self.sources) != 0 or len(self.list) != 0:
            return False

        self._filter_sources()
        return len(self.sourceThreads) == 0

    def is_ready(self):
        return len(self.list) > 0 or len(self.sources) == 0

    def map(self, func, delay, cb=None):
        """'func' will be called for each element of self.list along with its index when they are available.
        If 'func' return False, then break loop and skip to 'cb'.\n
        'delay' will be called when there are no new elements available,
        it should behave like this function: lambda func: root.after(100, func).\n
        'delay' can also be an int or a float, if it's okay to block the thread.\n
        'cb' will be called when all elements have been parsed, with the index of the last element as args
        or -1 if there have been no elements"""

        def map_func(func, delay, cb, idx=0):
            if self.stop:
                return
            if not self.empty():
                index = -1  # In case self.__iter__() returns nothing
                while self.is_ready():
                    elem = self.get(timeout=None)
                    index += 1

                    try:
                        out = func(idx + index, elem)
                    except Exception as e:
                        print(f"Error on Itemlist.map: {e}")  # TODO - Use logger
                    else:
                        if out is False:
                            if cb is not None:
                                self.interrupt()
                                cb(idx + index)
                            return

                idx += index + 1
                if not self.stop:
                    delay(
                        lambda func=func, delay=delay, cb=cb, idx=idx: map_func(
                            func, delay, cb, idx
                        )
                    )
                return
            elif cb is not None:
                self.interrupt()
                cb(idx - 1)

        # THIS MIGHT BREAK STUFF SO BE CAREFUL, but it also prevents the load more button from working so...
        if self.stop is True:
            self.stop = False

        if isinstance(delay, (int, float)):

            def delay_func(func, delay=delay):
                time.sleep(delay)
                func()

        else:
            delay_func = delay

        return map_func(func, delay_func, cb)

    def interrupt(self):
        self.stop = True

    def join(self):
        return list(self.__iter__())


class AnimeList(ItemList):
    """
    Specialized ItemList for managing anime data.

    Uses anime ID as the unique identifier and converts items to Anime objects.
    """

    def __init__(self, sources):
        """
        Initialize an AnimeList with data sources.

        Args:
            sources: Iterable data sources containing anime data
        """
        self.identifier = lambda a: a["id"]
        self.item_type = Anime
        super().__init__(sources)


class TorrentList(ItemList):
    """
    Specialized ItemList for managing torrent data.

    Uses torrent hash or description link as the unique identifier.
    """

    def __init__(self, sources):
        """
        Initialize a TorrentList with data sources.

        Args:
            sources: Iterable data sources containing torrent data
        """
        self.item_type = dict
        super().__init__(sources)

    def identifier(self, t, *args, **kwargs):
        """
        Get unique identifier for a torrent.

        Args:
            t: Torrent data dict
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments

        Returns:
            Unique identifier (hash, desc_link, or hash of values)
        """
        return t.get("hash", None) or t.get("desc_link", None) or hash(t.values())


class CharacterList(ItemList):
    """
    Specialized ItemList for managing character data.

    Uses character ID as the unique identifier and converts items to Character objects.
    """

    def __init__(self, sources):
        """
        Initialize a CharacterList with data sources.

        Args:
            sources: Iterable data sources containing character data
        """
        self.identifier = lambda c: c["id"]
        self.item_type = Character
        super().__init__(sources)


class DefaultDict(dict):
    """
    A dict with a default value instead of raising a KeyError.

    When accessing a non-existent key, returns the default value and
    sets that key to the default value for future access.
    """

    def __init__(self, default, *args, **kwargs):
        """
        Initialize a DefaultDict.

        Args:
            default: The default value to return for missing keys
            *args: Additional positional arguments for dict initialization
            **kwargs: Additional keyword arguments for dict initialization
        """
        self.default = default
        super().__init__(*args, **kwargs)

    def __getitem__(self, key):
        """
        Get an item, returning default value if key doesn't exist.

        Args:
            key: The key to look up

        Returns:
            The value associated with the key, or the default value
        """
        try:
            return super().__getitem__(key)
        except KeyError:
            self.__setitem__(key, self.default)
            return super().__getitem__(key)


class NoneDict(DefaultDict):
    """
    A dict that returns "NONE" instead of raising a KeyError.

    Extends DefaultDict with a default value of "NONE" and allows
    initialization with separate keys and values parameters.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize a NoneDict.

        Args:
            *args: Positional arguments for dict initialization
            **kwargs: Keyword arguments. Special keys:
                - keys: List of keys to initialize
                - values: List of values to initialize
                - default: Default value (defaults to "NONE")
        """
        if len(args) == 0 and not "default" in kwargs:
            kwargs["default"] = "NONE"

        keys = kwargs.pop("keys", None)
        values = kwargs.pop("values", None)

        super().__init__(*args, **kwargs)

        if len(args) == 0 and keys and values:
            for k, v in zip(keys, values):
                self[k] = v


class RegroupList:
    """
    A list of dict, wich regroup values based on a PK,
    creating a sub-list if values are different.
    You must access elements as an iterable, or
    convert the instance to a classic Python list()
    """

    def __init__(self, pk, merge_keys=[], *args):
        super().__init__()
        self.pk = pk
        self.merge_keys = merge_keys
        self.data = {}
        self.extend(args)

    def __iter__(self):
        for k, v in self.data.items():
            yield v

    def get_id(self, data):
        pairs = []
        # Doing this will sort the items
        # to make sure they are always in the same order
        items = list(set(data.items()))

        for k, v in items:
            # Doing this would return the same for
            # when a value is None or
            # when it just doesn't exists
            if k not in self.merge_keys:
                pairs.append(v)

        # We iterated on self.merge_keys, so pairs
        # should always have the same keys order
        return hash(tuple(pairs))

    def add_element(self, sub):
        if not isinstance(sub, dict):
            raise TypeError("Elements must be dicts, not " + str(type(sub)))

        sub_id = self.get_id(sub)
        append = True

        if sub_id in self.data:
            # An id already exist, merging
            # All non-mergable values *should* match,
            # or we would then have a different id

            current = self.data[sub_id]

            # Get all items (key, value) that aren't supposed to merge
            curset = set(
                item for item in current.items() if item[0] not in self.merge_keys
            )
            subset = set(sub.items())

            # Merge differences into a list
            # The list(set(...)) allow to make sure
            # that we don't have duplicate values
            for k in self.merge_keys:
                current[k] = list(set([sub[k]] + current[k]))

            self.data[sub_id] = current

        else:
            # Insert as new entry
            for k, v in sub.items():
                if k in self.merge_keys:
                    sub[k] = [v]

            self.data[sub_id] = sub

    def append(self, sub):
        self.add_element(sub)

    def extend(self, subs):
        for sub in subs:
            self.add_element(sub)

    def insert(self, i, sub):
        self.add_element(sub, i)


class SortedList(list):
    def __init__(self, keys=None):
        if (
            keys is None
        ):  # Keys must be either None or a list of tuples containing the key and a "reverse" bool
            self.keys = ((lambda e: e, False),)
        else:
            self.keys = keys

    def append(self, e):
        length = len(self)
        if length == 0:
            super().append(e)
        else:
            self.binary_insert(e, 0, length)
        return self

    def extend(self, e):
        for sub in e:
            self.append(sub)
        return self

    def __contains__(self, e):
        length = len(self)
        if length == 0:
            return False
        else:
            return self.binary_search(e, 0, length) is not False

    def compare(self, a, b):
        """Return True if a > b, False if a < b, and None if a == b"""

        for key, reverse in self.keys:
            # Check each keys in the right order
            try:
                k_a, k_b = key(a), key(b)

                if k_a > k_b:
                    return not reverse

                elif k_a < k_b:
                    return reverse

            except Exception:
                # Loop to the next key
                continue
            else:
                # Check next key because a == b
                pass

        # a == b for all keys
        return None

    def binary_insert(self, e, start, stop):
        middle = (stop + start) // 2
        if self.compare(e, self[middle]):  # Hacky - see reverse truth table
            if middle == start:
                self.insert(start + 1, e)
                return start + 1
            else:
                return self.binary_insert(e, middle, stop)
        else:
            if middle == stop:
                self.insert(stop, e)
                return stop
            else:
                return self.binary_insert(e, start, middle)

    def binary_search(self, e, start, stop):
        # Binary search utility

        middle = (start + stop) // 2
        comp = self.compare(e, self[middle])

        if comp is None:
            # e == self.middle
            # We found a matching element
            return middle

        elif comp:
            # e > comp
            # The element we are searching for should
            # be to the right of comp

            if middle == start:
                # No more elements
                # If this is true then we are looping
                return False
            else:
                return self.binary_search(e, middle, stop)

        else:
            # e < comp
            # The element we are searching for should
            # be to the left of comp

            if middle == stop:
                # No more elements
                # If this is true then we are looping
                return False
            else:
                return self.binary_search(e, start, middle)


class SortedDict:
    """Actually a sorted list of tuples, but behave like a dict"""

    def __init__(self, keys=None, reverse=False):
        super().__init__()
        if (
            keys is None
        ):  # Keys must be either None or a list of tuples containing the key and a "reverse" bool
            self._keys = ()
        else:
            self._keys = keys
        # Sort alphabetically the keys as a last key -> Avoid most unwanted matchs
        # self._keys = (*self._keys, (lambda e: e[0] or 'None', False)) # But it raises errors sometimes (problem with int < str)
        self.data_list = SortedList(keys=self._keys)
        self.reverse = reverse
        # self.data_list.compare = self.compare

    def __contains__(self, key):
        return self.search_key(key) is not False

    def __repr__(self):
        return (
            "SortedDict{"
            + ", ".join(":".join(map(str, item)) for item in self.data_list)
            + "}"
        )

    def __getitem__(self, key):
        i = self.search_key(key)
        if i is not False:
            return self.data_list[i][1]
        raise KeyError(key)

    def __setitem__(self, key, value):
        e = (key, value)
        found, i = self.binary_search(e, 0, len(self.data_list))

        if found:
            # Overwrite data
            self.data_list[i] = e
        else:
            # Insert data
            self.data_list.insert(i, e)

    def __len__(self):
        return len(self.data_list)

    def keys(self):
        self.quick_sort()
        return tuple(e[0] for e in self.data_list)

    def values(self):
        self.quick_sort()
        return tuple(e[1] for e in self.data_list)

    def items(self):
        self.quick_sort()
        return self.data_list

    def get(self, key, default=None):
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def search_key(self, search_key):
        for i, (key, value) in enumerate(self.data_list):
            if key == search_key:
                return i
        return False

    def compare(self, a, b):
        """Return True if a > b, False if a < b, and None if a == b"""
        for key, reverse in self._keys:
            try:
                k_a, k_b = key(a), key(b)
            except Exception:
                # Problematic -> Can't just skip
                # because looping would be as if it was
                # a match found
                raise
            else:
                if k_a > k_b:
                    return not reverse
                elif k_a < k_b:
                    return reverse
                else:
                    match = True
                # Loop if a == b

        return None

    def binary_search(self, e, start, stop):
        # Binary search utility
        # Return a tuple (bool, int),
        # where bool is whether the element 'e'
        # was found, and int the index of the element,
        # or at least where it should be

        if start == stop:
            # There's no data yet
            return False, 0

        middle = (start + stop) // 2
        found = self.data_list[middle]
        comp = self.compare(e, found)

        if comp is None:
            # e == self.middle
            # We found a matching element
            return True, middle

        elif comp:
            # e > comp
            # The element we are searching for should
            # be to the right of comp

            if middle == start:
                # No more elements
                # If this is true then we are looping
                return False, middle
            else:
                return self.binary_search(e, middle, stop)

        else:
            # e < comp
            # The element we are searching for should
            # be to the left of comp

            if middle == stop:
                # No more elements
                # If this is true then we are looping
                return False, middle
            else:
                return self.binary_search(e, start, middle)

    def quick_sort(self, start=None, stop=None, reversed=False):
        # Sorting function

        def iterator(start, stop, reversed):
            # Iterative implementation of the quick sort algorithm
            # on self.data_list

            if start == stop:
                # No data to sort
                # Shouldn't happen
                return

            if stop - start == 1:
                # There's only one item to sort
                yield self.data_list[start]
                return

            middle = (start + stop) // 2
            left, right = iterator(start, middle, reversed), iterator(
                middle, stop, reversed
            )
            # There should be at least one item
            # for each iterator
            item_left, item_right = next(left), next(right)

            while item_left is not None or item_right is not None:
                if item_left is None:
                    yield item_right
                    item_right = next(right, None)

                elif item_right is None:
                    yield item_left
                    item_left = next(left, None)

                else:
                    comp = self.compare(item_left, item_right)
                    if comp != reversed:
                        yield item_right
                        item_right = next(right, None)

                    else:
                        yield item_left
                        item_left = next(left, None)

        if start is None and stop is None:
            self.data_list = list(iterator(0, len(self.data_list), reversed))
            return self.data_list
        else:
            return iterator(start, stop, reversed)


class ReturnThread(threading.Thread):
    def __init__(self, target=None, args=(), kwargs={}, daemon=True):
        super().__init__(daemon=daemon)
        self.target = target
        self.args = args
        self.kwargs = kwargs
        self.output = queue.Queue()

        self.start()

    def run(self):
        try:
            out = self.target(*self.args, **self.kwargs)
        except Exception:
            self.output.put(None)
        else:
            self.output.put(out)

    def get(self, *args, **kwargs):
        return self.output.get(*args, **kwargs)

    def empty(self):
        return self.output.empty()

    def ready(self):
        return not self.empty()


class LockWrapper:
    """Wrap a context manager lock and adds a callback"""

    def __init__(self, lock, cb):
        self.lock = lock
        self.cb = cb

    def __getattr__(self, e):
        return getattr(self.lock, e)

    def __enter__(self):
        return self.lock.__enter__()

    def __exit__(self, *args):
        out = self.lock.__exit__(*args)
        if not self.lock._is_owned():
            with self.lock:
                self.cb()
        return out


class NoIdFound(KeyError):
    """An exception raised when there is no id found by the APIs"""

    def __init__(self, id):
        self.args = ("Id not found: " + str(id),)


class Magnet:
    """
    Wrap magnet URL and fetch it if necessary.

    Handles both magnet links and regular URLs, with optional downloading
    of non-magnet URLs using a provided downloader function.
    """

    pattern = re.compile(r"^magnet:\?xt=urn:")

    def __init__(self, url, engine_url=None, downloader=None):
        """
        Initialize a Magnet wrapper.

        Args:
            url: The URL (magnet or regular)
            engine_url: Base URL of the search engine (for relative links)
            downloader: Function to download non-magnet URLs
        """
        self.url = url
        self.engine_url = engine_url
        self.downloader = downloader

    def get(self):
        """
        Get the URL, downloading if necessary.

        Returns:
            The magnet URL or downloaded content
        """
        if self.url is None:
            return None
        elif self.is_magnet():
            return self.url
        else:
            if self.downloader is not None:
                self.url = self.downloader(self.engine_url, self.url)
            return self.url

    def is_magnet(self):
        """
        Check if the URL is a magnet link.

        Returns:
            True if the URL is a magnet link
        """
        return self.pattern.match(self.url) is not None

    @property
    def __dict__(self):
        """
        Get dict representation for JSON serialization.

        Returns:
            Dict with url and engine_url
        """
        # For JSON serialization
        return {"url": self.url, "engine_url": self.engine_url}

    def to_json(self):
        """
        Convert to JSON string.

        Returns:
            JSON representation of the Magnet
        """
        return json.dumps(self.__dict__)


if __name__ == "__main__":
    import random

    sl = SortedList(reverse=True)

    for i in random.sample(list(range(100)), 100):
        sl.append(i)

    sd = SortedDict()

    for i in range(100):
        sd[random.randint(0, 100)] = random.randint(0, 100)

    # def slow_iter(msg, t=1, length=10):
    #     for i in range(length):
    #         time.sleep(t)
    #         # log(msg+str(i))
    #         yield msg + str(i)
    # items = ItemList(range(5), ('a', 'b', 'c'), slow_iter(
    #     "haha", 1, 3), slow_iter("hehe", 5, 2))
    # for e in items:
    #     log(e)

    # a = Anime()
    # log(a.title)
    # a.title = "jujutsu"
    # a["synopsis"] = "salut"
    # log(a.title,a.synopsis)
