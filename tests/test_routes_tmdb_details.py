"""HTTP layer tests for GET /api/v1/search/tmdb/movie/{id} and /api/v1/search/tmdb/show/{id}."""

from datetime import date
from typing import Any

from fastapi.testclient import TestClient
from medialab_contracts import Episode, Season, SeriesEpisodesResponse
from pytest_mock import MockerFixture

from torrent_downloader.services.tmdb import TmdbUnavailableError

MOCK_MOVIE_PAYLOAD: dict[str, Any] = {
    "id": 27205,
    "title": "Inception",
    "original_title": "Inception",
    "overview": "A thief who steals corporate secrets.",
    "release_date": "2010-07-16",
    "runtime": 148,
    "status": "Released",
    "genres": [{"id": 28, "name": "Action"}, {"id": 878, "name": "Science Fiction"}],
    "vote_average": 8.4,
    "poster_path": "/qmDpIHrmpJINaRKAfWQfftjCdyi.jpg",
}

MOCK_TV_PAYLOAD: dict[str, Any] = {
    "id": 1396,
    "name": "Breaking Bad",
    "original_name": "Breaking Bad",
    "overview": "A chemistry teacher turned drug kingpin.",
    "first_air_date": "2008-01-20",
    "number_of_seasons": 5,
    "number_of_episodes": 62,
    "status": "Ended",
    "genres": [{"id": 18, "name": "Drama"}, {"id": 80, "name": "Crime"}],
    "vote_average": 9.5,
    "poster_path": "/ggFHVNu6YYI5L9pCfOacjizRGt.jpg",
}

EPISODES_RESULT = SeriesEpisodesResponse(
    tmdb_id=1396,
    seasons=[Season(season=1, name="Season 1", episode_count=1, air_date=date(2008, 1, 20))],
    episodes=[Episode(season=1, episode=1, title="Pilot", air_date=date(2008, 1, 20))],
    next_episode=None,
    status="Ended",
)


class TestMovieDetailsRoute:
    def test_returns_200_for_valid_movie_id(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.search.get_movie_details", return_value=MOCK_MOVIE_PAYLOAD
        )
        assert client.get("/api/v1/search/tmdb/movie/27205").status_code == 200

    def test_response_status_is_success(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(
            "torrent_downloader.routers.search.get_movie_details", return_value=MOCK_MOVIE_PAYLOAD
        )
        body = client.get("/api/v1/search/tmdb/movie/27205").json()
        assert body["status"] == "success"
        assert "data" in body

    def test_data_contains_full_tmdb_payload(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.search.get_movie_details", return_value=MOCK_MOVIE_PAYLOAD
        )
        data = client.get("/api/v1/search/tmdb/movie/27205").json()["data"]
        assert data["id"] == 27205
        assert data["title"] == "Inception"
        assert data["runtime"] == 148
        assert len(data["genres"]) == 2

    def test_returns_error_status_when_movie_not_found(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch("torrent_downloader.routers.search.get_movie_details", return_value={})
        body = client.get("/api/v1/search/tmdb/movie/99999999").json()
        assert body["status"] == "error"
        assert body["data"] is None

    def test_returns_422_for_non_integer_movie_id(self, client: TestClient) -> None:
        assert client.get("/api/v1/search/tmdb/movie/not-an-id").status_code == 422


class TestTvDetailsRoute:
    def test_returns_200_for_valid_series_id(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.search.get_tv_details", return_value=MOCK_TV_PAYLOAD
        )
        assert client.get("/api/v1/search/tmdb/show/1396").status_code == 200

    def test_response_status_is_success(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(
            "torrent_downloader.routers.search.get_tv_details", return_value=MOCK_TV_PAYLOAD
        )
        body = client.get("/api/v1/search/tmdb/show/1396").json()
        assert body["status"] == "success"
        assert "data" in body

    def test_data_contains_full_tmdb_payload(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.search.get_tv_details", return_value=MOCK_TV_PAYLOAD
        )
        data = client.get("/api/v1/search/tmdb/show/1396").json()["data"]
        assert data["id"] == 1396
        assert data["name"] == "Breaking Bad"
        assert data["number_of_seasons"] == 5
        assert data["number_of_episodes"] == 62

    def test_returns_error_status_when_series_not_found(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch("torrent_downloader.routers.search.get_tv_details", return_value={})
        body = client.get("/api/v1/search/tmdb/show/99999999").json()
        assert body["status"] == "error"
        assert body["data"] is None

    def test_returns_422_for_non_integer_series_id(self, client: TestClient) -> None:
        assert client.get("/api/v1/search/tmdb/show/not-an-id").status_code == 422


class TestSeriesEpisodesRoute:
    EPISODES_URL = "/api/v1/search/tmdb/show/1396/episodes"
    SERVICE = "torrent_downloader.routers.search.get_series_episodes"

    def test_returns_contract_shape(self, client: TestClient, mocker: MockerFixture) -> None:
        mock = mocker.patch(self.SERVICE, return_value=EPISODES_RESULT)
        response = client.get(self.EPISODES_URL)
        assert response.status_code == 200
        assert SeriesEpisodesResponse.model_validate(response.json()) == EPISODES_RESULT
        assert response.json()["episodes"][0]["air_date"] == "2008-01-20"
        mock.assert_called_once_with(1396)

    def test_tmdb_unavailable_is_503(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(self.SERVICE, side_effect=TmdbUnavailableError("down"))
        response = client.get(self.EPISODES_URL)
        assert response.status_code == 503
        assert response.json()["code"] == "TMDB_UNAVAILABLE"

    def test_returns_422_for_non_integer_series_id(self, client: TestClient) -> None:
        assert client.get("/api/v1/search/tmdb/show/not-an-id/episodes").status_code == 422

    def test_requires_api_key(self) -> None:
        from torrent_downloader.main import app

        assert TestClient(app).get(self.EPISODES_URL).status_code == 403
