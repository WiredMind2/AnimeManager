# from tkinter import *
import json
import multiprocessing
import os
import queue
import random
import re
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from datetime import time as datetime_time
from datetime import timedelta, timezone, tzinfo
from operator import itemgetter

import mysql.connector
import requests
from mysql.connector.errors import ProgrammingError
from thefuzz import fuzz
from thefuzz import process as fuzz_process

try:
    from .animeAPI.JikanMoe import JikanMoeWrapper
    from .animeManager import Manager
    from .classes import Anime, AnimeList, RegroupList, SortedDict, SortedList
    from .constants import Constants
    from .db_managers.dbManager import db_instance
    from .getters import Getters
    from .table_frame import TableFrame
except ImportError:
    from animeAPI.JikanMoe import JikanMoeWrapper
    from animeManager import Manager
    from classes import Anime, AnimeList, RegroupList, SortedDict, SortedList
    from constants import Constants
    from db_managers.dbManager import db_instance
    from getters import Getters
    from table_frame import TableFrame

# terms = 'classroom of the elite'
# data = main.api.searchAnime(terms, limit=main.animePerPage)
# while not data.empty():
# 	anime = data.get()
# 	if anime is not None:
# 		print(anime.title)

main = Manager(remote=True)

db = main.getDatabase()

main.getSchedule(force=True)

pass
# data = main.api.schedule(limit=main.maxTrendingAnime)

# queue = []

# timeout = time.time() + main.scheduleTimeout

# while not data.empty():
# 	anime = data.get(timeout=10)
# 	if anime is None or len(anime) == 0:
# 		continue

# 	queue.append(anime)

# pass