"""Heuristic parser for torrent release titles.

Extracts a small, structured ``ParsedTitle`` view of a free-form
``name`` field returned by the nova3 engines. The parser is intentionally
fail-soft: every facet is optional and a title that cannot be classified
still produces a valid (mostly-empty) ``ParsedTitle`` instance.

See ``docs/research/torrent_title_parsing.md`` for the corpus study that
drove the regex priorities and edge-case handling.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #


class Codec(str, Enum):
    H264 = "H.264"
    H265 = "H.265"
    AV1 = "AV1"
    VP9 = "VP9"
    OTHER = "OTHER"


class Source(str, Enum):
    BLURAY = "BluRay"
    WEBDL = "WEB-DL"
    WEBRIP = "WEBRip"
    HDTV = "HDTV"
    DVD = "DVD"
    TVRIP = "TVRip"
    OTHER = "OTHER"


class EpisodeKind(str, Enum):
    SINGLE = "single"
    RANGE = "range"
    NONE = "none"


class PublisherSource(str, Enum):
    HEAD_BRACKET = "head_bracket"
    CJK_BRACKET = "cjk_bracket"
    TAIL_DASH = "tail_dash"
    NONE = "none"


# --------------------------------------------------------------------------- #
# Vocabulary tables
# --------------------------------------------------------------------------- #

# Tokens that should NEVER be treated as a publisher. Used to validate
# the tail-dash candidate and any low-quality head-bracket match. Kept
# lowercased and free of punctuation.
_METADATA_TOKENS: frozenset[str] = frozenset(
    {
        # resolution
        "1080p", "720p", "480p", "2160p", "4k", "uhd", "1440p", "576p",
        # source tags
        "bluray", "bdrip", "bdremux", "bd-remux", "bd", "bdmv",
        "web", "webdl", "web-dl", "webrip", "web-rip",
        "hdtv", "dvd", "dvdrip", "tvrip", "hdrip",
        # streaming services
        "cr", "amzn", "nf", "funi", "vrv", "hidive", "abema",
        "bili", "iq", "tver", "dsnp", "hulu",
        # codecs
        "x264", "x265", "hevc", "avc", "h264", "h265", "h.264", "h.265",
        "av1", "vp9", "10bit", "10-bit", "8bit", "8-bit",
        # audio
        "aac", "aac2.0", "ac3", "eac3", "e-ac-3", "ddp", "ddp2.0", "ddp5.1",
        "flac", "opus", "mp3", "truehd", "dts", "dts-hd",
        # language/subs
        "multi", "multisubs", "multi-subs", "multi-sub", "dual-audio",
        "dual", "vostfr", "vf", "vff", "vfq", "eng", "engsub", "eng-sub",
        # misc
        "mkv", "mp4", "avi", "batch", "complete", "season",
        "pack", "raws", "subs", "ddl", "rerip",
    }
)

# Source token -> canonical Source enum. Order matters: more specific
# tokens (e.g. BDREMUX) are listed before generic ones (BD).
_SOURCE_ALIASES: tuple[tuple[str, Source], ...] = (
    ("BDREMUX", Source.BLURAY),
    ("BD-REMUX", Source.BLURAY),
    ("BLURAY", Source.BLURAY),
    ("BLU-RAY", Source.BLURAY),
    ("BDRIP", Source.BLURAY),
    ("BDMV", Source.BLURAY),
    ("BD", Source.BLURAY),
    ("WEB-DL", Source.WEBDL),
    ("WEBDL", Source.WEBDL),
    ("WEB-RIP", Source.WEBRIP),
    ("WEBRIP", Source.WEBRIP),
    ("WEB", Source.WEBDL),
    ("HDTV", Source.HDTV),
    ("DVDRIP", Source.DVD),
    ("DVD", Source.DVD),
    ("TVRIP", Source.TVRIP),
)

# Streaming-service tag -> canonical short name. Kept separate from the
# source enum because a single release can list both (e.g. "CR WEB-DL").
_PROVIDER_ALIASES: tuple[tuple[str, str], ...] = (
    ("CR", "CR"),
    ("AMZN", "AMZN"),
    ("NF", "NF"),
    ("FUNI", "FUNi"),
    ("HIDIVE", "HiDIVE"),
    ("HULU", "Hulu"),
    ("VRV", "VRV"),
    ("ABEMA", "ABEMA"),
    ("BILI", "BiliBili"),
    ("IQ", "iQ"),
    ("IQIYI", "iQ"),
    ("TVER", "TVER"),
    ("DSNP", "Disney+"),
)

# Codec aliases -> canonical Codec enum.
_CODEC_ALIASES: tuple[tuple[re.Pattern[str], Codec], ...] = (
    (re.compile(r"\b(?:x265|HEVC|H[.\s-]?265|H265)\b", re.IGNORECASE), Codec.H265),
    (re.compile(r"\b(?:x264|H[.\s-]?264|H264|AVC)\b", re.IGNORECASE), Codec.H264),
    (re.compile(r"\bAV1\b", re.IGNORECASE), Codec.AV1),
    (re.compile(r"\bVP9\b", re.IGNORECASE), Codec.VP9),
)


# --------------------------------------------------------------------------- #
# Regex catalogue
# --------------------------------------------------------------------------- #

_RE_CRC_TAIL = re.compile(r"\s*\[[0-9A-Fa-f]{8}\]\s*$")
_RE_EXTENSION = re.compile(r"\s*\.(mkv|mp4|avi|m4v|mov|ts|webm)\s*$", re.IGNORECASE)
# Trailing parenthetical metadata that we strip iteratively before
# applying the tail-dash publisher heuristic. Capturing groups must
# stay disabled so the strip is safe to run multiple times.
_RE_TRAILING_PAREN = re.compile(r"\s*\([^()]*\)\s*$")

_RE_PUB_HEAD = re.compile(r"^\s*\[([^\]]{1,60})\]")
_RE_PUB_CJK = re.compile(r"^\s*【([^】]{1,60})】")
_RE_PUB_TAIL_DASH = re.compile(
    r"-([A-Za-z][A-Za-z0-9_]{1,20}(?:-[A-Za-z][A-Za-z0-9_]{1,20})?)\s*$"
)

_RE_RESOLUTION = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    # Anamorphic / explicit hybrid form first (e.g. "1920x1080p"):
    r"(?P<wp>\d{3,4})x(?P<hp>\d{3,4})p"
    # Bare "1080p":
    r"|(?P<p>\d{3,4})p"
    # WxH without trailing p (e.g. "1920x1080"):
    r"|(?P<w>\d{3,4})x(?P<h>\d{3,4})"
    # Marketing names:
    r"|(?P<uhd>4k|uhd)"
    r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)

_RE_AUDIO = re.compile(
    r"\b("
    r"FLAC|AAC(?:2\.0|5\.1)?|AC3|E-?AC-?3|EAC3|DTS(?:-HD)?|MP3|Opus|"
    r"TrueHD|DDP\d?\.?\d?|DD\+?\d?\.?\d?|LPCM"
    r")\b",
    re.IGNORECASE,
)
_RE_BITDEPTH = re.compile(r"\b(10|8)[-\s]?bit\b", re.IGNORECASE)
_RE_DUAL_AUDIO = re.compile(r"\b(Dual[-\s]?Audio|Multi[-\s]?Audio)\b", re.IGNORECASE)
_RE_MULTI_SUB = re.compile(r"\b(Multi[-\s]?Sub(?:s|titles?)?|Multiple Subtitle)\b", re.IGNORECASE)
_RE_VOSTFR = re.compile(r"\b(VOSTFR|VOST[A-Z]{2,3}|VFF?|VFQ)\b")
_RE_ENGSUB = re.compile(r"\b(Eng[-\s]?Sub(?:s|bed)?|English[-\s]?Sub(?:s|bed)?)\b", re.IGNORECASE)

# Season patterns -- priority order
_RE_SEASON_SXX = re.compile(r"\bSS?(\d{1,2})(?:E\d{1,3})?\b")
_RE_SEASON_WORD = re.compile(r"\bSeason[\s._-]*(\d{1,2})\b", re.IGNORECASE)
_RE_SEASON_PART = re.compile(
    r"\b(?:Part|Cour)[\s._-]*([0-9]{1,2}|[IVX]{1,4})\b", re.IGNORECASE
)

# Episode patterns -- priority order
_RE_EP_SXXEXX = re.compile(r"\bS\d{1,2}E(\d{1,3})(?:v\d{1,2})?\b")
_RE_EP_EP = re.compile(r"\bEP[\s._-]?(\d{1,4})\b", re.IGNORECASE)
_RE_EP_BARE_E = re.compile(r"\bE(\d{2,3})\b")
_RE_EP_EPISODE = re.compile(r"\bEpisode[\s._-]+(\d{1,3})\b", re.IGNORECASE)
_RE_EP_DASH = re.compile(r"\s-\s(\d{1,4})(?:v\d)?(?=\s|$)")
_RE_EP_RANGE_PAREN = re.compile(r"\((\d{1,3})\s*[-~]\s*(\d{1,3})\)")
_RE_EP_RANGE_TILDE = re.compile(r"\b(\d{1,3})\s*~\s*(\d{1,3})\b")
_RE_EP_RANGE_DASH = re.compile(r"\b(\d{1,3})\s*-\s*(\d{1,4})\b")
_RE_EP_OF = re.compile(r"\b(\d{1,3})\s+of\s+(\d{1,3})\b", re.IGNORECASE)

_RE_BATCH_KEYWORD = re.compile(
    r"\b(batch|complete|season[\s._-]*pack|bd[-\s]?box)\b", re.IGNORECASE
)
_RE_YEAR = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")

_ROMAN: dict[str, int] = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
}


# --------------------------------------------------------------------------- #
# Dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ParsedTitle:
    """Structured view of a release title.

    Every field is optional; consumers should treat any combination of
    ``None`` values as "unknown for this facet" rather than as an
    error. ``parse_confidence`` is a 0..1 score over the four headline
    facets (publisher, resolution, season, episode) so UIs can de-rank
    rows with too little information instead of dropping them.
    """

    raw: str

    publisher: Optional[str] = None
    publisher_display: Optional[str] = None
    publisher_source: PublisherSource = PublisherSource.NONE

    resolution: Optional[str] = None
    source: Optional[Source] = None
    provider: Optional[str] = None
    codec: Optional[Codec] = None
    bit_depth: Optional[int] = None
    audio: Optional[str] = None

    season: Optional[int] = None
    season_source: Optional[str] = None

    episode_kind: EpisodeKind = EpisodeKind.NONE
    episode: Optional[int] = None
    episode_start: Optional[int] = None
    episode_end: Optional[int] = None

    is_batch: bool = False
    languages: Tuple[str, ...] = field(default_factory=tuple)

    crc: Optional[str] = None
    extension: Optional[str] = None
    year: Optional[int] = None

    parse_confidence: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly dict (enums coerced to strings)."""
        data = asdict(self)
        # Enums serialise as their string value via str.Enum, but
        # dataclasses.asdict returns the enum object -- normalise.
        data["publisher_source"] = self.publisher_source.value
        data["source"] = self.source.value if self.source else None
        data["codec"] = self.codec.value if self.codec else None
        data["episode_kind"] = self.episode_kind.value
        data["languages"] = list(self.languages)
        return data


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def parse_title(name: str) -> ParsedTitle:
    """Parse ``name`` into a ``ParsedTitle``.

    The function is total: it always returns a ``ParsedTitle`` and
    never raises. Empty / non-string inputs yield an empty record.
    """
    if not isinstance(name, str) or not name:
        return ParsedTitle(raw=name or "")

    cleaned = unicodedata.normalize("NFKC", name)

    # Strip the trailing CRC and file extension *for matching only*; we
    # keep ``raw`` untouched so the UI can still show the original.
    # The extension comes first so the CRC regex (anchored on `$`) can
    # see the `[XXXXXXXX]` bracket even when the original ended in `.mkv`.
    extension = _extract_extension(cleaned)
    working = _RE_EXTENSION.sub("", cleaned)
    crc = _extract_crc(working)
    working = _RE_CRC_TAIL.sub("", working)

    # Replace dot/underscore separators with spaces in the working copy
    # so scene-style releases ("Bocchi.the.Rock.S01.1080p...") match the
    # same regexes as bracketed ones. We only do this *after* the
    # publisher tail-dash candidate has been computed so the dash
    # rule isn't confused by sentence-style names.
    pub, pub_display, pub_source, working_no_pub = _extract_publisher(working)
    normalized = _normalise_for_matching(working_no_pub)

    resolution = _extract_resolution(normalized)
    source_enum = _extract_source(normalized)
    provider = _extract_provider(normalized)
    codec = _extract_codec(normalized)
    bit_depth = _extract_bit_depth(normalized)
    audio = _extract_audio(normalized)
    languages = _extract_languages(normalized)

    season, season_source = _extract_season(normalized)
    ep_kind, ep, ep_start, ep_end = _extract_episode(normalized, season)
    is_batch = _detect_batch(normalized, ep_kind)
    year = _extract_year(normalized)

    # When we see an explicit batch keyword but no episode range, we
    # mark it as RANGE(None, None) so the UI can still filter it as a
    # batch without inventing fake boundaries.
    if is_batch and ep_kind == EpisodeKind.NONE:
        ep_kind = EpisodeKind.RANGE

    confidence = _confidence(pub, resolution, season, ep_kind)

    return ParsedTitle(
        raw=name,
        publisher=pub,
        publisher_display=pub_display,
        publisher_source=pub_source,
        resolution=resolution,
        source=source_enum,
        provider=provider,
        codec=codec,
        bit_depth=bit_depth,
        audio=audio,
        season=season,
        season_source=season_source,
        episode_kind=ep_kind,
        episode=ep,
        episode_start=ep_start,
        episode_end=ep_end,
        is_batch=is_batch,
        languages=tuple(languages),
        crc=crc,
        extension=extension,
        year=year,
        parse_confidence=confidence,
    )


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


