"""Service and route tests for TMDB episode groups and a show's numbering."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import diskcache
import pytest
from fastapi.testclient import TestClient
from medialab_contracts import Episode, SeriesEpisodesResponse
from pytest_mock import MockerFixture

from torrent_downloader.services import tmdb
from torrent_downloader.services.tmdb import (
    NUMBERING_AUTO,
    NUMBERING_TMDB,
    UnknownEpisodeGroupError,
    get_episode_groups,
    get_show_numbering,
)

SERIES_ID = 95479
SPLIT_ID = "split"
SINGLE_ID = "single"
SPLIT = (2, 2)
AIRED = date(2026, 1, 1)


def _series() -> SeriesEpisodesResponse:
    return SeriesEpisodesResponse(
        tmdb_id=SERIES_ID,
        seasons=[],
        episodes=[Episode(season=1, episode=n, air_date=AIRED) for n in range(1, 5)],
    )


def _group(split: tuple[int, ...]) -> dict[str, Any]:
    groups, start = [], 1
    for order, size in enumerate(split, start=1):
        groups.append(
            {
                "order": order,
                "episodes": [
                    {"season_number": 1, "episode_number": n, "order": n - start}
                    for n in range(start, start + size)
                ],
            }
        )
        start += size
    return {"groups": groups}


LISTING = {
    "results": [
        {"id": "arcs", "type": 5, "name": "Arcs", "group_count": 2, "episode_count": 4},
        {"id": SINGLE_ID, "type": 6, "name": "One", "group_count": 1, "episode_count": 4},
        {"id": SPLIT_ID, "type": 6, "name": "Seasons", "group_count": 2, "episode_count": 4},
    ]
}


def _fake_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    if path.endswith("episode_groups"):
        return LISTING
    if path.endswith(SPLIT_ID):
        return _group(SPLIT)
    return _group((4,))


@pytest.fixture
def cache(tmp_path: Path, mocker: MockerFixture) -> Iterator[diskcache.Cache]:
    temp_cache = diskcache.Cache(str(tmp_path / "cache"))
    mocker.patch.object(tmdb, "app_cache", temp_cache)
    yield temp_cache
    temp_cache.close()


@pytest.fixture(autouse=True)
def tmdb_reads(mocker: MockerFixture, cache: diskcache.Cache) -> Any:
    mocker.patch.object(tmdb.config, "discover_cache_seconds", 86400)
    mocker.patch.object(tmdb, "get_series_episodes", return_value=_series())
    return mocker.patch.object(tmdb, "_tmdb_get", side_effect=_fake_get)


class TestEpisodeGroups:
    def test_lists_tv_groups_and_the_auto_choice(self) -> None:
        response = get_episode_groups(SERIES_ID)
        assert [g.id for g in response.groups] == [SINGLE_ID, SPLIT_ID]
        assert response.auto_group_id == SPLIT_ID


class TestShowNumbering:
    def test_auto_resolves_to_the_split_group(self) -> None:
        numbering = get_show_numbering(SERIES_ID, NUMBERING_AUTO)
        assert numbering.group_id == SPLIT_ID
        assert numbering.for_canonical(1, 3).release_season == 2  # type: ignore[union-attr]

    def test_tmdb_is_identity(self) -> None:
        assert get_show_numbering(SERIES_ID, NUMBERING_TMDB).group_id is None

    def test_a_named_group(self) -> None:
        assert get_show_numbering(SERIES_ID, SPLIT_ID).group_id == SPLIT_ID

    def test_a_group_that_does_not_qualify_is_identity(self) -> None:
        assert get_show_numbering(SERIES_ID, SINGLE_ID).group_id is None

    def test_an_unlisted_group_is_refused_before_any_tmdb_group_read(self, tmdb_reads: Any) -> None:
        with pytest.raises(UnknownEpisodeGroupError):
            get_show_numbering(SERIES_ID, "../../movie/1")
        paths = [c.args[0] for c in tmdb_reads.call_args_list]
        assert not any("episode_group/" in p for p in paths)

    def test_a_failing_group_is_skipped_by_auto(self, tmdb_reads: Any) -> None:
        def flaky(path: str, params: dict[str, Any]) -> dict[str, Any]:
            if path.endswith(SINGLE_ID):
                raise tmdb.TmdbUnavailableError("boom")
            return _fake_get(path, params)

        tmdb_reads.side_effect = flaky
        assert get_show_numbering(SERIES_ID, NUMBERING_AUTO).group_id == SPLIT_ID

    def test_cached(self, tmdb_reads: Any) -> None:
        get_show_numbering(SERIES_ID, NUMBERING_AUTO)
        calls = tmdb_reads.call_count
        get_show_numbering(SERIES_ID, NUMBERING_AUTO)
        assert tmdb_reads.call_count == calls


class TestRoutes:
    def test_numbering_route(self, client: TestClient) -> None:
        response = client.get(
            f"/api/v1/search/tmdb/show/{SERIES_ID}/numbering", params={"group": "auto"}
        )
        assert response.status_code == 200
        assert response.json()["group_id"] == SPLIT_ID

    def test_unknown_group_is_422(self, client: TestClient) -> None:
        response = client.get(
            f"/api/v1/search/tmdb/show/{SERIES_ID}/numbering", params={"group": "nope"}
        )
        assert response.status_code == 422
        assert response.json()["code"] == "INVALID_INPUT"

    def test_episode_groups_route(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/search/tmdb/show/{SERIES_ID}/episode-groups")
        assert response.status_code == 200
        assert response.json()["auto_group_id"] == SPLIT_ID
