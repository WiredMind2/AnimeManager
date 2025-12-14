import os
import sys

import requests

try:
    from ..getters import Getters
    from ..logger import Logger
except ImportError:
    from getters import Getters
    from logger import Logger

exceptions = requests.exceptions


class ParserUtils(Logger, Getters):
    def __init__(self):
        Logger.__init__(self, logs="ALL")
        # self.dbPath = dbPath
        # self.database = self.getDatabase()
        self.session = requests.Session()

    def get(self, *args, **kwargs):
        # Wrapper function for HTTP GET requests
        return self.session.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        # Wrapper function for HTTP POST requests
        return self.session.get(*args, **kwargs)
