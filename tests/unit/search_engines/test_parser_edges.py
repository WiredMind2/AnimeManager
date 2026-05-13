"""Additional edge case tests for ``adapters.search.parser``.

Covers malformed inputs, oversized payloads and Unicode normalisation.
"""

from __future__ import annotations

import pytest

from search_engines.parser import ResultParser, TorrentResult


@pytest.fixture
def parser():
    return ResultParser(max_line_bytes=4096)


class TestParserEmptyAndBadInputs:
    def test_empty_bytes_returns_none(self, parser):
        assert parser.parse(b"") is None

    def test_blank_line_returns_none(self, parser):
        assert parser.parse(b"   \t  \n  ") is None

    def test_oversized_line_dropped(self):
        small = ResultParser(max_line_bytes=10)
        assert small.parse(b"a" * 11) is None

    def test_non_magnet_link_dropped(self, parser):
        line = b"http://example.com|name|123|10|1|engine|desc"
        assert parser.parse(line) is None

    def test_missing_fields_dropped(self, parser):
        # Only 3 fields (need 6 or 7)
        line = b"magnet:?xt=urn:btih:abc|name|123"
        assert parser.parse(line) is None

    def test_missing_name_dropped(self, parser):
        line = b"magnet:?xt=urn:btih:abc||100|10|1|https://engine"
        assert parser.parse(line) is None

    def test_missing_engine_url_dropped(self, parser):
        line = b"magnet:?xt=urn:btih:abc|name|100|10|1|"
        assert parser.parse(line) is None


class TestParserCoercion:
    def test_non_numeric_size_coerces_to_zero(self, parser):
        line = b"magnet:?xt=urn:btih:abc|name|notanumber|10|1|https://engine"
        result = parser.parse(line)
        assert result is not None
        assert result.size == 0

    def test_negative_size_clamped_to_zero(self, parser):
        line = b"magnet:?xt=urn:btih:abc|name|-500|10|1|https://engine"
        result = parser.parse(line)
        assert result is not None
        assert result.size == 0

    def test_negative_seeds_clamped_to_zero(self, parser):
        line = b"magnet:?xt=urn:btih:abc|name|100|-5|1|https://engine"
        result = parser.parse(line)
        assert result is not None
        assert result.seeds == 0

    def test_blank_seeds_coerce_to_zero(self, parser):
        line = b"magnet:?xt=urn:btih:abc|name|100||1|https://engine"
        result = parser.parse(line)
        assert result is not None
        assert result.seeds == 0

    def test_blank_size_coerces_to_zero(self, parser):
        line = b"magnet:?xt=urn:btih:abc|name||10|1|https://engine"
        result = parser.parse(line)
        assert result is not None
        assert result.size == 0

    def test_huge_size_preserved(self, parser):
        big = 10**18
        line = f"magnet:?xt=urn:btih:abc|name|{big}|10|1|https://engine".encode()
        result = parser.parse(line)
        assert result is not None
        assert result.size == big


class TestParserUnicodeAndControl:
    def test_control_chars_stripped_from_name(self, parser):
        line = b"magnet:?xt=urn:btih:abc|na\x00me|100|10|1|https://engine"
        result = parser.parse(line)
        assert result is not None
        assert "\x00" not in result.name

    def test_unicode_name_preserved(self, parser):
        line = "magnet:?xt=urn:btih:abc|ナルト|100|10|1|https://engine".encode("utf-8")
        result = parser.parse(line)
        assert result is not None
        assert "ナルト" in result.name

    def test_invalid_utf8_replaced_not_dropped(self, parser):
        line = b"magnet:?xt=urn:btih:abc|na\xffme|100|10|1|https://engine"
        result = parser.parse(line)
        assert result is not None
        # Replacement character preserved or stripped, but record kept.

    def test_collapses_runs_of_whitespace(self, parser):
        line = b"magnet:?xt=urn:btih:abc|na   me   long|100|10|1|https://engine"
        result = parser.parse(line)
        assert result is not None
        assert "  " not in result.name


class TestParserInfohash:
    def test_extracts_infohash_lowercased(self, parser):
        line = b"magnet:?xt=urn:btih:ABCDEF1234|name|100|10|1|https://engine"
        result = parser.parse(line)
        assert result is not None
        assert result.infohash == "abcdef1234"

    def test_infohash_none_for_non_btih_magnet(self):
        parser = ResultParser(max_line_bytes=4096)
        # Non-btih xt= but still magnet-like
        line = b"magnet:?xt=urn:other:abcd|name|100|10|1|https://engine"
        result = parser.parse(line)
        # Magnet regex accepts urn:<scheme>:<id>; but infohash regex requires urn:btih
        assert result is not None
        assert result.infohash is None


class TestParserAsDict:
    def test_as_dict_shape(self):
        result = TorrentResult(
            link="magnet:?xt=urn:btih:abc",
            name="Sample",
            size=100,
            seeds=2,
            leech=3,
            engine_url="https://x",
            desc_link=None,
            infohash="abc",
        )
        d = result.as_dict()
        assert d == {
            "link": "magnet:?xt=urn:btih:abc",
            "name": "Sample",
            "size": 100,
            "seeds": 2,
            "leech": 3,
            "engine_url": "https://x",
            "desc_link": "",
            "infohash": "abc",
            # ``parsed`` is filled by ``ResultParser.parse`` from the
            # name field. When a ``TorrentResult`` is constructed
            # directly (without going through ``ResultParser``) it
            # stays ``None`` -- this is the contract for ad-hoc/test
            # construction.
            "parsed": None,
        }

    def test_as_dict_preserves_desc_link(self):
        result = TorrentResult(
            link="magnet:?xt=urn:btih:abc",
            name="Sample",
            size=100,
            seeds=2,
            leech=3,
            engine_url="https://x",
            desc_link="https://desc",
            infohash="abc",
        )
        assert result.as_dict()["desc_link"] == "https://desc"
