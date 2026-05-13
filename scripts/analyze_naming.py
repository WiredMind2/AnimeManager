"""Analyze torrent-result naming conventions from the gathered samples.

Reads ``scripts/_search_samples/*.json`` produced by ``run_search_samples.py``
and emits a structured report of the patterns observed for:

* publisher / release-group (the bracketed prefix or known suffix tag);
* video quality (resolution, source, codec, bit-depth);
* season (S1, Season 2, Part II, Cour 2...);
* episode (- 12, EP12, Episode 12, E12, 1080p..1085...).

The output is written to ``scripts/_search_samples/_analysis.json`` and a
human readable summary is printed to stdout.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "scripts" / "_search_samples"


# --------------------------------------------------------------------------- #
# Regex catalogue
# --------------------------------------------------------------------------- #

# Group / publisher tags are usually in square brackets at the start, but
# sometimes they appear as a free-standing token at the end (".-GROUP" or
# trailing "[GROUP]").
PUBLISHER_HEAD_BRACKET = re.compile(r"^\s*\[([^\]]{1,40})\]")
PUBLISHER_TAIL_DASH = re.compile(r"[-_.]([A-Z][A-Za-z0-9]{2,20})\s*(?:\.(?:mkv|mp4|avi))?\s*$")
PUBLISHER_TAIL_BRACKET = re.compile(r"\[([A-Za-z][A-Za-z0-9._-]{1,20})\]\s*(?:\.(?:mkv|mp4|avi))?\s*$")

# Quality / resolution / source / codec
RESOLUTION_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:(\d{3,4})p|(\d{3,4})x(\d{3,4})|(4k|uhd))(?![A-Za-z0-9])",
    re.IGNORECASE,
)
SOURCE_RE = re.compile(
    r"\b(BluRay|BD(?:Rip|MV)?|BDRemux|WEB[- ]?DL|WEB[- ]?Rip|WEBRip|WEB|HDTV|DVDRip|DVD|TVRip|HDRip|CR|FUNi|AMZN|NF|HULU|DSNP|VRV|HiDIVE|ABEMA|BILI|iQ|TVER)\b",
    re.IGNORECASE,
)
CODEC_RE = re.compile(
    r"\b(x265|x264|HEVC|AVC|H[. ]?265|H[. ]?264|H264|H265|AV1|VP9|10[- ]?bit|8[- ]?bit)\b",
    re.IGNORECASE,
)
AUDIO_RE = re.compile(
    r"\b(FLAC|AAC(?:2\.0)?|AC3|EAC3|DTS(?:-HD)?|MP3|Opus|TrueHD|DDP\d?\.\d|DD\+?\d?\.\d)\b",
    re.IGNORECASE,
)
DUAL_AUDIO_RE = re.compile(r"\b(Dual[- ]?Audio|Multi[- ]?Audio|Eng[- ]?Sub(?:s|bed)?|Multi[- ]?Sub(?:s|bed)?)\b", re.IGNORECASE)

# Season patterns
SEASON_PATTERNS = [
    re.compile(r"\bS(\d{1,2})(?:E\d{1,3})?\b"),                # S2, S02E10
    re.compile(r"\bSeason[\s._-]*(\d{1,2})\b", re.IGNORECASE),  # Season 2
    re.compile(r"\b(?:Part|Cour)[\s._-]*([0-9IVX]{1,3})\b", re.IGNORECASE),  # Part II, Cour 2
    re.compile(r"\bS\.(\d{1,2})\b"),                            # S.2
]

# Episode patterns
EPISODE_PATTERNS = [
    ("SxxExx",        re.compile(r"\bS\d{1,2}E(\d{1,3})\b")),
    ("Exx",           re.compile(r"\bE(\d{2,3})\b")),                        # bare E12, E012
    ("EPxxx",         re.compile(r"\bEP[\s._-]?(\d{1,3})\b", re.IGNORECASE)),
    ("Episode xx",    re.compile(r"\bEpisode[\s._-]+(\d{1,3})\b", re.IGNORECASE)),
    ("- xx",          re.compile(r"\s-\s(\d{1,3})(?:v\d)?\s")),               # " - 12 "
    ("- xx (end)",    re.compile(r"\s-\s(\d{1,3})(?:v\d)?\s*$")),
    ("xxofyy",        re.compile(r"\b(\d{1,3})\s*of\s*\d{1,3}\b", re.IGNORECASE)),
]

# Batch / range detectors
BATCH_PATTERNS = [
    re.compile(r"\b(\d{2,4})\s*[-~]\s*(\d{2,4})\b"),     # 001-1071, 01~12
    re.compile(r"\b(?:batch|complete|season\s*pack)\b", re.IGNORECASE),
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

KNOWN_GROUPS = {
    "subsplease", "erai-raws", "erai", "judas", "ember", "asw", "anime time",
    "toonshub", "hatsubs", "hakata ramen", "lostyears", "smurf", "yameii",
    "commie", "horriblesubs", "puyasubs!", "puyasubs", "ohys-raws", "ohys",
    "doki", "mtbb", "yamato", "anonymous", "judassubs", "anonymeow", "kawaiika",
    "anidl", "bluelobster", "anime chap", "anime kaizoku", "varyg", "naruse",
    "mezashite", "underwater", "ggkthx", "smc", "owlf",
}


def iter_results() -> Iterable[tuple[str, dict]]:
    for path in sorted(SAMPLES_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                rows = json.load(fh)
        except Exception:
            continue
        for row in rows:
            yield path.stem, row


def extract_publisher(name: str) -> tuple[str | None, str]:
    """Return (publisher, position) -- position is "head"/"tail"/"none"."""
    m = PUBLISHER_HEAD_BRACKET.match(name)
    if m:
        return m.group(1).strip(), "head"
    m = PUBLISHER_TAIL_BRACKET.search(name)
    if m and m.group(1).strip().lower() not in {"mkv", "mp4"}:
        # Avoid picking up CRC checksums (8 hex chars) or simple resolutions.
        candidate = m.group(1).strip()
        if not re.fullmatch(r"[0-9A-F]{8}", candidate, re.IGNORECASE):
            return candidate, "tail"
    m = PUBLISHER_TAIL_DASH.search(name)
    if m:
        return m.group(1).strip(), "tail-dash"
    return None, "none"


def extract_quality(name: str) -> dict:
    out: dict = {}
    m = RESOLUTION_RE.search(name)
    if m:
        if m.group(1):
            out["resolution"] = f"{m.group(1)}p"
        elif m.group(2):
            out["resolution"] = f"{m.group(2)}x{m.group(3)}"
        elif m.group(4):
            out["resolution"] = m.group(4).lower()
    src = SOURCE_RE.search(name)
    if src:
        out["source"] = src.group(1).upper().replace(" ", "-")
    codec = CODEC_RE.search(name)
    if codec:
        out["codec"] = codec.group(1).upper().replace(" ", "").replace(".", "")
    audio = AUDIO_RE.search(name)
    if audio:
        out["audio"] = audio.group(1).upper()
    if DUAL_AUDIO_RE.search(name):
        out["dual_audio_or_multisub"] = True
    return out


def extract_season(name: str) -> tuple[str | None, str | None]:
    for pat in SEASON_PATTERNS:
        m = pat.search(name)
        if m:
            return m.group(1), pat.pattern
    return None, None


def extract_episode(name: str) -> tuple[str | None, str | None]:
    for label, pat in EPISODE_PATTERNS:
        m = pat.search(name)
        if m:
            return m.group(1), label
    return None, None


def is_batch(name: str) -> bool:
    for pat in BATCH_PATTERNS:
        if pat.search(name):
            return True
    return False


# --------------------------------------------------------------------------- #
# Main analysis
# --------------------------------------------------------------------------- #

def main() -> int:
    pub_head_counts: Counter[str] = Counter()
    pub_tail_counts: Counter[str] = Counter()
    pub_missing = 0

    resolution_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    codec_counts: Counter[str] = Counter()
    audio_counts: Counter[str] = Counter()

    season_pattern_hits: Counter[str] = Counter()
    season_values: Counter[str] = Counter()

    episode_pattern_hits: Counter[str] = Counter()
    episode_missing = 0

    batch_count = 0
    total = 0
    per_query: dict[str, int] = defaultdict(int)

    pattern_examples: dict[str, list[str]] = defaultdict(list)
    no_publisher_examples: list[str] = []
    no_episode_examples: list[str] = []

    for query, row in iter_results():
        total += 1
        per_query[query] += 1
        name = row.get("name") or ""

        publisher, pos = extract_publisher(name)
        if publisher is None:
            pub_missing += 1
            if len(no_publisher_examples) < 25:
                no_publisher_examples.append(name)
        elif pos == "head":
            pub_head_counts[publisher.lower()] += 1
        else:
            pub_tail_counts[publisher.lower()] += 1

        quality = extract_quality(name)
        if "resolution" in quality:
            resolution_counts[quality["resolution"]] += 1
        if "source" in quality:
            source_counts[quality["source"]] += 1
        if "codec" in quality:
            codec_counts[quality["codec"]] += 1
        if "audio" in quality:
            audio_counts[quality["audio"]] += 1

        season, season_pat = extract_season(name)
        if season:
            season_pattern_hits[season_pat or "?"] += 1
            season_values[season] += 1

        ep, ep_label = extract_episode(name)
        if ep:
            episode_pattern_hits[ep_label or "?"] += 1
            if ep_label and len(pattern_examples[ep_label]) < 5:
                pattern_examples[ep_label].append(name)
        else:
            episode_missing += 1
            if len(no_episode_examples) < 25:
                no_episode_examples.append(name)

        if is_batch(name):
            batch_count += 1

    report = {
        "totals": {
            "results_analyzed": total,
            "by_query": dict(per_query),
            "batches_detected": batch_count,
        },
        "publishers": {
            "missing": pub_missing,
            "top_head_bracketed": pub_head_counts.most_common(40),
            "top_tail_tag": pub_tail_counts.most_common(30),
        },
        "quality": {
            "resolutions": resolution_counts.most_common(),
            "sources": source_counts.most_common(),
            "codecs": codec_counts.most_common(),
            "audio": audio_counts.most_common(),
        },
        "season": {
            "patterns": season_pattern_hits.most_common(),
            "values": season_values.most_common(10),
        },
        "episode": {
            "patterns": episode_pattern_hits.most_common(),
            "missing": episode_missing,
            "examples_by_pattern": {k: v[:3] for k, v in pattern_examples.items()},
        },
        "samples": {
            "no_publisher": no_publisher_examples[:10],
            "no_episode": no_episode_examples[:10],
        },
    }

    out = SAMPLES_DIR / "_analysis.json"
    with out.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    def header(text: str) -> None:
        print(f"\n=== {text} ===")

    print(f"Total results analyzed: {total}")
    print(f"  per query: {dict(per_query)}")
    header("Resolutions")
    for k, v in resolution_counts.most_common():
        print(f"  {v:5d}  {k}")
    header("Sources")
    for k, v in source_counts.most_common():
        print(f"  {v:5d}  {k}")
    header("Codecs")
    for k, v in codec_counts.most_common():
        print(f"  {v:5d}  {k}")
    header("Audio")
    for k, v in audio_counts.most_common():
        print(f"  {v:5d}  {k}")
    header("Publisher (head bracket) -- top 20")
    for k, v in pub_head_counts.most_common(20):
        print(f"  {v:5d}  [{k}]")
    print(f"  missing publisher: {pub_missing}")
    header("Season patterns")
    for k, v in season_pattern_hits.most_common():
        print(f"  {v:5d}  {k}")
    header("Episode patterns")
    for k, v in episode_pattern_hits.most_common():
        print(f"  {v:5d}  {k}")
    print(f"  no episode detected: {episode_missing}")
    print(f"\nFull analysis written to {out}")
    print("\n-- Examples of titles WITHOUT detected publisher --")
    for n in no_publisher_examples[:8]:
        print(f"  - {n}")
    print("\n-- Examples of titles WITHOUT detected episode --")
    for n in no_episode_examples[:8]:
        print(f"  - {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
