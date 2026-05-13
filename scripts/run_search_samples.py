"""One-off script to gather torrent search samples for naming-convention research.

Runs a batch of searches against the regular SearchFacade and writes the raw
results to JSON files under ``scripts/_search_samples`` for further analysis.

Usage:
    python -m scripts.run_search_samples
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from adapters.search.config import INTERACTIVE_PROFILE  # noqa: E402
from adapters.search.facade import SearchFacade  # noqa: E402

SAMPLE_QUERIES = [
    "One Piece",
    "Frieren",
    "Bocchi the Rock",
    "Demon Slayer",
    "Spy x Family",
    "Jujutsu Kaisen",
    "Chainsaw Man",
    "Solo Leveling",
    "Re Zero",
    "Attack on Titan",
    "Konosuba",
    "Mushoku Tensei",
]

OUT_DIR = ROOT / "scripts" / "_search_samples"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def safe_name(query: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in query.lower()).strip("_")


def main() -> int:
    facade = SearchFacade(profile=INTERACTIVE_PROFILE)
    summary = []

    for q in SAMPLE_QUERIES:
        out = OUT_DIR / f"{safe_name(q)}.json"
        if out.exists() and out.stat().st_size > 0:
            print(f"[skip] {q} (cached -> {out.name})")
            try:
                with out.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                summary.append({"query": q, "count": len(data), "cached": True})
            except Exception:
                summary.append({"query": q, "count": 0, "cached": True})
            continue

        print(f"[search] {q!r}")
        start = time.monotonic()
        try:
            rows = list(facade.search([q]))
        except Exception as exc:
            print(f"  !! search failed: {exc}")
            rows = []
        dur = time.monotonic() - start
        print(f"  -> {len(rows)} rows in {dur:.1f}s")

        with out.open("w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=2)
        summary.append({"query": q, "count": len(rows), "duration_s": round(dur, 2)})

    with (OUT_DIR / "_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    print("\n== summary ==")
    for entry in summary:
        print(entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
