"""Tests for TMDB field extractor functions."""

from torrent_downloader.services.tmdb import extract_media_type, extract_title, extract_year


# ---------------------------------------------------------------------------
# extract_title
# ---------------------------------------------------------------------------

class TestExtractTitle:
    def test_returns_title_for_movie(self) -> None:
        assert extract_title({"title": "Inception"}) == "Inception"

    def test_returns_name_for_tv_show(self) -> None:
        assert extract_title({"name": "Breaking Bad"}) == "Breaking Bad"

    def test_prefers_title_over_name(self) -> None:
        assert extract_title({"title": "Inception", "name": "Something"}) == "Inception"

    def test_falls_back_to_name_when_title_empty(self) -> None:
        assert extract_title({"title": "", "name": "Breaking Bad"}) == "Breaking Bad"

    def test_returns_empty_string_when_both_missing(self) -> None:
        assert extract_title({}) == ""


# ---------------------------------------------------------------------------
# extract_year
# ---------------------------------------------------------------------------

class TestExtractYear:
    def test_extracts_year_from_release_date(self) -> None:
        assert extract_year({"release_date": "2010-07-16"}) == "2010"

    def test_extracts_year_from_first_air_date(self) -> None:
        assert extract_year({"first_air_date": "2008-01-20"}) == "2008"

    def test_prefers_release_date_over_first_air_date(self) -> None:
        assert extract_year({"release_date": "2010-07-16", "first_air_date": "2008-01-20"}) == "2010"

    def test_falls_back_to_first_air_date_when_release_date_empty(self) -> None:
        assert extract_year({"release_date": "", "first_air_date": "2008-01-20"}) == "2008"

    def test_returns_empty_string_when_both_missing(self) -> None:
        assert extract_year({}) == ""

    def test_returns_empty_string_when_both_empty(self) -> None:
        assert extract_year({"release_date": "", "first_air_date": ""}) == ""

    def test_handles_date_with_only_year(self) -> None:
        assert extract_year({"release_date": "2010"}) == "2010"


# ---------------------------------------------------------------------------
# extract_media_type
# ---------------------------------------------------------------------------

class TestExtractMediaType:
    def test_returns_media_type_for_movie(self) -> None:
        assert extract_media_type({"media_type": "movie"}) == "movie"

    def test_returns_media_type_for_tv(self) -> None:
        assert extract_media_type({"media_type": "tv"}) == "tv"

    def test_falls_back_to_name_when_media_type_missing(self) -> None:
        assert extract_media_type({"name": "Breaking Bad"}) == "Breaking Bad"

    def test_falls_back_to_name_when_media_type_empty(self) -> None:
        assert extract_media_type({"media_type": "", "name": "Breaking Bad"}) == "Breaking Bad"

    def test_returns_empty_string_when_both_missing(self) -> None:
        assert extract_media_type({}) == ""
