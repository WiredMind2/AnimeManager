"""Compare recent SubsPlease Nyaa releases against local catalog search terms.

Fetches the subsplease user page, parses release show titles, attempts to
match them to anime rows in the local database, and reports whether the
current query planner would emit a term that finds each release on nyaa.

Usage:
    .\\.venv\\Scripts\\python.exe scripts/analyze_subsplease_titles.py
    .\\.venv\\Scripts\\python.exe scripts/analyze_subsplease_titles.py --pages 3
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from adapters.search.config import load_profile  # noqa: E402
from adapters.search.planner import plan_terms  # noqa: E402
from adapters.search.subsplease import (  # noqa: E402
    parse_subsplease_release,
    release_matches_catalog,
)
from clients.http import web as http_web  # noqa: E402
from clients.sdk import ClientSDK  # noqa: E402

NYAA_USER = "https://nyaa.si/user/subsplease?f=0&c=1_0"
OUT_DIR = ROOT / "scripts" / "_search_samples"
_MAGNET_DN = re.compile(r"dn=([^&\"]+)", re.IGNORECASE)
_RELEASE_FALLBACK = re.compile(
    r"\[SubsPlease\][^\n<]+?(?:\.mkv|\[Batch\])",
    re.IGNORECASE,
)


@dataclass
class ReleaseReport:
    show_title: str
    sample_name: str
    matched_anime_id: int | None
    matched_catalog_title: str | None
    planned_terms: list[str]
    would_find_on_nyaa: bool
    match_kind: str


def fetch_nyaa_page(url: str) -> str:
    req = Request(url, headers={"User-Agent": "AnimeManager/1.0 (title research)"})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_release_names(html: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for match in _MAGNET_DN.finditer(html):
        raw = unquote(match.group(1).replace("+", " "))
        if "[SubsPlease]" not in raw:
            continue
        if raw not in seen:
            seen.add(raw)
            names.append(raw)
    if names:
        return names

    for match in _RELEASE_FALLBACK.finditer(html):
        raw = match.group(0).strip()
        if raw not in seen:
            seen.add(raw)
            names.append(raw)
    return names


def unique_show_titles(names: list[str]) -> dict[str, str]:
    """Map show title -> one sample release name."""
    out: dict[str, str] = {}
    for name in names:
        parsed = parse_subsplease_release(name)
        if not parsed:
            continue
        out.setdefault(parsed.show_title, name)
    return out


def load_catalog_index(sdk: ClientSDK) -> list[tuple[int, list[str]]]:
    """Load anime id + catalog titles for currently airing library entries."""
    rows: list[tuple[int, list[str]]] = []
    start = 0
    page_size = 50
    while start < 500:
        payload = sdk.get_anime_list(
            filter_name="AIRING", list_start=start, list_stop=start + page_size
        )
        items = payload.get("items") if isinstance(payload, dict) else None
        if not items:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            anime_id = item.get("id")
            if anime_id is None:
                continue
            catalog = http_web._catalog_titles(item)
            if catalog:
                rows.append((int(anime_id), catalog))
        if not payload.get("has_next"):
            break
        start += page_size
    return rows


def match_show_to_catalog(
    show_title: str, catalog_index: list[tuple[int, list[str]]]
) -> tuple[int | None, str | None, str]:
    for anime_id, catalog in catalog_index:
        for title in catalog:
            if release_matches_catalog(show_title, title):
                return anime_id, title, "catalog"
    return None, None, "unmatched"


def term_finds_release(term: str, show_title: str) -> bool:
    """Nyaa full-text is substring-oriented; approximate locally."""
    def norm(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", text.casefold())

    term_key = norm(term)
    show_key = norm(show_title)
    if term_key in show_key or show_key in term_key:
        return True
    term_words = [w for w in re.split(r"\s+", term.casefold()) if len(w) >= 4]
    show_lower = show_title.casefold()
    if len(term_words) >= 2 and sum(1 for w in term_words[:4] if w in show_lower) >= 2:
        return True
    norm_term = re.sub(r"\bseason\s+(\d+)\b", r"s\1", term.casefold())
    norm_show = show_title.casefold()
    if norm_term in norm_show or norm_show in norm_term:
        return True
    return False


def planned_terms_for_catalog(catalog: list[str]) -> list[str]:
    plan = plan_terms(catalog, load_profile("interactive").limits)
    return [t.normalized for t in plan.terms]


def analyze(pages: int = 2) -> dict[str, Any]:
    sdk = ClientSDK()
    catalog_index = load_catalog_index(sdk)

    all_names: list[str] = []
    for page in range(1, pages + 1):
        url = NYAA_USER if page == 1 else f"{NYAA_USER}&p={page}"
        html = fetch_nyaa_page(url)
        all_names.extend(extract_release_names(html))

    show_samples = unique_show_titles(all_names)
    reports: list[ReleaseReport] = []

    for show_title, sample_name in sorted(show_samples.items(), key=lambda x: x[0].lower()):
        anime_id, catalog_hit, kind = match_show_to_catalog(show_title, catalog_index)
        planned: list[str] = []
        would_find = False
        if anime_id is not None:
            catalog = next(c for aid, c in catalog_index if aid == anime_id)
            planned = planned_terms_for_catalog(catalog)
            would_find = any(term_finds_release(t, show_title) for t in planned)
        reports.append(
            ReleaseReport(
                show_title=show_title,
                sample_name=sample_name,
                matched_anime_id=anime_id,
                matched_catalog_title=catalog_hit,
                planned_terms=planned,
                would_find_on_nyaa=would_find,
                match_kind=kind,
            )
        )

    missed = [r for r in reports if r.matched_anime_id and not r.would_find_on_nyaa]
    unmatched = [r for r in reports if r.matched_anime_id is None]

    patterns = Counter()
    for show in show_samples:
        if " S" in show and re.search(r"\bS\d+\b", show):
            patterns["season_suffix"] += 1
        elif re.search(r"\b[A-Za-z]{2,}\-[A-Za-z]", show):
            patterns["hyphenated_romaji"] += 1
        elif len(show.split()) == 1:
            patterns["single_word_nickname"] += 1
        elif show.endswith("."):
            patterns["trailing_period"] += 1
        elif " - " in show:
            patterns["compound_dash_title"] += 1
        elif len(show.split()) >= 5:
            patterns["long_romanized"] += 1
        else:
            patterns["other"] += 1

    summary = {
        "releases_parsed": len(all_names),
        "unique_shows": len(show_samples),
        "catalog_entries": len(catalog_index),
        "matched_to_catalog": sum(1 for r in reports if r.matched_anime_id),
        "would_find_count": sum(1 for r in reports if r.would_find_on_nyaa),
        "missed_matched": len(missed),
        "unmatched_shows": len(unmatched),
        "patterns": dict(patterns),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summary,
        "missed": [asdict(r) for r in missed],
        "unmatched": [asdict(r) for r in unmatched],
        "reports": [asdict(r) for r in reports],
    }
    out_path = OUT_DIR / "subsplease_catalog_analysis.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=2, help="Nyaa user pages to fetch")
    args = parser.parse_args()

    payload = analyze(pages=max(1, args.pages))
    summary = payload["summary"]
    print("== SubsPlease vs catalog analysis ==")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    print(f"\nWrote {OUT_DIR / 'subsplease_catalog_analysis.json'}")
    if payload["missed"]:
        print("\nMatched in catalog but planner would miss:")
        for row in payload["missed"][:15]:
            print(f"  - {row['show_title']!r} (anime {row['matched_anime_id']})")
    if payload["unmatched"]:
        print("\nRecent SubsPlease shows not in AIRING catalog index:")
        for row in payload["unmatched"][:10]:
            print(f"  - {row['show_title']!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
