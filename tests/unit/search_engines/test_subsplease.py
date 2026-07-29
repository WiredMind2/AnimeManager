"""Unit tests for SubsPlease release title parsing."""

from __future__ import annotations

from adapters.feeds.rss_feed_adapter import RssFeedEntry
from adapters.feeds.rss_match import entry_matches_anime
from adapters.search.subsplease import (
    expected_catalog_season,
    extract_title_season,
    parse_subsplease_release,
    release_matches_catalog,
)
from adapters.search.subsplease_api import find_subsplease_api_candidate


def test_parse_weekly_episode():
    parsed = parse_subsplease_release(
        "[SubsPlease] Tenkosaki - 02 (1080p) [7F8ACBE1].mkv"
    )
    assert parsed is not None
    assert parsed.show_title == "Tenkosaki"
    assert parsed.episode == 2


def test_parse_batch_release():
    parsed = parse_subsplease_release(
        "[SubsPlease] Kujima Utaeba Ie Hororo (01-12) (1080p) [Batch]"
    )
    assert parsed is not None
    assert parsed.show_title == "Kujima Utaeba Ie Hororo"
    assert parsed.batch_range == (1, 12)


def test_parse_season_suffix_title():
    parsed = parse_subsplease_release(
        "[SubsPlease] Mushoku Tensei S3 - 03 (1080p) [8488B15C].mkv"
    )
    assert parsed is not None
    assert parsed.show_title == "Mushoku Tensei S3"


def test_release_matches_catalog_colon_synonym():
    catalog = (
        "Tenkosaki: The Neat and Pretty Girl at My New School Is a Childhood "
        "Friend of Mine Who I Thought Was a Boy"
    )
    assert release_matches_catalog("Tenkosaki", catalog)


def test_release_matches_catalog_romanized_overlap():
    catalog = "Suterare Seijo no Isekai Gohan Tabi"
    assert release_matches_catalog("Suterare Seijo no Isekai Gohan Tabi", catalog)


def test_release_matches_catalog_rejects_tiny_folded_keys():
    # Japanese synonyms that fold to a lone ``s`` (from ``S-Rank``) must not
    # match arbitrary SubsPlease titles.
    jp = "落第賢者の学院無双～二度目の転生、Sランクチート魔術師冒険録～"
    assert not release_matches_catalog("Futsutsuka na Akujo dewa Gozaimasu ga", jp)
    assert not release_matches_catalog("Quanzhi Fashi S7", jp)
    assert release_matches_catalog(
        "Rakudai Kenja no Gakuin Musou",
        "Rakudai Kenja no Gakuin Musou: Nidome no Tensei, S-Rank Cheat Majutsushi Bouken-roku",
    )


def test_extract_title_season_variants():
    assert extract_title_season("Youjo Senki II") == 2
    assert extract_title_season("Youjo Senki S2") == 2
    assert extract_title_season("Saga of Tanya the Evil Season 2") == 2
    assert extract_title_season("Classroom of the Elite 4th Season") == 4
    assert extract_title_season("Youjo Senki 2") == 2
    assert extract_title_season("幼女戦記Ⅱ") == 2
    assert extract_title_season("Tenkosaki") is None


def test_expected_catalog_season_defaults_and_max():
    assert expected_catalog_season(["Tenkosaki", "Some Alias"]) == 1
    assert expected_catalog_season(["Youjo Senki II", "Youjo Senki 2"]) == 2
    assert (
        expected_catalog_season(
            ["Saga of Tanya the Evil II", "Saga of Tanya the Evil Season 2"]
        )
        == 2
    )


def test_release_matches_catalog_rejects_wrong_season():
    assert not release_matches_catalog("Youjo Senki", "Youjo Senki II")
    assert not release_matches_catalog(
        "Saga of Tanya the Evil", "Saga of Tanya the Evil II"
    )
    assert release_matches_catalog("Youjo Senki S2", "Youjo Senki II")
    # Different franchise bases should not match even with same season.
    assert not release_matches_catalog(
        "Youjo Senki II", "Saga of Tanya the Evil Season 2"
    )
    assert release_matches_catalog("Youjo Senki S2", "Youjo Senki Season 2")


def test_rss_entry_rejects_season1_for_season2_terms():
    terms = ["Youjo Senki II", "Saga of Tanya the Evil Season 2"]
    s1 = RssFeedEntry(
        feed_id="subsplease-720",
        item_key="s1",
        title="[SubsPlease] Youjo Senki - 04 (720p) [AAAA].mkv",
        link="magnet:?xt=urn:btih:s1",
    )
    s2 = RssFeedEntry(
        feed_id="subsplease-720",
        item_key="s2",
        title="[SubsPlease] Youjo Senki S2 - 04 (720p) [BBBB].mkv",
        link="magnet:?xt=urn:btih:s2",
    )
    assert not entry_matches_anime(s1, search_terms=terms)
    assert entry_matches_anime(s2, search_terms=terms)


def test_api_candidate_rejects_season1_for_season2_terms():
    terms = ["Youjo Senki II", "Youjo Senki 2"]
    rows = [
        {
            "name": "[SubsPlease] Youjo Senki - 01 (720p) [API].mkv",
            "show": "Youjo Senki",
            "episode": 1,
            "magnet": "magnet:?xt=urn:btih:s1ep1",
            "link": "magnet:?xt=urn:btih:s1ep1",
        },
        {
            "name": "[SubsPlease] Youjo Senki S2 - 01 (720p) [API].mkv",
            "show": "Youjo Senki S2",
            "episode": 1,
            "magnet": "magnet:?xt=urn:btih:s2ep1",
            "link": "magnet:?xt=urn:btih:s2ep1",
        },
    ]
    hit = find_subsplease_api_candidate(rows, search_terms=terms, episode=1)
    assert hit is not None
    assert hit["show"] == "Youjo Senki S2"
    assert "s2ep1" in hit["magnet"]
