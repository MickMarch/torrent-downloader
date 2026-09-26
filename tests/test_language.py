"""Audio language parsing and the filter policy (no qBittorrent, no network)."""

import pytest

from torrent_downloader.services.language import (
    LANGUAGES_KEY,
    MULTI_AUDIO_KEY,
    LanguageFilter,
    annotate_and_filter,
    is_allowed,
    parse_languages,
)


class TestParseLanguages:
    @pytest.mark.parametrize(
        ("name", "languages", "multi"),
        [
            ("Movie.Name.2021.FRENCH.1080p.WEB.H264-GROUP", ["French"], False),
            ("Movie.Name.2021.MULTi.TRUEFRENCH.1080p.BluRay.x264", ["French"], True),
            ("Movie.Name.2021.ITA.ENG.1080p.BluRay.x264-GRP", ["Italian", "English"], False),
            ("Movie.Name.2021.HINDI.DUBBED.1080p.WEBRip", ["Hindi"], False),
            ("Movie.Name.2021.SPANISH.LATINO.1080p.WEB-DL", ["Spanish"], False),
            ("Movie.Name.2021.GERMAN.DL.1080p.BluRay.x264-GRP", ["German"], False),
            ("Movie.Name.2021.1080p.KOREAN.WEB-DL.H264", ["Korean"], False),
            ("Movie.Name.2021.RUS.ENG.1080p.BluRay", ["Russian", "English"], False),
            (
                "Obsession.2026.2160p.WEB-DL.UNRATED.DV.HDR10+.MULTi.FRE.LAT.Atmos.H265.MP4-BTM",
                ["French"],
                True,
            ),
            ("Movie.Name.2021.1080p.BluRay.x264.DUAL-AUDIO", [], True),
            ("Movie.Name.2021.1080p.BluRay.x264.DUAL", [], True),
            ("Movie Name (2021) [1080p] [WEBRip] [5.1] [YTS.MX]", [], False),
            ("Obsession.2026.1080p.AMZN.WEB-DL.DDP5.1.H264.MP4-BTM", [], False),
        ],
    )
    def test_parses(self, name: str, languages: list[str], multi: bool) -> None:
        assert parse_languages(name) == (languages, multi)

    def test_subtitle_tags_are_not_audio(self) -> None:
        assert parse_languages("Movie.Name.2021.VOSTFR.1080p.WEB.H264-GROUP")[0] == []
        assert parse_languages("Movie.Name.2021.1080p.WEB-DL.ENG.SUBS")[0] == []

    def test_multi_token_must_be_a_whole_word(self) -> None:
        # "Multiverse" is a title word, not a MULTi tag.
        assert parse_languages("Spider-Man.Across.the.Multiverse.2023.1080p.mkv")[1] is False


class TestIsAllowed:
    @pytest.mark.parametrize(
        ("languages", "multi", "policy", "allowed"),
        [
            ([], False, LanguageFilter.LENIENT, True),
            (["French"], False, LanguageFilter.LENIENT, False),
            (["French"], True, LanguageFilter.LENIENT, True),
            (["Italian", "English"], False, LanguageFilter.LENIENT, True),
            (["English"], False, LanguageFilter.LENIENT, True),
            ([], False, LanguageFilter.STRICT, False),
            (["English"], False, LanguageFilter.STRICT, True),
            (["French"], False, LanguageFilter.STRICT, False),
            (["French"], False, LanguageFilter.OFF, True),
            ([], False, LanguageFilter.OFF, True),
        ],
    )
    def test_policy(self, languages, multi, policy, allowed) -> None:
        assert is_allowed(languages, multi, "English", policy) is allowed

    def test_match_is_case_insensitive(self) -> None:
        assert is_allowed(["english"], False, "English", LanguageFilter.STRICT)


class TestAnnotateAndFilter:
    def _results(self) -> list[dict]:
        return [
            {"fileName": "Movie.2021.1080p.WEB-GRP", "nbSeeders": 50},
            {"fileName": "Movie.2021.FRENCH.1080p.WEB-GRP", "nbSeeders": 40},
            {"fileName": "Movie.2021.MULTi.FRENCH.1080p.WEB-GRP", "nbSeeders": 30},
            {"fileName": "Movie.2021.ITA.ENG.1080p.WEB-GRP", "nbSeeders": 20},
        ]

    def test_lenient_drops_only_foreign_single_language(self) -> None:
        kept = annotate_and_filter(self._results(), target_code="en", policy=LanguageFilter.LENIENT)
        assert [r["fileName"] for r in kept] == [
            "Movie.2021.1080p.WEB-GRP",
            "Movie.2021.MULTi.FRENCH.1080p.WEB-GRP",
            "Movie.2021.ITA.ENG.1080p.WEB-GRP",
        ]

    def test_every_result_is_annotated_even_when_dropped(self) -> None:
        results = self._results()
        annotate_and_filter(results, target_code="en", policy=LanguageFilter.LENIENT)
        assert results[1][LANGUAGES_KEY] == ["French"]
        assert results[1][MULTI_AUDIO_KEY] is False
        assert results[2][MULTI_AUDIO_KEY] is True
        assert results[0][LANGUAGES_KEY] == []

    def test_strict_drops_untagged_too(self) -> None:
        kept = annotate_and_filter(self._results(), target_code="en", policy=LanguageFilter.STRICT)
        assert [r["fileName"] for r in kept] == [
            "Movie.2021.MULTi.FRENCH.1080p.WEB-GRP",
            "Movie.2021.ITA.ENG.1080p.WEB-GRP",
        ]

    def test_off_keeps_everything_but_still_annotates(self) -> None:
        results = self._results()
        kept = annotate_and_filter(results, target_code="en", policy=LanguageFilter.OFF)
        assert len(kept) == 4
        assert kept[1][LANGUAGES_KEY] == ["French"]

    def test_unknown_target_code_behaves_as_off(self) -> None:
        kept = annotate_and_filter(self._results(), target_code="xx", policy=LanguageFilter.STRICT)
        assert len(kept) == 4

    def test_french_target_keeps_french_drops_english_tagged(self) -> None:
        kept = annotate_and_filter(self._results(), target_code="fr", policy=LanguageFilter.LENIENT)
        names = [r["fileName"] for r in kept]
        assert "Movie.2021.FRENCH.1080p.WEB-GRP" in names
        assert "Movie.2021.ITA.ENG.1080p.WEB-GRP" not in names
