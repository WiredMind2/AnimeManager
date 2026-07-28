"""Fetch and parse RSS/Atom feeds for auto-download."""

from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_LOG = logging.getLogger("animemanager.rss_feed")

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
_DEFAULT_UA = "AnimeManager/1.0 (+local; rss-auto-download)"


@dataclass(frozen=True, slots=True)
class RssFeedEntry:
    """One feed item with downloadable torrent/magnet link."""

    feed_id: str
    item_key: str
    title: str
    link: str
    enclosure_url: Optional[str] = None

    @property
    def download_url(self) -> Optional[str]:
        for candidate in (self.enclosure_url, self.link):
            text = str(candidate or "").strip()
            if text:
                return text
        return None


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return str(node.text).strip()


def _child_text(parent: ET.Element, names: set[str]) -> str:
    for child in parent:
        if _local_tag(child.tag) in names:
            return _text(child)
    return ""


def _enclosure_url(item: ET.Element) -> Optional[str]:
    for child in item:
        if _local_tag(child.tag) != "enclosure":
            continue
        url = str(child.attrib.get("url") or "").strip()
        if url:
            return url
    return None


def _item_key(*, guid: str, link: str, title: str) -> str:
    if guid:
        return guid
    raw = f"{link}|{title}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def parse_feed_xml(xml_text: str, *, feed_id: str) -> list[RssFeedEntry]:
    """Parse RSS 2.0 or Atom XML into feed entries."""
    text = (xml_text or "").strip()
    if not text:
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []

    root_tag = _local_tag(root.tag).lower()
    entries: list[RssFeedEntry] = []

    if root_tag == "rss" or root_tag == "rdf":
        channel = None
        for child in root:
            if _local_tag(child.tag).lower() == "channel":
                channel = child
                break
        items = channel if channel is not None else root
        for item in items:
            if _local_tag(item.tag).lower() != "item":
                continue
            title = _child_text(item, {"title"})
            link = _child_text(item, {"link"})
            guid = _child_text(item, {"guid"})
            enclosure = _enclosure_url(item)
            if not title and not link and not enclosure:
                continue
            entries.append(
                RssFeedEntry(
                    feed_id=feed_id,
                    item_key=_item_key(guid=guid, link=link or enclosure or "", title=title),
                    title=title,
                    link=link,
                    enclosure_url=enclosure,
                )
            )
        return entries

    # Atom
    atom_entries = root.findall("atom:entry", _ATOM_NS)
    if not atom_entries:
        atom_entries = [c for c in root if _local_tag(c.tag).lower() == "entry"]
    for entry in atom_entries:
        title = _child_text(entry, {"title"})
        link = ""
        enclosure: Optional[str] = None
        for child in entry:
            if _local_tag(child.tag).lower() != "link":
                continue
            href = str(child.attrib.get("href") or "").strip()
            rel = str(child.attrib.get("rel") or "alternate").strip().lower()
            typ = str(child.attrib.get("type") or "").strip().lower()
            if not href:
                continue
            if "torrent" in typ or rel in {"enclosure", "related"}:
                enclosure = enclosure or href
            elif rel == "alternate" or not link:
                link = href
        guid = _child_text(entry, {"id"})
        if not title and not link and not enclosure:
            continue
        entries.append(
            RssFeedEntry(
                feed_id=feed_id,
                item_key=_item_key(guid=guid, link=link or enclosure or "", title=title),
                title=title,
                link=link,
                enclosure_url=enclosure,
            )
        )
    return entries


class RssFeedAdapter:
    """HTTP RSS/Atom fetcher used by auto-download RSS mode."""

    def __init__(
        self,
        *,
        opener: Callable[[str, float], str] | None = None,
        timeout_s: float = 20.0,
    ) -> None:
        self._opener = opener or self._default_fetch
        self._timeout_s = float(timeout_s)

    @staticmethod
    def _default_fetch(url: str, timeout_s: float) -> str:
        req = Request(url, headers={"User-Agent": _DEFAULT_UA})
        with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 — user-configured feed URLs
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")

    def fetch_entries(self, *, feed_id: str, url: str) -> list[RssFeedEntry]:
        clean_url = str(url or "").strip()
        if not clean_url.lower().startswith(("http://", "https://")):
            _LOG.warning("Rejecting non-http(s) feed url for %s", feed_id)
            return []
        try:
            xml_text = self._opener(clean_url, self._timeout_s)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            _LOG.warning("Feed fetch failed for %s: %s", feed_id, exc)
            return []
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("Feed fetch failed for %s: %s", feed_id, exc)
            return []
        return parse_feed_xml(xml_text, feed_id=str(feed_id))

    def fetch_many(self, feeds: list[dict[str, Any]]) -> list[RssFeedEntry]:
        out: list[RssFeedEntry] = []
        for feed in feeds:
            feed_id = str(feed.get("id") or "").strip()
            url = str(feed.get("url") or "").strip()
            if not feed_id or not url:
                continue
            out.extend(self.fetch_entries(feed_id=feed_id, url=url))
        return out
