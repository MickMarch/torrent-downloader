"""Unit tests for the automatic pick rule over grouped search results."""

from torrent_downloader.schemas.torrents import TorrentResult
from torrent_downloader.services.qbittorrent import (
    PICK_RESOLUTION_ORDER,
    RES_GROUP_4K,
    RES_GROUP_720,
    RES_GROUP_1080,
    RES_GROUP_OTHER,
    pick_best,
)

SEASON = 2
EPISODE = 5
NO_FLOOR = 0


def _result(name: str, seeders: int = 50, size: int = 1_000_000_000) -> TorrentResult:
    return TorrentResult(
        fileName=name,
        fileUrl=f"magnet:?xt=urn:btih:{abs(hash((name, seeders, size))):x}",
        nbSeeders=seeders,
        nbLeechers=1,
        siteUrl="https://example.com",
        descrLink="https://example.com/desc",
        fileSize=size,
    )


def _pick(
    grouped: dict[str, list[TorrentResult]],
    resolution: str = RES_GROUP_1080,
    min_seeders: int = NO_FLOOR,
) -> TorrentResult | None:
    return pick_best(
        grouped,
        season=SEASON,
        episode=EPISODE,
        resolution=resolution,
        min_seeders=min_seeders,
    )


class TestBucketOrder:
    def test_order_is_highest_to_lowest_without_other(self) -> None:
        assert PICK_RESOLUTION_ORDER == (RES_GROUP_4K, RES_GROUP_1080, RES_GROUP_720)
        assert RES_GROUP_OTHER not in PICK_RESOLUTION_ORDER


class TestEpisodeScope:
    def test_season_pack_is_never_picked(self) -> None:
        grouped = {RES_GROUP_1080: [_result("The.Wire.S02.1080p.BluRay", seeders=900)]}
        assert _pick(grouped) is None

    def test_complete_series_pack_is_never_picked(self) -> None:
        grouped = {RES_GROUP_1080: [_result("The.Wire.Complete.Series.1080p", seeders=900)]}
        assert _pick(grouped) is None

    def test_other_episode_in_same_season_is_never_picked(self) -> None:
        grouped = {RES_GROUP_1080: [_result("The.Wire.S02E04.1080p.WEB", seeders=900)]}
        assert _pick(grouped) is None

    def test_same_episode_number_in_another_season_is_never_picked(self) -> None:
        grouped = {RES_GROUP_1080: [_result("The.Wire.S03E05.1080p.WEB", seeders=900)]}
        assert _pick(grouped) is None

    def test_exact_episode_beats_a_better_seeded_pack(self) -> None:
        exact = _result("The.Wire.S02E05.1080p.WEB", seeders=20)
        grouped = {RES_GROUP_1080: [_result("The.Wire.S02.1080p.BluRay", seeders=900), exact]}
        assert _pick(grouped) == exact


class TestSeederFloor:
    def test_below_floor_is_dropped(self) -> None:
        grouped = {RES_GROUP_1080: [_result("The.Wire.S02E05.1080p.WEB", seeders=49)]}
        assert _pick(grouped, min_seeders=50) is None

    def test_at_floor_is_kept(self) -> None:
        exact = _result("The.Wire.S02E05.1080p.WEB", seeders=50)
        assert _pick({RES_GROUP_1080: [exact]}, min_seeders=50) == exact

    def test_floor_applies_to_the_fallback_bucket_too(self) -> None:
        grouped = {RES_GROUP_720: [_result("The.Wire.S02E05.720p.WEB", seeders=10)]}
        assert _pick(grouped, resolution=RES_GROUP_1080, min_seeders=50) is None


class TestResolutionBucket:
    def test_exact_bucket_wins_over_a_better_seeded_lower_bucket(self) -> None:
        exact = _result("The.Wire.S02E05.1080p.WEB", seeders=10)
        grouped = {
            RES_GROUP_1080: [exact],
            RES_GROUP_720: [_result("The.Wire.S02E05.720p.WEB", seeders=500)],
        }
        assert _pick(grouped, resolution=RES_GROUP_1080) == exact

    def test_higher_bucket_is_never_picked(self) -> None:
        grouped = {RES_GROUP_4K: [_result("The.Wire.S02E05.2160p.WEB", seeders=500)]}
        assert _pick(grouped, resolution=RES_GROUP_1080) is None

    def test_falls_back_one_bucket_lower_when_exact_is_empty(self) -> None:
        lower = _result("The.Wire.S02E05.720p.WEB", seeders=30)
        assert _pick({RES_GROUP_720: [lower]}, resolution=RES_GROUP_1080) == lower

    def test_falls_back_two_buckets_when_both_above_are_empty(self) -> None:
        lower = _result("The.Wire.S02E05.720p.WEB", seeders=30)
        assert _pick({RES_GROUP_720: [lower]}, resolution=RES_GROUP_4K) == lower

    def test_falls_back_when_exact_bucket_has_only_packs(self) -> None:
        lower = _result("The.Wire.S02E05.720p.WEB", seeders=30)
        grouped = {
            RES_GROUP_1080: [_result("The.Wire.S02.1080p.BluRay", seeders=900)],
            RES_GROUP_720: [lower],
        }
        assert _pick(grouped, resolution=RES_GROUP_1080) == lower

    def test_never_falls_back_to_other(self) -> None:
        grouped = {RES_GROUP_OTHER: [_result("The.Wire.S02E05.HDTV.x264", seeders=900)]}
        assert _pick(grouped, resolution=RES_GROUP_720) is None


class TestTieBreak:
    def test_highest_seeders_wins(self) -> None:
        best = _result("The.Wire.S02E05.1080p.WEB-B", seeders=80)
        grouped = {
            RES_GROUP_1080: [
                _result("The.Wire.S02E05.1080p.WEB-A", seeders=40),
                best,
                _result("The.Wire.S02E05.1080p.WEB-C", seeders=60),
            ]
        }
        assert _pick(grouped) == best

    def test_equal_seeders_prefers_the_larger_file(self) -> None:
        larger = _result("The.Wire.S02E05.1080p.WEB-B", seeders=80, size=4_000_000_000)
        grouped = {
            RES_GROUP_1080: [
                _result("The.Wire.S02E05.1080p.WEB-A", seeders=80, size=2_000_000_000),
                larger,
            ]
        }
        assert _pick(grouped) == larger


class TestNothing:
    def test_empty_grouping_is_none(self) -> None:
        assert _pick({}) is None

    def test_grouping_is_not_mutated(self) -> None:
        results = [
            _result("The.Wire.S02E05.1080p.WEB-A", seeders=40),
            _result("The.Wire.S02E05.1080p.WEB-B", seeders=80),
        ]
        grouped = {RES_GROUP_1080: list(results)}
        _pick(grouped)
        assert grouped[RES_GROUP_1080] == results
