"""Torrent web parser for nyaa.si"""

import io
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
    API_NAME = "NyaaSi"

    def search(self, terms, results=50):
        terms = terms.strip()
        results_list = []
        searchterms = urllib.parse.quote_plus(terms)

        tree = None
        for url in (
            "https://nyaa.si/?page=rss&q={}&c=1_0&f=0",
            "https://nyaa.si/?page=rss&q={}&c=1_0&f=0&s=seeders&o=desc",
        ):
            url = "https://nyaa.si/?page=rss&q={}&c=1_0&f=0".format(searchterms)
            try:
                r = self.get(url, timeout=10)
            except exceptions.ConnectionError:
                self.log("Nyaasi - No internet connection!")
                results_list.append(False)
            except exceptions.ReadTimeout:
                self.log("Nyaasi - Timed out!")
                results_list.append(False)
            else:
                try:
                    tree = etree.parse(io.BytesIO(r.content))
                except etree.XMLSyntaxError as e:
                    self.log("Nyaasi - Error:", e, tree)
                    continue
                for child in tree.getroot().find("channel"):
                    try:
                        if child.tag == "item":
                            filename = child.find("title").text
                            torrent_url = child.find("link").text
                            seeds = child.find(
                                "{https://nyaa.si/xmlns/nyaa}seeders"
                            ).text
                            leechs = child.find(
                                "{https://nyaa.si/xmlns/nyaa}leechers"
                            ).text
                            file_size = child.find(
                                "{https://nyaa.si/xmlns/nyaa}size"
                            ).text
                            results_list.append(
                                {
                                    "name": filename,
                                    "link": torrent_url,
                                    "seeds": seeds,
                                    "leech": leechs,
                                    "size": file_size,
                                }
                            )
                    except Exception as e:
                        self.log("Nyaasi - error:", e)
        return results_list


if __name__ == "__main__":
    p = Parser()

    r = p.search("meikyuu")
    for m in r:
        pass
