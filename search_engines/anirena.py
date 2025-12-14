"""Torrent web parser for anirena.com"""

import io
import re
import urllib.parse

from lxml import etree

try:
    from .parserUtils import ParserUtils, exceptions
except ImportError:
    # Local testing
    import os
    import sys

    sys.path.append(os.path.abspath("./"))
    from parserUtils import ParserUtils, exceptions


class Parser(ParserUtils):
    API_NAME = "Anirena"

    def search(self, terms, results=50):
        terms = terms.strip()
        results_list = []
        searchterms = urllib.parse.quote_plus(terms)

        tree = None
        url = "https://www.anirena.com/rss.php?s={}".format(searchterms)
        try:
            r = self.get(url, timeout=15)
            if r.status_code == 522:
                self.log("Timed out!")
                return
        except exceptions.ConnectionError:
            self.log("Anirena - No internet connection!")
            results_list.append(False)
        except exceptions.ReadTimeout:
            self.log("Anirena - Timed out!")
            results_list.append(False)
        else:
            tree = etree.parse(io.BytesIO(r.content))
            pattern = re.compile(
                r"(\d+?) seeder\(s\), (\d+?) leecher\(s\), \d+? downloads, (\S+? .B)"
            )
            for child in tree.getroot().find("channel"):
                try:
                    if child.tag == "item":
                        category = child.find("category").text
                        if category == "Anime":
                            filename = child.find("title").text
                            torrent_url = child.find("link").text
                            desc = child.find("description").text
                            seeds, leechs, file_size = pattern.findall(desc)[0]
                            out = {
                                "name": filename,
                                "link": torrent_url,
                                "seeds": seeds,
                                "leech": leechs,
                                "size": file_size,
                            }
                            results_list.append(out)
                except Exception as e:
                    self.log("Anirena - error:", e)
        return results_list


if __name__ == "__main__":
    p = Parser()

    r = p.search("meikyu")
    for m in r:
        pass
