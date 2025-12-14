"""Template to use for the torrent database web parsers"""

try:
    from .parserUtils import ParserUtils
except ImportError:
    # Local testing
    import os
    import sys

    sys.path.append(os.path.abspath("./"))
    from parserUtils import ParserUtils


class Parser(ParserUtils):
    API_NAME = "CoolApiName"  # This name is used for logging

    def __init__(self):
        # If you need to use __init__(),
        # don't forget to do this:
        super().__init__()

    def search(self, terms, results=50):
        data = [
            {
                "name": "firstMatch.mkv",
                "link": "https://somewebsite.com/torrent_file_url",
                "seeds": 0,
                "leech": 0,
                "size": 0,
            },
            {
                "name": "secondMatch.mkv",
                "link": "https://somewebsite.com/other_torrent_file_url",
                "seeds": 0,
                "leech": 0,
                "size": 0,
            },
        ]
        return data


"""
Your class does not have to be called Parser, 
you can also do something like:

Parser = YourClassName
"""
