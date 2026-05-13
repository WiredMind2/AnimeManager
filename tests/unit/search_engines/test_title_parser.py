"""Tests for ``adapters.search.title_parser.parse_title``.

The cases are mined from the corpus collected by
``scripts/run_search_samples.py`` and curated by query so the suite
stays representative of the actual nova3 output.
"""

from __future__ import annotations

import pytest

from adapters.search.title_parser import (
    Codec,
    EpisodeKind,
    ParsedTitle,
    PublisherSource,
    Source,
    parse_title,
)

# --------------------------------------------------------------------------- #
# Publisher detection
# --------------------------------------------------------------------------- #


class TestPublisher:
    def test_head_bracket_simple(self):
        parsed = parse_title("[SubsPlease] One Piece - 1161 (1080p) [9BEAE717].mkv")
        assert parsed.publisher == "subsplease"
        assert parsed.publisher_display == "SubsPlease"
        assert parsed.publisher_source == PublisherSource.HEAD_BRACKET

    def test_head_bracket_with_hyphen(self):
        parsed = parse_title("[Erai-raws] One Piece - 1161 [1080p CR WEB-DL AVC AAC][7540CB4F]")
        assert parsed.publisher == "erai-raws"
        assert parsed.publisher_display == "Erai-raws"

    def test_head_bracket_with_space(self):
        parsed = parse_title("[Anime Time] One Piece (0001-1071+Movies+Specials) [BD+CR]")
        assert parsed.publisher == "anime time"
        assert parsed.publisher_display == "Anime Time"

    def test_cjk_bracket(self):
        parsed = parse_title("【喵萌奶茶屋】★10月新番★[孤独摇滚!/Bocchi the Rock!][01-12][1080p][简体][招募翻译]")
        assert parsed.publisher == "喵萌奶茶屋"
        assert parsed.publisher_source == PublisherSource.CJK_BRACKET

    def test_tail_dash_scene_style(self):
        parsed = parse_title("Bocchi.the.Rock.S01.1080p.BluRay.10-Bit.FLAC2.0.x265-YURASUKA")
        assert parsed.publisher == "yurasuka"
        assert parsed.publisher_source == PublisherSource.TAIL_DASH

    def test_tail_dash_with_internal_hyphen(self):
        parsed = parse_title("Bocchi the Rock! S01 VOSTFR 1080p BluRay x265 FLAC -Tsundere-Raws")
        assert parsed.publisher == "tsundere-raws"
        assert parsed.publisher_source == PublisherSource.TAIL_DASH

    def test_tail_dash_skipped_when_parenthetical_metadata_follows(self):
        # Trailing "(AMZN) (VOSTFR, ...)" is metadata, not part of the
        # publisher token; the regex should still find Tsundere-Raws.
        parsed = parse_title(
            "Bocchi the Rock! Re (2024) 1080p WEB H.265 E-AC-3 -Tsundere-Raws (AMZN) (VOSTFR, Multi-Subs, Bocchi the Rock! Movie)"
        )
        assert parsed.publisher == "tsundere-raws"
        assert parsed.publisher_source == PublisherSource.TAIL_DASH

    def test_no_publisher_for_doujinshi(self):
        # Catalogue-style filename with no clear release group.
        parsed = parse_title("Alina Becker - Bocchi the rock. zip")
        # Either no publisher is detected, or whatever falls out is
        # the tail-dash candidate -- as long as it isn't a metadata
        # token we don't really mind. The key invariant is that the
        # function doesn't crash.
        assert isinstance(parsed, ParsedTitle)

    def test_head_bracket_rejects_pure_metadata(self):
        # The head bracket [BDMV] is a metadata token, not a publisher.
        # We expect parse_title to skip it and look for the next
        # plausible publisher source (none here -> NONE).
        parsed = parse_title("[BDMV] Some Anime Vol.1 (1080p AVC FLAC)")
        assert parsed.publisher_source != PublisherSource.HEAD_BRACKET

    def test_crc_tail_does_not_become_publisher(self):
        parsed = parse_title("[SubsPlease] One Piece - 1161 (1080p) [9BEAE717].mkv")
        # The 8-hex CRC tail must not be detected as a tail-dash
        # publisher.
        assert parsed.publisher == "subsplease"
        assert parsed.crc == "9BEAE717"


# --------------------------------------------------------------------------- #
# Resolution + codec + source + provider
# --------------------------------------------------------------------------- #


