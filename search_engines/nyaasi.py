""" Torrent web parser for nyaa.si """
import urllib.parse
import io

from lxml import etree

try:
    from .parserUtils import ParserUtils, exceptions
except ImportError:
    # Local testing
    import os
    import sys
    sys.path.append(os.path.abspath('./'))
    from parserUtils import ParserUtils, exceptions


class Parser(ParserUtils):
    def search(self, terms, limit=50):
        terms = terms.strip()
        searchterms = urllib.parse.quote_plus(terms)

        tree = None
        url = "https://nyaa.si/?page=rss&q={}&c=1_0&f=0".format(searchterms)
        try:
            self.log("Nyaasi", terms, url)
            r = self.get(url, timeout=10)
        except exceptions.ConnectionError:
            self.log("Nyaasi - No internet connection!")
        except exceptions.ReadTimeout:
            self.log("Nyaasi - Timed out!")
        else:
            try:
                tree = etree.parse(io.BytesIO(r.content))
            except etree.XMLSyntaxError as e:
                self.log("Nyaasi - Error:", e, tree)
                return
            for child in tree.getroot().find('channel'):
                try:
                    if child.tag == 'item':
                        filename = child.find('title').text
                        torrent_url = child.find('link').text
                        seeds = child.find(
                            '{https://nyaa.si/xmlns/nyaa}seeders').text
                        leechs = child.find(
                            '{https://nyaa.si/xmlns/nyaa}leechers').text
                        file_size = child.find(
                            "{https://nyaa.si/xmlns/nyaa}size").text
                        yield {'filename': filename, 'torrent_url': torrent_url, 'seeds': seeds, 'leechs': leechs, 'file_size': file_size}
                except Exception as e:
                    self.log("Nyaasi - error:", e)


if __name__ == "__main__":
    p = Parser()

    r = p.search("meikyuu")
    for m in r:
        print(m)