def _extract_crc(text: str) -> Optional[str]:
    m = _RE_CRC_TAIL.search(text)
    if not m:
        return None
    return m.group(0).strip().strip("[]").upper()


def _extract_extension(text: str) -> Optional[str]:
    m = _RE_EXTENSION.search(text)
    if not m:
        return None
    return "." + m.group(1).lower()


def _is_metadata_token(token: str) -> bool:
    """Return True when ``token`` is part of the metadata vocabulary."""
    lowered = token.lower().strip()
    if not lowered:
        return True
    if lowered in _METADATA_TOKENS:
        return True
    # Resolutions inside a token (e.g. "1080p"): be defensive.
    if _RE_RESOLUTION.fullmatch(lowered):
        return True
    return False


def _extract_publisher(
    text: str,
) -> tuple[Optional[str], Optional[str], PublisherSource, str]:
    """Detect publisher in priority order and strip it from the working copy."""
    m = _RE_PUB_HEAD.match(text)
    if m:
        candidate = m.group(1).strip()
        if not _is_metadata_token(candidate):
            stripped = text[m.end():].lstrip(" -_.")
            return _canonicalise_publisher(candidate), candidate, PublisherSource.HEAD_BRACKET, stripped

    m = _RE_PUB_CJK.match(text)
    if m:
        candidate = m.group(1).strip()
        stripped = text[m.end():].lstrip(" -_.")
        return _canonicalise_publisher(candidate), candidate, PublisherSource.CJK_BRACKET, stripped

    # Tail-dash style: applied AFTER stripping CRC/extension and any
    # trailing parenthetical metadata that might confuse the regex.
    # We iterate the paren strip until stable so "...-Group (AMZN)
    # (VOSTFR, Multi-Subs, Movie)" reduces all the way down to
    # "...-Group" before we run the dash regex.
    tail_text = text
    while True:
        stripped = _RE_TRAILING_PAREN.sub("", tail_text)
        if stripped == tail_text:
            break
        tail_text = stripped
    m = _RE_PUB_TAIL_DASH.search(tail_text)
    if m:
        candidate = m.group(1).strip()
        if not _is_metadata_token(candidate):
            stripped = tail_text[: m.start()] + tail_text[m.end():]
            stripped = stripped.rstrip(" -_.")
            return _canonicalise_publisher(candidate), candidate, PublisherSource.TAIL_DASH, stripped

    return None, None, PublisherSource.NONE, text


