"""Strict parser for nova3 ``prettyPrinter`` output.

The legacy wrapper split lines on ``|`` and applied a coarse magnet regex.
This module replaces that with a schema-aware parser that:
  * validates the magnet URI format;
  * coerces numeric fields safely;
  * normalizes Unicode and trims whitespace;
  * rejects oversized or malformed rows without raising.

The parser produces ``TorrentResult`` records consumed by the dedupe and
ranking stages, and a dict view that preserves backward compatibility with
existing GUI/API consumers.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .telemetry import get_metrics
from .title_parser import ParsedTitle, parse_title

_PRETTY_KEYS = ("link", "name", "size", "seeds", "leech", "engine_url", "desc_link")
_MAGNET_RE = re.compile(r"^magnet:\?xt=urn:[A-Za-z0-9]+:[A-Za-z0-9]+", re.IGNORECASE)
_INFOHASH_RE = re.compile(r"xt=urn:btih:([A-Za-z0-9]+)", re.IGNORECASE)


@dataclass(frozen=True)
class TorrentResult:
    """Validated, immutable view of a single torrent row."""

    link: str
    name: str
    size: int
    seeds: int
    leech: int
    engine_url: str
    desc_link: Optional[str]
    infohash: Optional[str]
    parsed: Optional[ParsedTitle] = field(default=None)

    def as_dict(self) -> Dict[str, Any]:
        """Return a dict compatible with the legacy emit format.

        The ``parsed`` sub-object exposes the structured metadata
        (publisher, resolution, season, episode, ...) extracted by
        :mod:`adapters.search.title_parser`. Older consumers that only
        read ``name`` / ``link`` keep working unchanged.
        """
        return {
            "link": self.link,
            "name": self.name,
            "size": self.size,
            "seeds": self.seeds,
            "leech": self.leech,
            "engine_url": self.engine_url,
            "desc_link": self.desc_link or "",
            "infohash": self.infohash,
            "parsed": self.parsed.as_dict() if self.parsed is not None else None,
        }


class ResultParser:
    """Parses ``prettyPrinter`` lines into ``TorrentResult`` records."""

    def __init__(self, *, max_line_bytes: int):
        self._max_line_bytes = max_line_bytes
        self._metrics = get_metrics()

    def parse(self, line: bytes) -> Optional[TorrentResult]:
        if not line:
            return None
        if len(line) > self._max_line_bytes:
            self._metrics.incr("parser_dropped_oversize")
            return None

        try:
            text = line.decode("utf-8", errors="replace").strip()
        except Exception:
            self._metrics.incr("parser_dropped_decode")
            return None
        if not text:
            return None

        parts = text.split("|")
        if len(parts) < len(_PRETTY_KEYS) - 1:
            self._metrics.incr("parser_dropped_arity")
            return None

        record: Dict[str, str] = dict(zip(_PRETTY_KEYS, parts))
        link = record.get("link", "").strip()
        if not _MAGNET_RE.match(link):
            self._metrics.incr("parser_dropped_non_magnet")
            return None

        infohash = self._extract_infohash(link)
        name = self._clean_text(record.get("name", ""))
        engine_url = record.get("engine_url", "").strip()
        desc_link = record.get("desc_link") or None
        if desc_link is not None:
            desc_link = desc_link.strip() or None

        try:
            size = max(0, int(record.get("size", "0").strip() or 0))
        except ValueError:
            size = 0
            self._metrics.incr("parser_size_coerced")
        seeds = self._safe_int(record.get("seeds"))
        leech = self._safe_int(record.get("leech"))

        if not name or not engine_url:
            self._metrics.incr("parser_dropped_missing_field")
            return None

        self._metrics.incr("parser_accepted")
        try:
            parsed = parse_title(name)
        except Exception:  # pragma: no cover - parser is total but defensive
            self._metrics.incr("parser_title_extract_failed")
            parsed = None
        return TorrentResult(
            link=link,
            name=name,
            size=size,
            seeds=seeds,
            leech=leech,
            engine_url=engine_url,
            desc_link=desc_link,
            infohash=infohash,
            parsed=parsed,
        )

    @staticmethod
    def _safe_int(raw: Optional[str]) -> int:
        if raw is None:
            return 0
        try:
            value = int(str(raw).strip() or 0)
        except ValueError:
            return 0
        return max(0, value)

    @staticmethod
    def _clean_text(value: str) -> str:
        text = unicodedata.normalize("NFKC", value)
        text = "".join(ch for ch in text if ch == " " or not _is_control(ch))
        return " ".join(text.split())

    @staticmethod
    def _extract_infohash(magnet: str) -> Optional[str]:
        match = _INFOHASH_RE.search(magnet)
        return match.group(1).lower() if match else None


def _is_control(ch: str) -> bool:
    return unicodedata.category(ch).startswith("C")