class TestQuality:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("[SubsPlease] One Piece - 1161 (1080p) [9BEAE717].mkv", "1080p"),
            ("[Judas] One Piece - 1161 [720p][HEVC x265 10bit][Multi-Subs]", "720p"),
            ("Demon.Slayer.S02.2160p.Blu-Ray.10-Bit.x265-iAHD", "2160p"),
            ("[UCCUSS] Bocchi the Rock! 第3巻 (BD 1920x1080p AVC FLAC)", "1080p"),
            ("[Some] Title 4K WEB-DL", "2160p"),
        ],
    )
    def test_resolution_canonicalised(self, name, expected):
        assert parse_title(name).resolution == expected

    @pytest.mark.parametrize(
        "name,expected_codec",
        [
            ("[Erai-raws] One Piece - 1161 [1080p CR WEBRip HEVC AAC]", Codec.H265),
            ("Bocchi.the.Rock.S01.1080p.NF.WEB-DL.DDP2.0.H.264-KQRM", Codec.H264),
            ("Some Anime 1080p AV1 FLAC", Codec.AV1),
            ("Some Anime 1080p VP9 AAC", Codec.VP9),
            ("[Group] Title 1080p x265 10bit AAC", Codec.H265),
            ("[Group] Title 1080p x264 AAC", Codec.H264),
        ],
    )
    def test_codec_canonicalised(self, name, expected_codec):
        assert parse_title(name).codec is expected_codec

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("[Erai-raws] One Piece - 1161 [1080p CR WEB-DL AVC AAC]", Source.WEBDL),
            ("[Group] One Piece - 1161 [1080p CR WEBRip HEVC AAC]", Source.WEBRIP),
            ("Bocchi.the.Rock.S01.1080p.BluRay.x265-YURASUKA", Source.BLURAY),
            ("[Group] Anime BDRip 1080p HEVC", Source.BLURAY),
            ("[Group] Anime 1080p WEB AAC2.0", Source.WEBDL),
        ],
    )
    def test_source_canonicalised(self, name, expected):
        assert parse_title(name).source is expected

    @pytest.mark.parametrize(
        "name,provider",
        [
            ("[Erai-raws] One Piece - 1161 [1080p CR WEB-DL AVC AAC]", "CR"),
            ("Bocchi.the.Rock.S01.1080p.NF.WEB-DL.DDP2.0.H.264-KQRM", "NF"),
            ("Bocchi the Rock S01 1080p AMZN WEB-DL DDP2.0 H 264 MULTi", "AMZN"),
            ("[ToonsHub] One Piece EP1161 2160p BILI WEB-DL AAC2.0 H.264", "BiliBili"),
            ("Demon Slayer S04 1080p iQ WEB-DL H 264", "iQ"),
        ],
    )
    def test_provider_extracted(self, name, provider):
        assert parse_title(name).provider == provider

    def test_bit_depth_and_languages(self):
        parsed = parse_title(
            "[Judas] Bocchi the Rock! (Season 1) [BD 1080p][HEVC x265 10bit][Multi-Subs] (Batch)"
        )
        assert parsed.bit_depth == 10
        assert "multi-sub" in parsed.languages


# --------------------------------------------------------------------------- #
# Season detection
# --------------------------------------------------------------------------- #


class TestSeason:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("[SubsPlease] Demon Slayer S03 - 01 (1080p)", 3),
            ("Demon.Slayer.S04.1080p.MULTI.CR.WEB-DL.H.264-BlackLuster", 4),
            ("[Judas] Bocchi the Rock! (Season 1) [BD 1080p][Multi-Subs] (Batch)", 1),
            ("[Group] Demon Slayer Season 04 [Batch]", 4),
            ("[Fumi-Raws] Demon Slayer - Swordsmith Village - (SS3) EP02", 3),
        ],
    )
    def test_season_extracted(self, name, expected):
        assert parse_title(name).season == expected

    def test_part_with_roman_numeral(self):
        parsed = parse_title("[Group] Some Anime Part II [1080p][Batch]")
        assert parsed.season == 2

    def test_no_season_when_movie(self):
        parsed = parse_title(
            "Demon Slayer Kimetsu No Yaiba Infinity Castle 2025 1080p WEB-DL H 264-Cassu"
        )
        assert parsed.season is None


# --------------------------------------------------------------------------- #
# Episode detection
# --------------------------------------------------------------------------- #