def _canonicalise_publisher(display: str) -> str:
    """Reduce a publisher token to a stable key for grouping/filtering."""
    return re.sub(r"\s+", " ", display).strip().lower()


def _normalise_for_matching(text: str) -> str:
    # Replace runs of dots/underscores with a space, but keep `.` inside
    # version-like tokens (`H.264`, `2.0`, `5.1`) by only collapsing
    # runs of length >= 2 and dots adjacent to whitespace/letters.
    text = re.sub(r"[_]+", " ", text)
    # Scene-style "A.B.C.D" -> "A B C D". We require the dot to be
    # surrounded by word characters of >=2 chars so version numbers
    # survive.
    text = re.sub(r"(?<=[A-Za-z]{2})\.(?=[A-Za-z]{2})", " ", text)
    # Multiple consecutive spaces -> one space.
    return re.sub(r"\s+", " ", text).strip()


def _canonical_resolution(height: int) -> str:
    if height <= 540:
        return "480p"
    if height <= 800:
        return "720p"
    if height <= 1200:
        return "1080p"
    if height <= 1600:
        return "1440p"
    if height <= 2400:
        return "2160p"
    return f"{height}p"


def _extract_resolution(text: str) -> Optional[str]:
    m = _RE_RESOLUTION.search(text)
    if not m:
        return None
    if m.group("p"):
        return _canonical_resolution(int(m.group("p")))
    if m.group("hp"):
        return _canonical_resolution(int(m.group("hp")))
    if m.group("w") and m.group("h"):
        return _canonical_resolution(int(m.group("h")))
    if m.group("uhd"):
        return "2160p"
    return None


