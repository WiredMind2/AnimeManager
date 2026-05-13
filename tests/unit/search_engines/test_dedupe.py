"""Unit tests for ``search_engines.dedupe``."""

from __future__ import annotations

from search_engines.dedupe import ResultDeduper, fingerprint
from search_engines.parser import TorrentResult


def _result(**overrides) -> TorrentResult:
    base = dict(
        link="magnet:?xt=urn:btih:abc",
        name="Sample Anime",
        size=100,
        seeds=10,
        leech=1,
        engine_url="https://nyaa.si",
        desc_link="https://nyaa.si/view/1",
        infohash="abc",
    )
    base.update(overrides)
    return TorrentResult(**base)


def test_fingerprint_uses_infohash_when_available():
    fp1 = fingerprint(_result(infohash="DEF", name="Different Name"))
    fp2 = fingerprint(_result(infohash="def", name="another"))
    assert fp1 == fp2 == ("ih", "def")


def test_fingerprint_falls_back_to_normalized_fields():
    fp1 = fingerprint(
        _result(infohash=None, name="My Anime", engine_url="https://A")
    )
    fp2 = fingerprint(
        _result(infohash=None, name="  my   anime  ", engine_url="HTTPS://a")
    )
    assert fp1 == fp2


def test_dedupe_returns_none_for_duplicates():
    deduper = ResultDeduper()
    first = deduper.register(_result(infohash="abc"))
    second = deduper.register(_result(infohash="abc"))
    third = deduper.register(_result(infohash="xyz"))

    assert first is not None
    assert second is None
    assert third is not None
    assert len(deduper) == 2
