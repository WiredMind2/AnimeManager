"""Tests for RSS feed parsing and auto-download matching."""

from __future__ import annotations

from adapters.feeds.rss_feed_adapter import RssFeedAdapter, RssFeedEntry, parse_feed_xml
from adapters.feeds.rss_match import find_rss_candidate
from adapters.search.title_parser import parse_title
from application.services.auto_download_matching import ReleasePreference

RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>SubsPlease</title>
    <item>
      <title>[SubsPlease] Cool Show - 03 (1080p) [AABBCCDD].mkv</title>
      <link>https://example.com/dl/3</link>
      <guid>guid-3</guid>
      <enclosure url="magnet:?xt=urn:btih:abc123" type="application/x-bittorrent"/>
    </item>
    <item>
      <title>[SubsPlease] Cool Show - 02 (720p) [EEFF0011].mkv</title>
      <link>https://example.com/dl/2</link>
      <guid>guid-2</guid>
    </item>
  </channel>
</rss>
"""


def test_parse_feed_xml_rss_items():
    entries = parse_feed_xml(RSS_SAMPLE, feed_id="subsplease-1080")
    assert len(entries) == 2
    assert entries[0].item_key == "guid-3"
    assert entries[0].enclosure_url.startswith("magnet:")
    assert entries[0].download_url.startswith("magnet:")


def test_rss_adapter_fetch_entries_uses_opener():
    adapter = RssFeedAdapter(opener=lambda url, timeout: RSS_SAMPLE)
    entries = adapter.fetch_entries(
        feed_id="subsplease-1080",
        url="https://subsplease.org/rss/?r=1080",
    )
    assert len(entries) == 2


def test_rss_adapter_rejects_non_http():
    adapter = RssFeedAdapter(opener=lambda url, timeout: RSS_SAMPLE)
    assert adapter.fetch_entries(feed_id="x", url="file:///etc/passwd") == []


def test_find_rss_candidate_matches_terms_and_preference():
    entries = parse_feed_xml(RSS_SAMPLE, feed_id="subsplease-1080")
    preference = ReleasePreference(publisher="subsplease", resolution="1080p")
    candidate = find_rss_candidate(
        entries,
        search_terms=["Cool Show"],
        preference=preference,
        episode=3,
        parse_title=parse_title,
        seen_keys=set(),
    )
    assert candidate is not None
    assert candidate["item_key"] == "guid-3"
    assert "magnet:" in candidate["link"]


def test_find_rss_candidate_skips_seen():
    entries = [
        RssFeedEntry(
            feed_id="f1",
            item_key="k1",
            title="[SubsPlease] Cool Show - 03 (1080p) [AA].mkv",
            link="https://example.com/a",
            enclosure_url="magnet:?xt=urn:btih:aaa",
        )
    ]
    preference = ReleasePreference(publisher="subsplease", resolution="1080p")
    assert (
        find_rss_candidate(
            entries,
            search_terms=["Cool Show"],
            preference=preference,
            episode=3,
            parse_title=parse_title,
            seen_keys={("f1", "k1")},
        )
        is None
    )