def _extract_source(text: str) -> Optional[Source]:
    upper = text.upper()
    for token, canonical in _SOURCE_ALIASES:
        # Use word-boundary-ish matching on the upper-cased copy so
        # `WEB-DL` doesn't match `MULTi-VARYG-WEB` style words.
        pattern = re.compile(rf"(?:^|[^A-Z0-9]){re.escape(token)}(?:[^A-Z0-9]|$)")
        if pattern.search(upper):
            return canonical
    return None


def _extract_provider(text: str) -> Optional[str]:
    upper = text.upper()
    for token, label in _PROVIDER_ALIASES:
        pattern = re.compile(rf"(?:^|[^A-Z0-9]){re.escape(token)}(?:[^A-Z0-9]|$)")
        if pattern.search(upper):
            return label
    return None


def _extract_codec(text: str) -> Optional[Codec]:
    for pattern, codec in _CODEC_ALIASES:
        if pattern.search(text):
            return codec
    return None


def _extract_bit_depth(text: str) -> Optional[int]:
    m = _RE_BITDEPTH.search(text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _extract_audio(text: str) -> Optional[str]:
    m = _RE_AUDIO.search(text)
    if not m:
        return None
    return m.group(1).upper()


def _extract_languages(text: str) -> list[str]:
    out: list[str] = []
    if _RE_DUAL_AUDIO.search(text):
        out.append("dual-audio")
    if _RE_MULTI_SUB.search(text):
        out.append("multi-sub")
    m = _RE_VOSTFR.search(text)
    if m:
        out.append(m.group(1).lower())
    if _RE_ENGSUB.search(text):
        out.append("eng-sub")
    return out


def _extract_season(text: str) -> tuple[Optional[int], Optional[str]]:
    m = _RE_SEASON_SXX.search(text)
    if m:
        try:
            return int(m.group(1)), "sxx"
        except ValueError:
            pass
    m = _RE_SEASON_WORD.search(text)
    if m:
        try:
            return int(m.group(1)), "season_word"
        except ValueError:
            pass
    m = _RE_SEASON_PART.search(text)
    if m:
        token = m.group(1).upper()
        if token in _ROMAN:
            return _ROMAN[token], "part_cour"
        try:
            return int(token), "part_cour"
        except ValueError:
            pass
    return None, None


def _looks_like_year(value: int) -> bool:
    return 1900 <= value <= 2099


def _extract_episode(
    text: str, season_hint: Optional[int]
) -> tuple[EpisodeKind, Optional[int], Optional[int], Optional[int]]:
    # 1. SxxExx -- highest confidence, never a false positive.
    m = _RE_EP_SXXEXX.search(text)
    if m:
        return EpisodeKind.SINGLE, _safe_int(m.group(1)), None, None

    # 2. Range patterns -- check before the bare `- xx` form so
    # "01-12" inside parens / next to a dash isn't read as a single
    # episode "01" with a leftover dash.
    for pat in (_RE_EP_RANGE_PAREN, _RE_EP_RANGE_TILDE):
        m = pat.search(text)
        if m:
            return EpisodeKind.RANGE, None, _safe_int(m.group(1)), _safe_int(m.group(2))
    m = _RE_EP_OF.search(text)
    if m:
        return EpisodeKind.RANGE, None, _safe_int(m.group(1)), _safe_int(m.group(2))
    m = _RE_EP_RANGE_DASH.search(text)
    if m:
        start = _safe_int(m.group(1))
        end = _safe_int(m.group(2))
        # Avoid reading "10-bit" / "AAC2.0" leftovers: range is only a
        # range when end > start and neither side looks like a year.
        if (
            start is not None
            and end is not None
            and end > start
            and not _looks_like_year(end)
            and not _looks_like_year(start)
        ):
            return EpisodeKind.RANGE, None, start, end

    # 3. EP123 / E12 / Episode 12 / bare " - xx "
    for pat, label in (
        (_RE_EP_EP, "ep"),
        (_RE_EP_BARE_E, "bare_e"),
        (_RE_EP_EPISODE, "episode"),
    ):
        m = pat.search(text)
        if m:
            return EpisodeKind.SINGLE, _safe_int(m.group(1)), None, None

    m = _RE_EP_DASH.search(text)
    if m:
        value = _safe_int(m.group(1))
        # Guard against years masquerading as episode numbers.
        if value is not None and not (1900 <= value <= 2099):
            return EpisodeKind.SINGLE, value, None, None

    return EpisodeKind.NONE, None, None, None


def _safe_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _detect_batch(text: str, ep_kind: EpisodeKind) -> bool:
    if ep_kind == EpisodeKind.RANGE:
        return True
    return bool(_RE_BATCH_KEYWORD.search(text))


def _extract_year(text: str) -> Optional[int]:
    m = _RE_YEAR.search(text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _confidence(
    publisher: Optional[str],
    resolution: Optional[str],
    season: Optional[int],
    ep_kind: EpisodeKind,
) -> float:
    score = 0.0
    if publisher:
        score += 0.25
    if resolution:
        score += 0.25
    if season is not None:
        score += 0.25
    if ep_kind != EpisodeKind.NONE:
        score += 0.25
    return round(score, 2)


__all__ = [
    "Codec",
    "Source",
    "EpisodeKind",
    "PublisherSource",
    "ParsedTitle",
    "parse_title",
]
