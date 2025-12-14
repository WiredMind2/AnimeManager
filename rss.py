import re
import threading

import requests

from classes import Torrent

# from lxml import etree, html



class RSS:
    def addRSS(self, id):
        # TODO
        pass

    def parseRSS(self, link):
        try:
            r = requests.get(link)
            r.raise_for_status()
        except Exception as e:
            # TODO
            raise

        tree = etree.ElementTree(html.fromstring(r.content))
        channel = tree.xpath("channel")[0]
        title, desc = "No title", "No description"
        items = []
        for entry in channel:
            if entry.tag == "item":
                data = {}
                keys = ("title", "link", "pubdate")
                for sub in entry:
                    if sub.tag in keys:
                        data[sub.tag] = sub.text or sub.tail
                items.append(data)

            elif entry.tag == "title":
                title = entry.text
            elif entry.tag == "description":
                desc = entry.text

        return {"title": title, "desc": desc, "data": items}

    def getRSSTorrents(self, data, thread=True):
        # Data is a dict with anime id, links and filters: {'id': (link, [filter1, filter2, ...]), ...}
        if thread:
            threading.Thread(target=self.getRSSTorrents, args=(data, False)).start()
            return

        out = {}
        for id, (link, filters) in data.items():
            items = self.parseRSS(link).get("data", [])
            for item in items:
                if all(map(lambda f: f(item), filters)):
                    if id not in out:
                        out[id] = []

                    out[id].append(item)

        self.log(
            "[RSS]",
            f"{sum(map(len, out.values()))} new torrents found from RSS, downloading",
        )
        for id, items in out.items():
            for item in items:
                self.downloadFile(id, url=item["link"])
