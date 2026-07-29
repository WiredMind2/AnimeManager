"""Unit tests for SubsPlease JSON search API adapter."""

from __future__ import annotations

import json

from adapters.search.subsplease_api import (
    SubsPleaseSearchAdapter,
    find_subsplease_api_candidate,
    is_useful_search_query,
    parse_search_payload,
)

_SAMPLE = {
    "Rakudai Kenja no Gakuin Musou - 01": {
        "show": "Rakudai Kenja no Gakuin Musou",
        "episode": "01",
        "page": "rakudai-kenja",
        "downloads": [
            {
                "res": "480",
                "magnet": "magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&dn=480&xl=100",
            },
            {
                "res": "720",
                "magnet": "magnet:?xt=urn:btih:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb&dn=720&xl=200",
            },
            {
                "res": "1080",
                "magnet": "magnet:?xt=urn:btih:cccccccccccccccccccccccccccccccc&dn=1080&xl=300",
            },
        ],
    },
    "Rakudai Kenja no Gakuin Musou - 05": {
        "show": "Rakudai Kenja no Gakuin Musou",
        "episode": "05",
        "downloads": [
            {
                "res": "720",
                "magnet": "magnet:?xt=urn:btih:dddddddddddddddddddddddddddddddd&dn=720ep5",
            },
        ],
    },
    "Some Show (01-12)": {
        "show": "Some Show",
        "episode": None,
        "downloads": [
            {
                "res": "720",
                "magnet": "magnet:?xt=urn:btih:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee&dn=batch",
            },
        ],
    },
}


def test_parse_search_payload_keeps_720p_singles_only():
    rows = parse_search_payload(_SAMPLE, resolution="720")
    assert len(rows) == 2
    assert all(r["resolution"] == "720p" for r in rows)
    assert all(r["source"] == "subsplease-api" for r in rows)
    assert {r["episode"] for r in rows} == {1, 5}
    assert rows[0]["magnet"].startswith("magnet:")
    assert rows[0]["infohash"] == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    assert rows[0]["size"] == 200
    assert rows[0]["engine_url"] == "https://subsplease.org/"
    assert rows[0]["desc_link"] == "https://subsplease.org/shows/rakudai-kenja"


def test_parse_search_payload_interactive_all_resolutions_and_batches():
    rows = parse_search_payload(_SAMPLE, resolution=None, include_batches=True)
    # 3 resolutions for ep1 + 1 for ep5 + 1 batch = 5
    assert len(rows) == 5
    assert {r["resolution"] for r in rows} == {"480p", "720p", "1080p"}
    assert any(r["episode"] is None for r in rows)
    assert all(r["name"].startswith("[SubsPlease]") for r in rows)
    assert all(
        "(720p)" in r["name"] or "(480p)" in r["name"] or "(1080p)" in r["name"]
        for r in rows
    )


def test_is_useful_search_query_skips_cjk_and_short_ascii():
    assert is_useful_search_query("Rakudai Kenja no Gakuin Musou")
    assert not is_useful_search_query(
        "落第賢者の学院無双～二度目の転生、Sランクチート魔術師冒険録～"
    )
    assert not is_useful_search_query("S")
    assert not is_useful_search_query("")


def test_find_subsplease_api_candidate_matches_catalog_and_episode():
    rows = parse_search_payload(_SAMPLE, resolution="720")
    terms = [
        "落第賢者の学院無双",
        "Rakudai Kenja no Gakuin Musou: Nidome no Tensei",
    ]
    hit = find_subsplease_api_candidate(rows, search_terms=terms, episode=1)
    assert hit is not None
    assert hit["episode"] == 1
    assert "bbbbbbbb" in hit["infohash"]

    miss = find_subsplease_api_candidate(rows, search_terms=terms, episode=99)
    assert miss is None


def test_adapter_search_paginates_and_filters():
    calls: list[str] = []

    def opener(url: str, timeout_s: float) -> str:
        calls.append(url)
        if "p=0" in url:
            return json.dumps(_SAMPLE)
        return "{}"

    adapter = SubsPleaseSearchAdapter(opener=opener, max_pages=3, resolution="720")
    rows = adapter.search("Rakudai Kenja")
    assert len(rows) == 2
    assert any("p=0" in u for u in calls)
    # Empty second page stops pagination early (no need for p=2).
    assert len(calls) == 2

    match = adapter.search_for_episode(
        ["Rakudai Kenja no Gakuin Musou: Extra"],
        episode=5,
    )
    assert match is not None
    assert match["episode"] == 5


def test_adapter_search_interactive_includes_all_resolutions_and_batches():
    def opener(url: str, timeout_s: float) -> str:
        if "p=0" in url:
            return json.dumps(_SAMPLE)
        return "{}"

    adapter = SubsPleaseSearchAdapter(opener=opener, max_pages=2)
    rows = adapter.search_interactive("Rakudai Kenja")
    assert len(rows) == 5
    assert {r["resolution"] for r in rows} >= {"480p", "720p", "1080p"}


def test_adapter_skips_useless_queries_without_http():
    calls: list[str] = []

    def opener(url: str, timeout_s: float) -> str:
        calls.append(url)
        return "{}"

    adapter = SubsPleaseSearchAdapter(opener=opener)
    assert adapter.search("落第賢者") == []
    assert adapter.search_interactive("落第賢者") == []
    assert calls == []
    assert (
        adapter.search_for_episode(["落第賢者の学院無双～Sランク～"], episode=1) is None
    )
    assert calls == []


def test_search_query_variants_shorten_long_synonyms():
    from adapters.search.subsplease_api import search_query_variants

    variants = search_query_variants(
        "Rakudai Kenja no Gakuin Musou: Nidome no Tensei, S-Rank Cheat Majutsushi Bouken-roku"
    )
    assert variants[0].startswith("Rakudai Kenja no Gakuin Musou:")
    assert "Rakudai Kenja no Gakuin Musou" in variants
    assert any(v == "Rakudai Kenja no Gakuin Musou" for v in variants)


def test_adapter_search_for_episode_uses_short_variant(monkeypatch):
    adapter = SubsPleaseSearchAdapter(
        opener=lambda url, timeout_s: (_ for _ in ()).throw(AssertionError(url)),
        max_pages=1,
    )
    calls: list[str] = []

    def fake_search(query: str):
        calls.append(query)
        if query == "Rakudai Kenja no Gakuin Musou":
            return [
                {
                    "name": "[SubsPlease] Rakudai Kenja no Gakuin Musou - 01 (720p) [API].mkv",
                    "show": "Rakudai Kenja no Gakuin Musou",
                    "episode": 1,
                    "magnet": "magnet:?xt=urn:btih:shortvariant01",
                    "link": "magnet:?xt=urn:btih:shortvariant01",
                    "url": "magnet:?xt=urn:btih:shortvariant01",
                    "infohash": "shortvariant01",
                    "source": "subsplease-api",
                }
            ]
        return []

    adapter.search = fake_search  # type: ignore[method-assign]
    hit = adapter.search_for_episode(
        [
            "Rakudai Kenja no Gakuin Musou: Nidome no Tensei, S-Rank Cheat Majutsushi Bouken-roku"
        ],
        episode=1,
    )
    assert hit is not None
    assert hit["infohash"] == "shortvariant01"
    assert "Rakudai Kenja no Gakuin Musou" in calls
