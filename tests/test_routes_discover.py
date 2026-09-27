"""HTTP layer tests for GET /api/v1/discover/{media_type} and its genre list."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from medialab_contracts import (
    DiscoverItem,
    DiscoverResponse,
    Genre,
    GenresResponse,
    MediaType,
)
from pytest_mock import MockerFixture

from torrent_downloader.services.tmdb import TmdbUnavailableError

DISCOVER_URL = "/api/v1/discover"
ROUTER = "torrent_downloader.routers.discover"

DISCOVER_RESULT = DiscoverResponse(
    items=[
        DiscoverItem(
            tmdb_id=1396,
            media_type=MediaType.SHOW,
            title="Breaking Bad",
            year="2008",
            overview="A chemistry teacher turned drug kingpin.",
            vote_average=9.5,
            poster_path="/bb.jpg",
        )
    ],
    page=1,
    total_pages=9,
    cached_at=datetime(2026, 9, 27, tzinfo=UTC),
)

GENRES_RESULT = GenresResponse(genres=[Genre(id=18, name="Drama")])


class TestDiscoverRoute:
    def test_returns_contract_shape(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(f"{ROUTER}.get_discover", return_value=DISCOVER_RESULT)
        response = client.get(f"{DISCOVER_URL}/show")
        assert response.status_code == 200
        parsed = DiscoverResponse.model_validate(response.json())
        assert parsed == DISCOVER_RESULT
        assert response.json()["items"][0]["media_type"] == "show"

    def test_passes_type_genre_and_page(self, client: TestClient, mocker: MockerFixture) -> None:
        mock = mocker.patch(f"{ROUTER}.get_discover", return_value=DISCOVER_RESULT)
        client.get(f"{DISCOVER_URL}/movie", params={"genre": 28, "page": 3})
        mock.assert_called_once_with(MediaType.MOVIE, genre=28, page=3)

    def test_defaults_to_first_page_without_genre(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mock = mocker.patch(f"{ROUTER}.get_discover", return_value=DISCOVER_RESULT)
        client.get(f"{DISCOVER_URL}/movie")
        mock.assert_called_once_with(MediaType.MOVIE, genre=None, page=1)

    def test_tmdb_media_type_tv_is_rejected(self, client: TestClient) -> None:
        response = client.get(f"{DISCOVER_URL}/tv")
        assert response.status_code == 422
        assert response.json()["code"] == "INVALID_INPUT"

    def test_page_out_of_range_is_rejected(self, client: TestClient) -> None:
        assert client.get(f"{DISCOVER_URL}/movie", params={"page": 0}).status_code == 422
        assert client.get(f"{DISCOVER_URL}/movie", params={"page": 501}).status_code == 422

    def test_tmdb_unavailable_is_503(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(f"{ROUTER}.get_discover", side_effect=TmdbUnavailableError("down"))
        response = client.get(f"{DISCOVER_URL}/movie")
        assert response.status_code == 503
        assert response.json()["code"] == "TMDB_UNAVAILABLE"

    def test_requires_api_key(self) -> None:
        from torrent_downloader.main import app

        assert TestClient(app).get(f"{DISCOVER_URL}/movie").status_code == 403


class TestGenresRoute:
    def test_returns_contract_shape(self, client: TestClient, mocker: MockerFixture) -> None:
        mock = mocker.patch(f"{ROUTER}.get_genres", return_value=GENRES_RESULT)
        response = client.get(f"{DISCOVER_URL}/show/genres")
        assert response.status_code == 200
        assert GenresResponse.model_validate(response.json()) == GENRES_RESULT
        mock.assert_called_once_with(MediaType.SHOW)

    def test_tmdb_unavailable_is_503(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(f"{ROUTER}.get_genres", side_effect=TmdbUnavailableError("down"))
        response = client.get(f"{DISCOVER_URL}/movie/genres")
        assert response.status_code == 503
        assert response.json()["code"] == "TMDB_UNAVAILABLE"

    def test_requires_api_key(self) -> None:
        from torrent_downloader.main import app

        assert TestClient(app).get(f"{DISCOVER_URL}/movie/genres").status_code == 403
