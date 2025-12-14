"""Torrent web parser for nyaa.si"""

import re
import traceback
import urllib.parse

from bs4 import BeautifulSoup

try:
    from .parserUtils import ParserUtils, exceptions
except ImportError:
    # Local testing
    import os
    import sys

    sys.path.append(os.path.abspath("./"))
    from parserUtils import ParserUtils, exceptions


class Parser(ParserUtils):
    API_NAME = "TokyoTosho"

    def search(self, terms, limit=50):
        terms = terms.strip()
        searchterms = urllib.parse.quote_plus(terms)

        soup = None
        url = "https://www.tokyotosho.info/search.php?terms={}&type=1&searchName=true&searchComment=true".format(
            searchterms
        )
        try:
            r = self.get(url, timeout=10)
        except exceptions.ConnectionError:
            self.log("Tokyotosho - No internet connection!")
            yield False
        except exceptions.ReadTimeout:
            self.log("Tokyotosho - Timed out!")
            yield False
        else:
            soup = BeautifulSoup(r.content, "html.parser")
            pattern = re.compile(r"\| Size: (\S*?) \|")
            table = soup.find("table", class_="listing")
            body = table.find_all("tr")[1:]
            for rowA, rowB in self.table_iter(body):
                try:
                    title_column = rowA.find("td", class_="desc-top")
                    if title_column is None:
                        continue
                    filename = title_column.find_all("a")[-1].text
                    torrent_url = title_column.find_all("a")[-1]["href"]

                    desc = rowB.find("td", class_="desc-bot").text
                    result = pattern.findall(desc)
                    file_size = result[0] if len(result) >= 1 else ""

                    stats = rowB.find("td", class_="stats")
                    seeds, leechs = map(lambda e: e.text, stats.find_all("span")[:2])

                    out = {
                        "name": filename,
                        "link": torrent_url,
                        "seeds": seeds,
                        "leech": leechs,
                        "size": file_size,
                    }
                    yield out
                except Exception as e:
                    self.log("Tokyotosho - error:", traceback.format_exc())

    def table_iter(self, table):
        a, b = None, None
        for e in table:
            if a is None:
                a = e
            elif b is None:
                b = e
                yield a, b
                a, b = None, None


if __name__ == "__main__":
    p = Parser()

    r = p.search("meikyu")
    for m in r:
        pass