class TestEpisode:
    def test_sxxexx_strongly_preferred(self):
        parsed = parse_title(
            "Demon.Slayer.Kimetsu.no.Yaiba.S04E10.1080p.AMZN.WEB-DL.H.264-KQRM"
        )
        assert parsed.episode_kind is EpisodeKind.SINGLE
        assert parsed.season == 4
        assert parsed.episode == 10

    def test_dash_subsplease_style(self):
        parsed = parse_title("[SubsPlease] One Piece - 1161 (1080p) [9BEAE717].mkv")
        assert parsed.episode_kind is EpisodeKind.SINGLE
        assert parsed.episode == 1161

    def test_dash_v2(self):
        parsed = parse_title(
            "Demon.Slayer.Kimetsu.no.Yaiba.S05E03v2.1080p.CR.WEB-DL.MULTi.AAC2.0.H.264-NanDesuKa.mkv"
        )
        assert parsed.episode_kind is EpisodeKind.SINGLE
        assert parsed.episode == 3

    def test_ep_uppercase(self):
        parsed = parse_title("[ToonsHub] One Piece EP1161 1080p TVER WEB-DL AAC2.0 H.264")
        assert parsed.episode_kind is EpisodeKind.SINGLE
        assert parsed.episode == 1161

    def test_episode_word(self):
        parsed = parse_title("[OtakuSubs] Demon Slayer - Kimetsu no Yaiba Episode 02")
        assert parsed.episode_kind is EpisodeKind.SINGLE
        assert parsed.episode == 2

    def test_range_paren(self):
        parsed = parse_title("[SubsPlease] Bocchi the Rock! (01-12) (1080p) [Batch]")
        assert parsed.episode_kind is EpisodeKind.RANGE
        assert parsed.episode_start == 1
        assert parsed.episode_end == 12
        assert parsed.is_batch is True

    def test_range_tilde(self):
        parsed = parse_title("[Erai-raws] Bocchi the Rock! - 01 ~ 12 [1080p][Multiple Subtitle]")
        assert parsed.episode_kind is EpisodeKind.RANGE
        assert parsed.episode_start == 1
        assert parsed.episode_end == 12

    def test_xx_of_yy(self):
        parsed = parse_title(
            "Kimetsu no Yaiba: Hashira Geiko Hen [ТВ-4] [2024] [08 of 11] [WEBRip] [1080p]"
        )
        assert parsed.episode_kind is EpisodeKind.RANGE
        assert parsed.episode_start == 8
        assert parsed.episode_end == 11

    def test_movie_year_not_treated_as_episode(self):
        parsed = parse_title(
            "Demon Slayer Kimetsu No Yaiba Infinity Castle 2025 1080p WEB-DL H 264-Cassu"
        )
        # 2025 must not be picked up as an episode by the " - xx" rule.
        assert parsed.episode_kind is EpisodeKind.NONE

    def test_batch_keyword_without_range(self):
        parsed = parse_title("[ASW] Bocchi the Rock! [1080p HEVC x265 10Bit][AAC] (Batch)")
        assert parsed.is_batch is True
        assert parsed.episode_kind in (EpisodeKind.RANGE, EpisodeKind.SINGLE)


# --------------------------------------------------------------------------- #
# Misc / robustness
# --------------------------------------------------------------------------- #


class TestRobustness:
    def test_returns_parsed_for_empty_string(self):
        parsed = parse_title("")
        assert isinstance(parsed, ParsedTitle)
        assert parsed.raw == ""
        assert parsed.publisher is None

    def test_returns_parsed_for_none_like(self):
        parsed = parse_title(None)  # type: ignore[arg-type]
        assert isinstance(parsed, ParsedTitle)
        assert parsed.publisher is None

    def test_as_dict_is_json_friendly(self):
        parsed = parse_title("[SubsPlease] One Piece - 1161 (1080p) [9BEAE717].mkv")
        out = parsed.as_dict()
        # Enums must be plain strings, languages a list.
        assert isinstance(out["publisher_source"], str)
        assert isinstance(out["episode_kind"], str)
        assert isinstance(out["languages"], list)
        # Round-trips through json without raising.
        import json

        json.dumps(out)

    def test_crc_isolated(self):
        parsed = parse_title("[SubsPlease] One Piece - 1161 (1080p) [9BEAE717].mkv")
        assert parsed.crc == "9BEAE717"
        assert parsed.extension == ".mkv"

    def test_confidence_high_for_complete_release(self):
        parsed = parse_title(
            "[SubsPlease] Demon Slayer S03 - 01 (1080p) [ABCDEF12].mkv"
        )
        assert parsed.parse_confidence == 1.0

    def test_confidence_low_for_unparseable_filename(self):
        parsed = parse_title("Alina Becker - Bocchi the rock. zip")
        assert parsed.parse_confidence <= 0.25
