"""Run the new title parser over the entire corpus to sanity-check it.

Reports parser recall on the four headline facets (publisher, resolution,
season, episode) and lists the lowest-confidence examples so we can spot
regressions while iterating on the regexes.
"""

from __future__ import annotations

import io
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from adapters.search.title_parser import EpisodeKind, parse_title  # noqa: E402

SAMPLES = ROOT / "scripts" / "_search_samples"


def main() -> int:
    total = 0
    pub_hits = 0
    res_hits = 0
    season_hits = 0
    ep_hits = 0
    batch_hits = 0

    pub_sources: Counter[str] = Counter()
    confidence_buckets: Counter[str] = Counter()
    low_confidence: list[tuple[float, str, dict]] = []
    publishers: Counter[str] = Counter()
    codecs: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    providers: Counter[str] = Counter()
    resolutions: Counter[str] = Counter()

    for p in sorted(SAMPLES.glob("*.json")):
        if p.name.startswith("_"):
            continue
        with p.open("r", encoding="utf-8") as fh:
            rows = json.load(fh)
        for row in rows:
            name = row.get("name") or ""
            if not name:
                continue
            total += 1
            parsed = parse_title(name)
            if parsed.publisher:
                pub_hits += 1
                publishers[parsed.publisher] += 1
            if parsed.resolution:
                res_hits += 1
                resolutions[parsed.resolution] += 1
            if parsed.season is not None:
                season_hits += 1
            if parsed.episode_kind != EpisodeKind.NONE:
                ep_hits += 1
            if parsed.is_batch:
                batch_hits += 1
            pub_sources[parsed.publisher_source.value] += 1
            if parsed.codec:
                codecs[parsed.codec.value] += 1
            if parsed.source:
                sources[parsed.source.value] += 1
            if parsed.provider:
                providers[parsed.provider] += 1
            bucket = f"{parsed.parse_confidence:.2f}"
            confidence_buckets[bucket] += 1
            if parsed.parse_confidence <= 0.25:
                if len(low_confidence) < 20:
                    low_confidence.append((parsed.parse_confidence, name, parsed.as_dict()))

    def pct(n: int) -> str:
        return f"{n} ({n / total * 100:.1f}%)" if total else "0"

    print(f"Analysed {total} titles\n")
    print(f"  publisher:  {pct(pub_hits)}")
    print(f"  resolution: {pct(res_hits)}")
    print(f"  season:     {pct(season_hits)}")
    print(f"  episode:    {pct(ep_hits)}")
    print(f"  batch:      {pct(batch_hits)}")
    print()
    print("publisher_source distribution:")
    for k, v in pub_sources.most_common():
        print(f"  {k:>14}: {v}")
    print()
    print("confidence buckets:")
    for k, v in sorted(confidence_buckets.items(), reverse=True):
        print(f"  {k}: {v}")
    print()
    print("top publishers (canonical):")
    for k, v in publishers.most_common(10):
        print(f"  {v:5d}  {k}")
    print("resolutions:")
    for k, v in resolutions.most_common():
        print(f"  {v:5d}  {k}")
    print("codecs:")
    for k, v in codecs.most_common():
        print(f"  {v:5d}  {k}")
    print("sources:")
    for k, v in sources.most_common():
        print(f"  {v:5d}  {k}")
    print("providers:")
    for k, v in providers.most_common():
        print(f"  {v:5d}  {k}")

    print("\nlow-confidence examples (<=0.25):")
    for conf, name, _ in low_confidence:
        print(f"  conf={conf}  {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
