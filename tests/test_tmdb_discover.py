"""Service tests for TMDB trending, discover-by-genre and genre lists."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import diskcache
import pytest
import requests
from fastapi.testclient import TestClient
from medialab_contracts import DiscoverResponse, GenresResponse, MediaType
from pytest_mock import MockerFixture

from torrent_downloader.services import tmdb
from torrent_downloader.services.tmdb import (
    DISCOVER_MIN_VOTES,
    TmdbUnavailableError,
    get_discover,
    get_genres,
)

MOVIE_PAGE: dict[str, Any] = {
    "page": 1,
    "total_pages": 3,
    "results": [
        {
            "id": 27205,
            "title": "Inception",
            "release_date": "2010-07-16",
            "overview": "A thief who steals corporate secrets.",
            "vote_average": 8.4,
            "poster_path": "/inception.jpg",
        },
        {"id": 1, "title": "Undated", "release_date": "", "poster_path": None},
    ],
}

SHOW_PAGE: dict[str, Any] = {
    "page": 2,
    "total_pages": 9,
    "results": [
        {
            "id": 1396,
            "name": "Breaking Bad",
            "first_air_date": "2008-01-20",
            "overview": "A chemistry teacher turned drug kingpin.",
            "vote_average": 9.5,
            "poster_path": "/bb.jpg",
        }
    ],
}

GENRES_PAYLOAD: dict[str, Any] = {"genres": [{"id": 28, "name": "Action"}]}


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


def _mock_get(mocker: MockerFixture, payload: dict[str, Any], status_code: int = 200) -> MagicMock:
    return mocker.patch.object(tmdb.requests, "get", return_value=_response(payload, status_code))


def _called_url_and_params(mock_get: MagicMock) -> tuple[str, dict[str, Any]]:
    call = mock_get.call_args
    return call.args[0], call.kwargs["params"]


class TestSources:
    def test_no_genre_calls_trending(self, cache, mocker: MockerFixture) -> None:
        mock_get = _mock_get(mocker, MOVIE_PAGE)
        get_discover(MediaType.MOVIE)
        url, params = _called_url_and_params(mock_get)
        assert url.endswith("/trending/movie/week")
        assert "with_genres" not in params
        assert params["language"] == "en"
        assert params["api_key"] == "tmdb-test-key"
        assert params["page"] == 1

    def test_genre_calls_discover_with_vote_floor(self, cache, mocker: MockerFixture) -> None:
        mock_get = _mock_get(mocker, MOVIE_PAGE)
        get_discover(MediaType.MOVIE, genre=28, page=2)
        url, params = _called_url_and_params(mock_get)
        assert url.endswith("/discover/movie")
        assert params["with_genres"] == 28
        assert params["sort_by"] == "popularity.desc"
        assert params["vote_count.gte"] == DISCOVER_MIN_VOTES
        assert params["page"] == 2

    def test_show_uses_tmdb_tv_paths(self, cache, mocker: MockerFixture) -> None:
        mock_get = _mock_get(mocker, SHOW_PAGE)
        get_discover(MediaType.SHOW)
        assert _called_url_and_params(mock_get)[0].endswith("/trending/tv/week")

    def test_genre_list_endpoint(self, cache, mocker: MockerFixture) -> None:
        mock_get = _mock_get(mocker, GENRES_PAYLOAD)
        result = get_genres(MediaType.SHOW)
        url, params = _called_url_and_params(mock_get)
        assert url.endswith("/genre/tv/list")
        assert params["language"] == "en"
        assert isinstance(result, GenresResponse)
        assert result.genres[0].id == 28
        assert result.genres[0].name == "Action"


class TestMapping:
    def test_movie_fields(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, MOVIE_PAGE)
        result = get_discover(MediaType.MOVIE)
        assert isinstance(result, DiscoverResponse)
        assert result.page == 1
        assert result.total_pages == 3
        first = result.items[0]
        assert first.tmdb_id == 27205
        assert first.media_type is MediaType.MOVIE
        assert first.title == "Inception"
        assert first.year == "2010"
        assert first.vote_average == 8.4
        assert first.poster_path == "/inception.jpg"

    def test_missing_date_gives_no_year(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, MOVIE_PAGE)
        undated = get_discover(MediaType.MOVIE).items[1]
        assert undated.year is None
        assert undated.poster_path is None

    def test_tv_mapped_to_show_with_name_and_first_air_date(
        self, cache, mocker: MockerFixture
    ) -> None:
        _mock_get(mocker, SHOW_PAGE)
        show = get_discover(MediaType.SHOW, page=2).items[0]
        assert show.media_type is MediaType.SHOW
        assert show.title == "Breaking Bad"
        assert show.year == "2008"

    def test_total_pages_capped_at_tmdb_limit(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, {**MOVIE_PAGE, "total_pages": 40000})
        assert get_discover(MediaType.MOVIE).total_pages == tmdb.TMDB_MAX_PAGE


class TestCaching:
    def test_second_call_within_ttl_does_not_hit_tmdb(self, cache, mocker: MockerFixture) -> None:
        mock_get = _mock_get(mocker, MOVIE_PAGE)
        first = get_discover(MediaType.MOVIE, genre=28)
        second = get_discover(MediaType.MOVIE, genre=28)
        assert mock_get.call_count == 1
        assert second == first
        assert second.cached_at == first.cached_at

    def test_genres_cached(self, cache, mocker: MockerFixture) -> None:
        mock_get = _mock_get(mocker, GENRES_PAYLOAD)
        get_genres(MediaType.MOVIE)
        get_genres(MediaType.MOVIE)
        assert mock_get.call_count == 1

    @pytest.mark.parametrize(
        ("first", "second"),
        [
            ({"media_type": MediaType.MOVIE}, {"media_type": MediaType.SHOW}),
            ({"media_type": MediaType.MOVIE}, {"media_type": MediaType.MOVIE, "genre": 28}),
            ({"media_type": MediaType.MOVIE}, {"media_type": MediaType.MOVIE, "page": 2}),
        ],
    )
    def test_key_varies_by_type_genre_and_page(
        self, cache, mocker: MockerFixture, first, second
    ) -> None:
        mock_get = _mock_get(mocker, MOVIE_PAGE)
        get_discover(**first)
        get_discover(**second)
        assert mock_get.call_count == 2

    def test_key_varies_by_language(self, cache, mocker: MockerFixture) -> None:
        mock_get = _mock_get(mocker, MOVIE_PAGE)
        get_discover(MediaType.MOVIE)
        mocker.patch.object(tmdb.config, "target_language", "fr")
        get_discover(MediaType.MOVIE)
        assert mock_get.call_count == 2

    def test_ttl_read_from_runtime_setting_at_write_time(
        self, cache, mocker: MockerFixture
    ) -> None:
        _mock_get(mocker, MOVIE_PAGE)
        spy = mocker.spy(cache, "set")
        mocker.patch.object(tmdb.config, "discover_cache_seconds", 7200)
        get_discover(MediaType.MOVIE)
        mocker.patch.object(tmdb.config, "discover_cache_seconds", 3600)
        get_discover(MediaType.SHOW)
        assert [c.kwargs["expire"] for c in spy.call_args_list] == [7200, 3600]

    def test_failure_is_not_cached(self, cache, mocker: MockerFixture) -> None:
        _mock_get(mocker, {}, status_code=500)
        with pytest.raises(TmdbUnavailableError):
            get_discover(MediaType.MOVIE)
        assert len(cache) == 0

    def test_delete_cache_route_clears_discover_entries(
        self, cache, client: TestClient, mocker: MockerFixture
    ) -> None:
        mock_get = _mock_get(mocker, MOVIE_PAGE)
        get_discover(MediaType.MOVIE)
        get_genres(MediaType.MOVIE)
        assert client.delete("/api/v1/cache").status_code == 200
        get_discover(MediaType.MOVIE)
        get_genres(MediaType.MOVIE)
        assert mock_get.call_count == 4


class TestFailures:
    def test_missing_api_key_raises(self, cache, mocker: MockerFixture) -> None:
        mocker.patch.object(tmdb.config, "tmdb_api_key", None)
        mock_get = _mock_get(mocker, MOVIE_PAGE)
        with pytest.raises(TmdbUnavailableError):
            get_discover(MediaType.MOVIE)
        mock_get.assert_not_called()

    def test_network_error_raises(self, cache, mocker: MockerFixture) -> None:
        mocker.patch.object(tmdb.requests, "get", side_effect=requests.ConnectionError("down"))
        with pytest.raises(TmdbUnavailableError):
            get_genres(MediaType.MOVIE)
