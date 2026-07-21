#!/usr/bin/env python3
"""Atheris harness for adapters.search.parser.ResultParser.parse."""

from __future__ import annotations

import sys
from pathlib import Path

import atheris

# Repo root on path when run as fuzz/parse_pretty_line_fuzzer.py
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

with atheris.instrument_imports():
    from adapters.search.parser import ResultParser

_PARSER = ResultParser(max_line_bytes=65536)


def TestOneInput(data: bytes) -> None:
    # Parser is total for validation failures; unexpected exceptions are findings.
    _PARSER.parse(data)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
