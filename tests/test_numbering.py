"""Unit tests for episode numbering: group parsing, the map, auto selection,
and the absolute episode number read from fansub release names."""

from datetime import date
from typing import Any

import pytest
from medialab_contracts import Episode

from torrent_downloader.services.numbering import (
    GroupSeason,
    build_numbering,
    identity_numbering,
    parse_absolute_episode,
    parse_group_seasons,
    select_auto,
)

TMDB_ID = 95479
TODAY = date(2026, 11, 5)
AIRED = date(2026, 1, 1)
FUTURE = date(2027, 1, 1)
SPLIT = (24, 23, 12)
TOTAL = sum(SPLIT)


def _canonical(count: int = TOTAL, future_tail: int = 0) -> list[Episode]:
    return [
        Episode(season=1, episode=n, air_date=FUTURE if n > count - future_tail else AIRED)
        for n in range(1, count + 1)
    ]


def _split_groups(split: tuple[int, ...] = SPLIT, specials: int = 0) -> list[GroupSeason]:
    seasons: list[GroupSeason] = []
    start = 1
    for order, size in enumerate(split, start=1):
        seasons.append(
            GroupSeason(order=order, episodes=[(1, n) for n in range(start, start + size)])
        )
        start += size
    if specials:
        seasons.append(GroupSeason(order=0, episodes=[(0, n) for n in range(1, specials + 1)]))
    return seasons


def _raw_group(seasons: list[GroupSeason]) -> dict[str, Any]:
    return {
        "groups": [
            {
                "order": s.order,
                "episodes": [
                    {"season_number": se, "episode_number": ep, "order": i}
                    for i, (se, ep) in reversed(list(enumerate(s.episodes)))
                ],
            }
            for s in reversed(seasons)
        ]
    }


class TestParseGroupSeasons:
    def test_orders_groups_and_episodes(self) -> None:
        parsed = parse_group_seasons(_raw_group(_split_groups(specials=2)))
        assert [s.order for s in parsed] == [0, 1, 2, 3]
        assert parsed[1].episodes[:2] == [(1, 1), (1, 2)]


class TestBuildNumbering:
    def test_jujutsu_kaisen_split(self) -> None:
        numbering = build_numbering(
            TMDB_ID,
            _canonical(),
            _split_groups(specials=5),
            today=TODAY,
            group_id="g",
            group_name="Seasons",
        )
        assert numbering is not None
        first_s3 = numbering.for_canonical(1, 48)
        assert first_s3 is not None
        assert (first_s3.release_season, first_s3.release_episode, first_s3.absolute) == (3, 1, 48)
        assert numbering.for_release(2, 1).episode == 25  # type: ignore[union-attr]
        assert len(numbering.episodes) == TOTAL

    def test_duplicate_episode_disqualifies(self) -> None:
        groups = _split_groups()
        groups[1].episodes.append((1, 1))
        assert build_numbering(TMDB_ID, _canonical(), groups, today=TODAY, group_id="g") is None

    def test_missing_aired_episode_disqualifies(self) -> None:
        groups = _split_groups()
        groups[2].episodes.pop(0)
        assert build_numbering(TMDB_ID, _canonical(), groups, today=TODAY, group_id="g") is None

    def test_specials_in_a_regular_group_disqualify(self) -> None:
        groups = _split_groups()
        groups[0].episodes.append((0, 1))
        assert build_numbering(TMDB_ID, _canonical(), groups, today=TODAY, group_id="g") is None

    def test_unaired_tail_continues_the_last_release_season(self) -> None:
        canonical = _canonical(TOTAL + 2, future_tail=2)
        numbering = build_numbering(TMDB_ID, canonical, _split_groups(), today=TODAY, group_id="g")
        assert numbering is not None
        tail = numbering.for_canonical(1, TOTAL + 2)
        assert tail is not None
        assert (tail.release_season, tail.release_episode, tail.absolute) == (3, 14, TOTAL + 2)


class TestIdentity:
    def test_release_equals_canonical_and_absolute_counts_across_seasons(self) -> None:
        canonical = [
            Episode(season=1, episode=1),
            Episode(season=1, episode=2),
            Episode(season=2, episode=1),
        ]
        numbering = identity_numbering(TMDB_ID, canonical)
        assert numbering.group_id is None
        assert [(e.release_season, e.release_episode, e.absolute) for e in numbering.episodes] == [
            (1, 1, 1),
            (1, 2, 2),
            (2, 1, 3),
        ]


class TestSelectAuto:
    def test_first_qualifying_group_wins(self) -> None:
        single = [GroupSeason(order=1, episodes=[(1, n) for n in range(1, TOTAL + 1)])]
        candidates = [
            ("single", "One", single),
            ("split", "Seasons", _split_groups()),
            ("other", "B", _split_groups()),
        ]
        numbering = select_auto(TMDB_ID, _canonical(), candidates, today=TODAY)
        assert numbering.group_id == "split"

    def test_same_split_as_tmdb_falls_back_to_identity(self) -> None:
        canonical = [Episode(season=s, episode=e, air_date=AIRED) for s in (1, 2) for e in (1, 2)]
        same = [GroupSeason(order=s, episodes=[(s, 1), (s, 2)]) for s in (1, 2)]
        numbering = select_auto(TMDB_ID, canonical, [("same", "Seasons", same)], today=TODAY)
        assert numbering.group_id is None

    def test_no_candidates_is_identity(self) -> None:
        assert select_auto(TMDB_ID, _canonical(), [], today=TODAY).group_id is None


class TestParseAbsoluteEpisode:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("[SubsPlease] Jujutsu Kaisen - 58 (1080p) [3D64E486].mkv", 58),
            ("[SubsPlease] Jujutsu Kaisen - 05 (720p) [8BC8D419].mkv", 5),
            ("[Group] One Piece - 1100v2 [1080p]", 1100),
            ("[ToonsHub] Jujutsu Kaisen S03E06 1080p NF WEB-DL", None),
            ("[SubsPlease] Jujutsu Kaisen - SP1 (720p) [67B93912] mkv", None),
            ("Jujutsu Kaisen S01 1080p Dual Audio WEBRip AAC x265-EMBER", None),
            ("Spider-Man - Across the Spider-Verse 2023 1080p", None),
        ],
    )
    def test_fansub_names(self, name: str, expected: int | None) -> None:
        assert parse_absolute_episode(name) == expected
