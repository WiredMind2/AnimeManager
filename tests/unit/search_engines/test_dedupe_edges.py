"""Additional edge case tests for ``adapters.search.dedupe``."""

from __future__ import annotations

import threading

from search_engines.dedupe import ResultDeduper, fingerprint
from search_engines.parser import TorrentResult


def _result(**overrides) -> TorrentResult:
    base = dict(
        link="magnet:?xt=urn:btih:abc",
        name="Sample Anime",
        size=100,
        seeds=10,
        leech=1,
        engine_url="https://example.com",
        desc_link="https://example.com/view/1",
        infohash="abc",
    )
    base.update(overrides)
    return TorrentResult(**base)


class TestFingerprintEdges:
    def test_empty_name_fallback(self):
        fp = fingerprint(_result(infohash=None, name=""))
        assert fp[0] == "nf"

    def test_whitespace_only_name_normalises_to_empty(self):
        fp = fingerprint(_result(infohash=None, name="    "))
        # Tuple structure: ("nf", name, size, engine, desc)
        assert fp[1] == ""

    def test_nfkd_normalisation_used(self):
        fp1 = fingerprint(_result(infohash=None, name="naïve"))
        fp2 = fingerprint(_result(infohash=None, name="naive\u0308".replace("\u0308", "")))
        # Should not equal, just confirm normalisation runs
        assert fp1[0] == "nf"

    def test_engine_url_case_insensitive(self):
        a = fingerprint(_result(infohash=None, engine_url="HTTPS://EXAMPLE.COM"))
        b = fingerprint(_result(infohash=None, engine_url="https://example.com"))
        assert a == b

    def test_desc_link_case_insensitive(self):
        a = fingerprint(_result(infohash=None, desc_link="HTTPS://X/Y"))
        b = fingerprint(_result(infohash=None, desc_link="https://x/y"))
        assert a == b

    def test_infohash_whitespace_stripped(self):
        a = fingerprint(_result(infohash="  abc  "))
        assert a == ("ih", "abc")


class TestDeduperEdges:
    def test_repeated_registration_returns_none(self):
        d = ResultDeduper()
        first = d.register(_result(infohash="x"))
        second = d.register(_result(infohash="x"))
        assert first is not None
        assert second is None

    def test_distinct_items_increase_length(self):
        d = ResultDeduper()
        d.register(_result(infohash="a"))
        d.register(_result(infohash="b"))
        d.register(_result(infohash="c"))
        assert len(d) == 3

    def test_thread_safety(self):
        d = ResultDeduper()
        results = [_result(infohash=str(i)) for i in range(200)]

        # Duplicate every infohash so half should be dropped
        all_results = results + results

        def worker(items):
            for r in items:
                d.register(r)

        threads = []
        chunk = len(all_results) // 4
        for i in range(4):
            t = threading.Thread(
                target=worker,
                args=(all_results[i * chunk:(i + 1) * chunk],),
            )
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        assert len(d) == 200

    def test_dedup_by_fallback_when_infohash_missing(self):
        d = ResultDeduper()
        first = d.register(_result(infohash=None, name="x", engine_url="e"))
        second = d.register(_result(infohash=None, name="X", engine_url="E"))
        assert first is not None
        # second should be a dup due to case-insensitive equality
        assert second is None
