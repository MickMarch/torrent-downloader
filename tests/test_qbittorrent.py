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

    def test_removes_results_without_magnet_link(self) -> None:
        results = [
            make_result("no_magnet", 50, url="https://example.com/file.torrent"),
            make_result("has_magnet", 50),
        ]
        filtered = filter_and_sort_results(results)
        assert len(filtered) == 1
        assert filtered[0]["fileName"] == "has_magnet"

    def test_sorts_descending_by_seeder_count(self) -> None:
        results = [make_result("c", 15), make_result("a", 100), make_result("b", 40)]
        filtered = filter_and_sort_results(results)
        seed_counts = [r["nbSeeders"] for r in filtered]
        assert seed_counts == sorted(seed_counts, reverse=True)

    def test_returns_empty_list_when_all_filtered(self) -> None:
        results = [make_result("low", 1), make_result("no_magnet", 50, url="http://x.com")]
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

    def test_omits_unknown_resolutions(self) -> None:
        results = [make_result("Movie.480p.DVDRip", 20)]
        grouped = group_by_resolution(results)
        assert grouped == {}

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
