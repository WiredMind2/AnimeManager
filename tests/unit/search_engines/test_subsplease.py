"""Unit tests for SubsPlease release title parsing."""

from __future__ import annotations

from adapters.search.subsplease import parse_subsplease_release, release_matches_catalog


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
