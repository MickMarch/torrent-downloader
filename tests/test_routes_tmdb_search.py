"""HTTP layer tests for GET /api/v1/search/tmdb."""

from typing import Any

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

SEARCH_URL = "/api/v1/search/tmdb"

MOCK_TMDB_RESULTS: list[dict[str, Any]] = [
    {
        "id": 27205,
        "title": "Inception",
        "name": "",
        "media_type": "movie",
        "release_date": "2010-07-16",
        "first_air_date": "",
        "overview": "A thief who steals corporate secrets.",
        "vote_average": 8.4,
        "poster_path": "/qmDpIHrmpJINaRKAfWQfftjCdyi.jpg",
    },
    {
        "id": 1396,
        "title": "",
        "name": "Breaking Bad",
        "media_type": "tv",
        "release_date": "",
        "first_air_date": "2008-01-20",
        "overview": "A chemistry teacher turned drug kingpin.",
        "vote_average": 9.5,
        "poster_path": "/ggFHVNu6YYI5L9pCfOacjizRGt.jpg",
    },
]


class TestSearchTmdbRoute:
    def test_returns_200_with_results(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(
            "torrent_downloader.routers.search.search_tmdb_multi", return_value=MOCK_TMDB_RESULTS
        )
        response = client.get(SEARCH_URL, params={"query": "inception"})
        assert response.status_code == 200

    def test_response_shape_has_status_message_data(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.search.search_tmdb_multi", return_value=MOCK_TMDB_RESULTS
        )
        body = client.get(SEARCH_URL, params={"query": "inception"}).json()
        assert "status" in body
        assert "message" in body
        assert "data" in body

    def test_result_contains_expected_fields(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.search.search_tmdb_multi", return_value=MOCK_TMDB_RESULTS
        )
        data = client.get(SEARCH_URL, params={"query": "inception"}).json()["data"]
        first = data[0]
        assert "tmdb_id" in first
        assert "title" in first
        assert "year" in first
        assert "media_type" in first
        assert "overview" in first
        assert "vote_average" in first
        assert "poster_path" in first

    def test_movie_result_fields_mapped_correctly(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.search.search_tmdb_multi", return_value=MOCK_TMDB_RESULTS
        )
        data = client.get(SEARCH_URL, params={"query": "inception"}).json()["data"]
        movie = next(r for r in data if r["media_type"] == "movie")
        assert movie["tmdb_id"] == 27205
        assert movie["title"] == "Inception"
        assert movie["year"] == "2010"
        assert movie["vote_average"] == 8.4

    def test_tv_result_fields_mapped_correctly(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.search.search_tmdb_multi", return_value=MOCK_TMDB_RESULTS
        )
        data = client.get(SEARCH_URL, params={"query": "breaking bad"}).json()["data"]
        show = next(r for r in data if r["media_type"] == "tv")
        assert show["tmdb_id"] == 1396
        assert show["title"] == "Breaking Bad"
        assert show["year"] == "2008"

    def test_returns_empty_data_list_when_no_results(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch("torrent_downloader.routers.search.search_tmdb_multi", return_value=[])
        body = client.get(SEARCH_URL, params={"query": "xyzzy"}).json()
        assert body["data"] == []

    def test_requires_query_param(self, client: TestClient) -> None:
        response = client.get(SEARCH_URL)
        assert response.status_code == 422
