"""Dry-run: can each WATCHING+autodownload anime resolve the next torrent?"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from application.services.auto_download_matching import next_episode
from application.services.auto_download_prefs import select_feeds_for_anime
from composition.root import build_embedded_facade


def main() -> int:
    facade = build_embedded_facade()
    svc = facade._startup_jobs._auto_download_service
    eligible = svc.list_eligible_anime()
    print(f"eligible_count={len(eligible)}", flush=True)

    # Prefetch RSS once for all RSS-mode anime.
    settings = svc._settings()
    feeds = select_feeds_for_anime(
        settings,
        ["subsplease-720", "subsplease-1080"],
    )
    rss_entries = []
    if svc._feed_fetcher is not None and feeds:
        try:
            rss_entries = list(svc._feed_fetcher.fetch_many(feeds) or [])
            print(f"rss_entries={len(rss_entries)}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"rss_fetch_error={exc}", flush=True)

    rows: list[dict] = []
    for aid in eligible:
        prefs = svc.get_download_preferences(aid)
        pref = svc.resolve_preference(aid)
        owned = svc.owned_episodes(aid)
        ep = next_episode(owned)
        mode = str(prefs.get("source_mode") or "rss").lower()
        title = f"#{aid}"
        try:
            anime = facade.get_anime(aid) or {}
            title = str(anime.get("title") or anime.get("name") or title)
        except Exception:  # noqa: BLE001
            pass

        status = "match"
        source = None
        name = None
        detail = None
        try:
            if pref is None:
                status = "no_preference"
            elif ep is None:
                status = "no_next_episode"
            elif mode == "rss":
                terms = svc._search_terms(aid)
                cand = None
                if svc._rss_match_fn is not None and rss_entries:
                    cand = svc._rss_match_fn(
                        rss_entries,
                        search_terms=terms,
                        preference=pref,
                        episode=ep,
                        parse_title=svc._parse_title,
                        seen_keys=set(),
                    )
                if cand is not None:
                    source = "rss"
                else:
                    cand = svc.find_subsplease_api_candidate(aid, ep)
                    if cand is not None:
                        source = "subsplease-api"
                if cand is None:
                    status = "no_match"
                    detail = f"no match for ep {ep}"
                else:
                    name = str(cand.get("name") or "")
            else:
                cand = svc.find_candidate(aid, pref, ep)
                if cand is None:
                    status = "no_match"
                    detail = f"no match for ep {ep}"
                else:
                    source = "search"
                    name = str(cand.get("name") or "")
        except Exception as exc:  # noqa: BLE001
            status = "error"
            detail = f"{type(exc).__name__}: {exc}"

        row = {
            "id": aid,
            "title": title,
            "mode": mode,
            "owned_tail": sorted(owned)[-8:] if owned else [],
            "next_ep": ep,
            "status": status,
            "source": source,
            "candidate": name,
            "detail": detail,
            "pref": None
            if pref is None
            else {"publisher": pref.publisher, "resolution": pref.resolution},
        }
        rows.append(row)
        print(
            f"{aid}\t{status}\tnext={ep}\tsrc={source}\t{title[:60]}",
            flush=True,
        )
        if name:
            print(f"  -> {name[:100]}", flush=True)

    ok = [r for r in rows if r["status"] == "match"]
    bad = [r for r in rows if r["status"] != "match"]
    print("---", flush=True)
    print(f"match={len(ok)} fail={len(bad)}", flush=True)
    print("FAILS:", flush=True)
    for r in bad:
        print(
            json.dumps(
                {
                    k: r[k]
                    for k in (
                        "id",
                        "title",
                        "mode",
                        "next_ep",
                        "owned_tail",
                        "status",
                        "detail",
                        "pref",
                    )
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    out = Path("test-results/autodownload-eligible-check.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}", flush=True)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
