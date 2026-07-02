"""Tests for scope-aware search: pattern building and season/episode filtering."""

from typing import Any

from medialab_contracts import MediaType, TorrentSearchScope

from torrent_downloader.services.qbittorrent import build_search_pattern, filter_by_scope


def make_result(name: str) -> dict[str, Any]:
    return {"fileName": name, "nbSeeders": 50, "fileUrl": "magnet:?xt=urn:btih:abc"}


class TestBuildSearchPattern:
    def test_movie_pattern_is_query_only(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.MOVIE)
        assert build_search_pattern("Inception", scope) == "Inception"

    def test_whole_series_pattern_is_query_only(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW)
        assert build_search_pattern("The Wire", scope) == "The Wire"

    def test_season_pattern_appends_zero_padded_season_tag(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=2)
        assert build_search_pattern("The Wire", scope) == "The Wire S02"

    def test_episode_pattern_appends_season_and_episode_tag(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=2, episode=5)
        assert build_search_pattern("The Wire", scope) == "The Wire S02E05"

    def test_double_digit_season_and_episode_stay_two_wide(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=12, episode=34)
        assert build_search_pattern("Show", scope) == "Show S12E34"


class TestFilterByScopeNoFiltering:
    def test_movie_scope_returns_input_unchanged(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.MOVIE)
        results = [make_result("Inception.2010.1080p"), make_result("Other.2011.720p")]
        assert filter_by_scope(results, scope) == results

    def test_whole_series_scope_returns_input_unchanged(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW)
        results = [make_result("The.Wire.S01.1080p"), make_result("The.Wire.S05.1080p")]
        assert filter_by_scope(results, scope) == results


class TestFilterByScopeSeason:
    def test_keeps_matching_season_pack(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=2)
        results = [make_result("The.Wire.S02.1080p.BluRay")]
        assert len(filter_by_scope(results, scope)) == 1

    def test_drops_non_matching_season(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=2)
        results = [make_result("The.Wire.S05.1080p")]
        assert filter_by_scope(results, scope) == []

    def test_keeps_episode_within_requested_season(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=2)
        results = [make_result("The.Wire.S02E04.1080p")]
        assert len(filter_by_scope(results, scope)) == 1

    def test_primary_season_match_ranked_before_range_fallback(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=2)
        results = [
            make_result("The.Wire.S01-S05.Complete.1080p"),
            make_result("The.Wire.S02.1080p"),
        ]
        filtered = filter_by_scope(results, scope)
        assert filtered[0]["fileName"] == "The.Wire.S02.1080p"
        assert len(filtered) == 2

    def test_multi_season_range_pack_containing_season_is_fallback(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=2)
        results = [make_result("The.Wire.S01-S03.1080p")]
        assert len(filter_by_scope(results, scope)) == 1

    def test_multi_season_range_pack_not_containing_season_is_dropped(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=2)
        results = [make_result("The.Wire.S03-S05.1080p")]
        assert filter_by_scope(results, scope) == []

    def test_complete_series_pack_is_kept_as_fallback(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=2)
        results = [make_result("The.Wire.Complete.Series.1080p")]
        assert len(filter_by_scope(results, scope)) == 1

    def test_season_result_set_never_empty_when_only_fallbacks_exist(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=2)
        results = [make_result("The.Wire.Complete.Series.1080p")]
        assert filter_by_scope(results, scope) != []


class TestFilterByScopeEpisode:
    def test_keeps_exact_episode_match(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=2, episode=5)
        results = [make_result("The.Wire.S02E05.1080p")]
        assert len(filter_by_scope(results, scope)) == 1

    def test_drops_wrong_episode_same_season(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=2, episode=5)
        results = [make_result("The.Wire.S02E04.1080p")]
        assert filter_by_scope(results, scope) == []

    def test_matching_season_pack_is_fallback_for_episode_request(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=2, episode=5)
        results = [make_result("The.Wire.S02.1080p")]
        assert len(filter_by_scope(results, scope)) == 1

    def test_episode_primary_ranked_before_season_pack_fallback(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=2, episode=5)
        results = [
            make_result("The.Wire.S02.Complete.1080p"),
            make_result("The.Wire.S02E05.1080p"),
        ]
        filtered = filter_by_scope(results, scope)
        assert filtered[0]["fileName"] == "The.Wire.S02E05.1080p"

    def test_wrong_season_episode_dropped(self) -> None:
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=2, episode=5)
        results = [make_result("The.Wire.S03E05.1080p")]
        assert filter_by_scope(results, scope) == []
