"""Tests for qBittorrent pure logic: filtering, sorting, and resolution grouping."""

from typing import Any

from torrent_downloader.services.qbittorrent import filter_and_sort_results, group_by_resolution

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_result(name: str, seeders: int, url: str = "magnet:?xt=urn:btih:abc") -> dict[str, Any]:
    return {"fileName": name, "nbSeeders": seeders, "fileUrl": url}


# ---------------------------------------------------------------------------
# filter_and_sort_results
# ---------------------------------------------------------------------------


class TestFilterAndSortResults:
    def test_removes_results_below_minimum_seeders(self) -> None:
        results = [make_result("low", 1), make_result("ok", 50)]
        filtered = filter_and_sort_results(results)
        assert all(r["nbSeeders"] >= 10 for r in filtered)

    def test_keeps_magnet_torrent_file_and_html_page_urls(self) -> None:
        # Every torrent-source URL a plugin returns is addable: magnets and
        # .torrent files add directly; HTML details pages get their magnet
        # scraped at download time.
        results = [
            make_result("torrent_file", 50, url="https://www.torlock.com/tor/123.torrent"),
            make_result("details_page", 50, url="https://www.limetorrents.lol/x-torrent-1.html"),
            make_result("has_magnet", 50),
        ]
        filtered = filter_and_sort_results(results)
        names = {r["fileName"] for r in filtered}
        assert names == {"torrent_file", "details_page", "has_magnet"}

    def test_sorts_descending_by_seeder_count(self) -> None:
        results = [make_result("c", 15), make_result("a", 100), make_result("b", 40)]
        filtered = filter_and_sort_results(results)
        seed_counts = [r["nbSeeders"] for r in filtered]
        assert seed_counts == sorted(seed_counts, reverse=True)

    def test_returns_empty_list_when_all_filtered(self) -> None:
        # low seeders + an unaddable source (neither magnet nor http) -> both dropped.
        results = [make_result("low", 1), make_result("bogus", 50, url="ftp://x.com/a")]
        assert filter_and_sort_results(results) == []

    def test_returns_empty_list_for_empty_input(self) -> None:
        assert filter_and_sort_results([]) == []

    def test_result_at_minimum_seeders_threshold_is_kept(self) -> None:
        results = [make_result("exactly_min", 10)]
        filtered = filter_and_sort_results(results)
        assert len(filtered) == 1

    def test_result_one_below_threshold_is_removed(self) -> None:
        results = [make_result("just_below", 9)]
        assert filter_and_sort_results(results) == []


# ---------------------------------------------------------------------------
# group_by_resolution
# ---------------------------------------------------------------------------


class TestGroupByResolution:
    def test_groups_4k_resolutions(self) -> None:
        results = [
            make_result("Movie.2160p.BluRay", 50),
            make_result("Movie.4K.WEB-DL", 40),
        ]
        grouped = group_by_resolution(results)
        assert len(grouped.get("4K", [])) == 2

    def test_groups_1080p_resolution(self) -> None:
        results = [make_result("Movie.1080p.BluRay", 50)]
        grouped = group_by_resolution(results)
        assert len(grouped.get("1080p", [])) == 1

    def test_groups_720p_resolution(self) -> None:
        results = [make_result("Movie.720p.WEB-DL", 30)]
        grouped = group_by_resolution(results)
        assert len(grouped.get("720p", [])) == 1

    def test_buckets_unknown_resolution_into_other(self) -> None:
        # Untagged / SD releases (common for older TV) must not be dropped -
        # they belong in the Other bucket so they still reach the picker.
        results = [make_result("Movie.480p.DVDRip", 20)]
        grouped = group_by_resolution(results)
        assert len(grouped.get("Other", [])) == 1

    def test_buckets_no_resolution_token_into_other(self) -> None:
        results = [make_result("The Simpsons Season 23 Episode 22 HDTV", 24)]
        grouped = group_by_resolution(results)
        assert len(grouped.get("Other", [])) == 1

    def test_omits_empty_resolution_buckets(self) -> None:
        results = [make_result("Movie.1080p.BluRay", 50)]
        grouped = group_by_resolution(results)
        assert "4K" not in grouped
        assert "720p" not in grouped

    def test_returns_empty_dict_for_empty_input(self) -> None:
        assert group_by_resolution([]) == {}

    def test_mixed_resolutions_bucketed_correctly(self) -> None:
        results = [
            make_result("Movie.2160p.BluRay", 100),
            make_result("Movie.1080p.WEB-DL", 80),
            make_result("Movie.720p.HDTV", 30),
            make_result("Movie.480p.DVDRip", 10),
        ]
        grouped = group_by_resolution(results)
        assert len(grouped["4K"]) == 1
        assert len(grouped["1080p"]) == 1
        assert len(grouped["720p"]) == 1
        assert "480p" not in grouped
        assert len(grouped["Other"]) == 1


class TestScopedSearchUnion:
    def test_season_scope_runs_both_patterns_and_dedupes(self, mocker) -> None:
        from medialab_contracts import MediaType, TorrentSearchScope

        from torrent_downloader.services import qbittorrent as qb

        mocker.patch.object(qb.app_cache, "get", return_value=None)
        mocker.patch.object(qb.app_cache, "set")
        by_pattern = {
            "Show S06": [{"fileName": "Show.S06.1080p", "fileUrl": "magnet:?a"}],
            "Show": [
                {"fileName": "Show.S06.1080p", "fileUrl": "magnet:?a"},
                {"fileName": "Show.Season.6.Complete", "fileUrl": "magnet:?b"},
            ],
        }
        run = mocker.patch.object(
            qb, "execute_plugin_search", side_effect=lambda _c, p, _cat: by_pattern[p]
        )
        scope = TorrentSearchScope(media_type=MediaType.SHOW, season=6)
        results = qb.search_torrents(mocker.MagicMock(), "Show", scope)
        assert [c.args[1] for c in run.call_args_list] == ["Show S06", "Show"]
        assert [r["fileUrl"] for r in results] == ["magnet:?a", "magnet:?b"]
