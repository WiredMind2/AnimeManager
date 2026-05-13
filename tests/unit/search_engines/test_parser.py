"""Unit tests for ``search_engines.parser``."""

from __future__ import annotations

import pytest

from search_engines.parser import ResultParser


@pytest.fixture
def parser() -> ResultParser:
    return ResultParser(max_line_bytes=4096)


VALID_MAGNET = (
    "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567"
    "&dn=Example&tr=udp://tracker.example.org:6969"
)


def _line(*parts: str) -> bytes:
    return ("|".join(parts) + "\n").encode("utf-8")


def test_parser_accepts_well_formed_row(parser, reset_metrics):
    line = _line(
        VALID_MAGNET,
        "Example Anime [Dual Audio]",
        "1073741824",
        "120",
        "5",
        "https://nyaa.si",
        "https://nyaa.si/view/123",
    )

    result = parser.parse(line)
    assert result is not None
    assert result.size == 1073741824
    assert result.seeds == 120
    assert result.leech == 5
    assert result.engine_url == "https://nyaa.si"
    assert result.desc_link == "https://nyaa.si/view/123"
    assert result.infohash == "0123456789abcdef0123456789abcdef01234567"


def test_parser_rejects_non_magnet(parser, reset_metrics):
    line = _line(
        "https://example.com/torrent",
        "Some Name",
        "100",
        "1",
        "0",
        "https://example.com",
        "https://example.com/desc",
    )

    assert parser.parse(line) is None


def test_parser_drops_oversize_line():
    parser = ResultParser(max_line_bytes=128)
    huge = b"x" * 1024 + b"\n"
    assert parser.parse(huge) is None


def test_parser_handles_missing_desc_link(parser):
    line = _line(
        VALID_MAGNET,
        "Name only",
        "0",
        "0",
        "0",
        "https://engine.example",
    )
    result = parser.parse(line)
    assert result is not None
    assert result.desc_link is None


def test_parser_coerces_non_numeric_fields(parser):
    line = _line(
        VALID_MAGNET,
        "Robust Parsing",
        "not-a-number",
        "abc",
        "-5",
        "https://engine.example",
        "https://engine.example/desc",
    )
    result = parser.parse(line)
    assert result is not None
    assert result.size == 0
    assert result.seeds == 0
    assert result.leech == 0


def test_parser_handles_control_chars_in_name(parser):
    raw = _line(
        VALID_MAGNET,
        "Bad\x00Name\nWith\tControl",
        "100",
        "1",
        "0",
        "https://engine.example",
        "https://engine.example/desc",
    )
    result = parser.parse(raw)
    assert result is not None
    assert "\x00" not in result.name
    assert "\n" not in result.name
