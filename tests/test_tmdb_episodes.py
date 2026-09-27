"""Service tests for the TMDB series episode listing."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import diskcache
import pytest
import requests
from fastapi.testclient import TestClient
from medialab_contracts import SeriesEpisodesResponse
from pytest_mock import MockerFixture

from torrent_downloader.services import tmdb
from torrent_downloader.services.tmdb import (
    TMDB_APPEND_MAX_SEASONS,
    TmdbUnavailableError,
    get_series_episodes,
)

SERIES_ID = 1396
# Season N of the fixture show airs in FIRST_YEAR + N - 1.
FIRST_YEAR = 2008
SPECIALS_SEASON = 0
BEYOND_APPEND_LIMIT = TMDB_APPEND_MAX_SEASONS + 1
# The series summary is always fetched first; season fetches come after it.
SUMMARY_CALL = 1
# A show within the append limit costs the summary plus one appended call.
SMALL_SHOW_CALLS = SUMMARY_CALL + 1


def _episode(season: int, episode: int, **overrides: Any) -> dict[str, Any]:
    return {
        "season_number": season,
        "episode_number": episode,
        "name": f"S{season}E{episode}",
        "air_date": f"{FIRST_YEAR + season - 1}-01-{episode:02d}",
        "overview": f"Episode {episode} of season {season}.",
        "still_path": f"/s{season}e{episode}.jpg",
        "runtime": 47,
        **overrides,
    }


def _season_summary(season: int, episode_count: int) -> dict[str, Any]:
    return {
        "season_number": season,
        "name": f"Season {season}",
        "episode_count": episode_count,
        "air_date": f"{FIRST_YEAR + season - 1}-01-01",
        "poster_path": f"/season{season}.jpg",
        "overview": f"Season {season} overview.",
    }


def _season_detail(season: int, episodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"season_number": season, "episodes": episodes}


SEASON_ONE_EPISODES = [_episode(1, 1), _episode(1, 2)]
SEASON_TWO_EPISODES = [_episode(2, 1, air_date=""), _episode(2, 2)]
NEXT_EPISODE = _episode(3, 1, air_date="2030-01-01", still_path=None, runtime=None)

SERIES_PAYLOAD: dict[str, Any] = {
    "id": SERIES_ID,
    "status": "Returning Series",
    "next_episode_to_air": NEXT_EPISODE,
    "seasons": [
        _season_summary(SPECIALS_SEASON, 3),
        _season_summary(1, 2),
        _season_summary(2, 2),
    ],
    "season/1": _season_detail(1, SEASON_ONE_EPISODES),
    "season/2": _season_detail(2, SEASON_TWO_EPISODES),
    "season/0": _season_detail(SPECIALS_SEASON, [_episode(SPECIALS_SEASON, 1)]),
}


def _response(payload: dict[str, Any], status_code: int = 200) -> MagicMock:
    response = MagicMock(status_code=status_code)
    response.json.return_value = payload
    return response


@pytest.fixture
def cache(tmp_path: Path, mocker: MockerFixture) -> Iterator[diskcache.Cache]:
    temp_cache = diskcache.Cache(str(tmp_path / "cache"))
    mocker.patch.object(tmdb, "app_cache", temp_cache)
    mocker.patch("torrent_downloader.routers.system.app_cache", temp_cache)
    yield temp_cache
    temp_cache.close()


@pytest.fixture(autouse=True)
def tmdb_config(mocker: MockerFixture) -> None:
    mocker.patch.object(tmdb.config, "tmdb_api_key", "tmdb-test-key")
    mocker.patch.object(tmdb.config, "target_language", "en")
    mocker.patch.object(tmdb.config, "discover_cache_seconds", 86400)


def _url_and_params(call: Any) -> tuple[str, dict[str, Any]]:
    return call.args[0], call.kwargs["params"]


def _mock_get(mocker: MockerFixture, payload: dict[str, Any], status_code: int = 200) -> MagicMock:
    return mocker.patch.object(tmdb.requests, "get", return_value=_response(payload, status_code))


def _large_series(season_count: int) -> dict[str, Any]:
    return {
        "id": SERIES_ID,
        "status": "Ended",
        "next_episode_to_air": None,
        "seasons": [_season_summary(n, 1) for n in range(1, season_count + 1)],
    }


def _large_series_get(season_count: int) -> Any:
    """Answers ``tv/{id}`` with the summary and ``tv/{id}/season/{n}`` per season."""

    def fake_get(url: str, params: dict[str, Any], timeout: int) -> MagicMock:
        if url.endswith(f"/tv/{SERIES_ID}"):
            return _response(_large_series(season_count))
        season = int(url.rsplit("/", 1)[-1])
        return _response(_season_detail(season, [_episode(season, 1)]))

    return fake_get


class TestRequests:
    def test_small_show_appends_every_season_to_one_series_call(
        self, cache, mocker: MockerFixture
    ) -> None:
        mock_get = _mock_get(mocker, SERIES_PAYLOAD)
        get_series_episodes(SERIES_ID)
        assert mock_get.call_count == SMALL_SHOW_CALLS
        summary_url, summary_params = _url_and_params(mock_get.call_args_list[0])
        assert summary_url.endswith(f"/tv/{SERIES_ID}")
        assert "append_to_response" not in summary_params
        url, params = _url_and_params(mock_get.call_args_list[1])
        assert url.endswith(f"/tv/{SERIES_ID}")
        assert params["append_to_response"] == "season/1,season/2"
        assert params["language"] == "en"
        assert params["api_key"] == "tmdb-test-key"

    def test_append_limit_is_inclusive(self, cache, mocker: MockerFixture) -> None:
        payload = _large_series(TMDB_APPEND_MAX_SEASONS)
        for n in range(1, TMDB_APPEND_MAX_SEASONS + 1):
            payload[f"season/{n}"] = _season_detail(n, [_episode(n, 1)])
        mock_get = _mock_get(mocker, payload)
        result = get_series_episodes(SERIES_ID)
        assert mock_get.call_count == SMALL_SHOW_CALLS
        assert len(result.episodes) == TMDB_APPEND_MAX_SEASONS

    def test_large_show_fetches_each_season_separately(self, cache, mocker: MockerFixture) -> None:
        mock_get = mocker.patch.object(
            tmdb.requests, "get", side_effect=_large_series_get(BEYOND_APPEND_LIMIT)
        )
        result = get_series_episodes(SERIES_ID)
        assert mock_get.call_count == SUMMARY_CALL + BEYOND_APPEND_LIMIT
        urls = [call.args[0] for call in mock_get.call_args_list]
        assert urls[0].endswith(f"/tv/{SERIES_ID}")
        assert "append_to_response" not in mock_get.call_args_list[0].kwargs["params"]
        assert urls[1:] == [
            f"{tmdb.TMDB_BASE_URL}/tv/{SERIES_ID}/season/{n}"
            for n in range(1, BEYOND_APPEND_LIMIT + 1)
        ]
        assert [e.season for e in result.episodes] == list(range(1, BEYOND_APPEND_LIMIT + 1))


class TestMapping:
    def test_returns_contract_model(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, SERIES_PAYLOAD)
        result = get_series_episodes(SERIES_ID)
        assert isinstance(result, SeriesEpisodesResponse)
        assert result.tmdb_id == SERIES_ID

    def test_specials_season_dropped_from_seasons_and_episodes(
        self, cache, mocker: MockerFixture
    ) -> None:
        _mock_get(mocker, SERIES_PAYLOAD)
        result = get_series_episodes(SERIES_ID)
        assert [s.season for s in result.seasons] == [1, 2]
        assert all(e.season != SPECIALS_SEASON for e in result.episodes)

    def test_season_fields(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, SERIES_PAYLOAD)
        first = get_series_episodes(SERIES_ID).seasons[0]
        assert first.season == 1
        assert first.name == "Season 1"
        assert first.episode_count == 2
        assert first.air_date == date(FIRST_YEAR, 1, 1)
        assert first.poster_path == "/season1.jpg"
        assert first.overview == "Season 1 overview."

    def test_episodes_flattened_in_season_episode_order(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, SERIES_PAYLOAD)
        result = get_series_episodes(SERIES_ID)
        assert [(e.season, e.episode) for e in result.episodes] == [
            (1, 1),
            (1, 2),
            (2, 1),
            (2, 2),
        ]

    def test_episode_fields(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, SERIES_PAYLOAD)
        first = get_series_episodes(SERIES_ID).episodes[0]
        assert first.title == "S1E1"
        assert first.air_date == date(FIRST_YEAR, 1, 1)
        assert first.overview == "Episode 1 of season 1."
        assert first.still_path == "/s1e1.jpg"
        assert first.runtime_minutes == 47

    def test_empty_air_date_becomes_none(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, SERIES_PAYLOAD)
        unaired = get_series_episodes(SERIES_ID).episodes[2]
        assert (unaired.season, unaired.episode) == (2, 1)
        assert unaired.air_date is None

    def test_next_episode_mapped(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, SERIES_PAYLOAD)
        next_episode = get_series_episodes(SERIES_ID).next_episode
        assert next_episode is not None
        assert (next_episode.season, next_episode.episode) == (3, 1)
        assert next_episode.air_date == date(2030, 1, 1)
        assert next_episode.still_path is None
        assert next_episode.runtime_minutes is None

    def test_no_next_episode_is_none(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, {**SERIES_PAYLOAD, "next_episode_to_air": None})
        assert get_series_episodes(SERIES_ID).next_episode is None

    def test_status_passed_through(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, SERIES_PAYLOAD)
        assert get_series_episodes(SERIES_ID).status == "Returning Series"


class TestCaching:
    def test_second_call_does_not_hit_tmdb(self, cache, mocker: MockerFixture) -> None:
        mock_get = _mock_get(mocker, SERIES_PAYLOAD)
        first = get_series_episodes(SERIES_ID)
        second = get_series_episodes(SERIES_ID)
        assert mock_get.call_count == SMALL_SHOW_CALLS
        assert second == first

    def test_key_varies_by_series_and_language(self, cache, mocker: MockerFixture) -> None:
        mock_get = _mock_get(mocker, SERIES_PAYLOAD)
        get_series_episodes(SERIES_ID)
        get_series_episodes(SERIES_ID + 1)
        mocker.patch.object(tmdb.config, "target_language", "fr")
        get_series_episodes(SERIES_ID)
        assert mock_get.call_count == 3 * SMALL_SHOW_CALLS

    def test_ttl_read_from_runtime_setting_at_write_time(
        self, cache, mocker: MockerFixture
    ) -> None:
        _mock_get(mocker, SERIES_PAYLOAD)
        spy = mocker.spy(cache, "set")
        mocker.patch.object(tmdb.config, "discover_cache_seconds", 7200)
        get_series_episodes(SERIES_ID)
        assert spy.call_args.kwargs["expire"] == 7200

    def test_failure_is_not_cached(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, {}, status_code=500)
        with pytest.raises(TmdbUnavailableError):
            get_series_episodes(SERIES_ID)
        assert len(cache) == 0

    def test_delete_cache_route_clears_entries(
        self, cache, client: TestClient, mocker: MockerFixture
    ) -> None:
        mock_get = _mock_get(mocker, SERIES_PAYLOAD)
        get_series_episodes(SERIES_ID)
        assert client.delete("/api/v1/cache").status_code == 200
        get_series_episodes(SERIES_ID)
        assert mock_get.call_count == 2 * SMALL_SHOW_CALLS


class TestFailures:
    def test_missing_api_key_raises(self, cache, mocker: MockerFixture) -> None:
        mocker.patch.object(tmdb.config, "tmdb_api_key", None)
        mock_get = _mock_get(mocker, SERIES_PAYLOAD)
        with pytest.raises(TmdbUnavailableError):
            get_series_episodes(SERIES_ID)
        mock_get.assert_not_called()

    def test_network_error_raises(self, cache, mocker: MockerFixture) -> None:
        mocker.patch.object(tmdb.requests, "get", side_effect=requests.ConnectionError("down"))
        with pytest.raises(TmdbUnavailableError):
            get_series_episodes(SERIES_ID)
