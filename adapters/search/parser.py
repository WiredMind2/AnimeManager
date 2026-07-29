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

    def from_fields(
        self,
        *,
        link: str,
        name: str,
        size: Any = 0,
        seeds: Any = 0,
        leech: Any = 0,
        engine_url: str,
        desc_link: Optional[str] = None,
    ) -> Optional[TorrentResult]:
        """Build a :class:`TorrentResult` from already-split fields.

        Used by first-party sources (e.g. SubsPlease API) that do not emit
        ``prettyPrinter`` lines but still need the same validation / title
        parsing as Nova workers.
        """
        magnet = str(link or "").strip()
        if not _MAGNET_RE.match(magnet):
            self._metrics.incr("parser_dropped_non_magnet")
            return None
        clean_name = self._clean_text(str(name or ""))
        clean_engine = str(engine_url or "").strip()
        if not clean_name or not clean_engine:
            self._metrics.incr("parser_dropped_missing_field")
            return None
        try:
            size_i = max(0, int(size or 0))
        except (TypeError, ValueError):
            size_i = 0
            self._metrics.incr("parser_size_coerced")
        seeds_i = self._safe_int(seeds)
        leech_i = self._safe_int(leech)
        desc = str(desc_link).strip() if desc_link else None
        if desc == "":
            desc = None
        self._metrics.incr("parser_accepted")
        try:
            parsed = parse_title(clean_name)
        except Exception:  # pragma: no cover - parser is total but defensive
            self._metrics.incr("parser_title_extract_failed")
            parsed = None
        return TorrentResult(
            link=magnet,
            name=clean_name,
            size=size_i,
            seeds=seeds_i,
            leech=leech_i,
            engine_url=clean_engine,
            desc_link=desc,
            infohash=self._extract_infohash(magnet),
            parsed=parsed,
        )

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
        return self.from_fields(
            link=record.get("link", ""),
            name=record.get("name", ""),
            size=record.get("size", "0"),
            seeds=record.get("seeds"),
            leech=record.get("leech"),
            engine_url=record.get("engine_url", ""),
            desc_link=record.get("desc_link"),
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
