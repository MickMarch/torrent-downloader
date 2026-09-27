"""HTTP layer tests for GET /api/v1/search/tmdb/{media_type}/{id}/videos."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from medialab_contracts import MediaType, Video, VideosResponse, VideoType
from pytest_mock import MockerFixture

from torrent_downloader.services.tmdb import TmdbUnavailableError

MOVIE_ID = 438631
SERIES_ID = 100088
SEASON = 2
MOVIE_URL = f"/api/v1/search/tmdb/movie/{MOVIE_ID}/videos"
SHOW_URL = f"/api/v1/search/tmdb/show/{SERIES_ID}/videos"
SERVICE = "torrent_downloader.routers.search.get_videos"

VIDEOS_RESULT = VideosResponse(
    videos=[
        Video(
            key="abc123",
            name="Official Trailer",
            type=VideoType.TRAILER,
            official=True,
            published_at=datetime(2024, 3, 1, 12, 0, tzinfo=UTC),
            language="en",
        ),
        Video(key="def456", name="Teaser", type=VideoType.TEASER),
    ]
)


class TestVideosRoute:
    def test_returns_contract_shape(self, client: TestClient, mocker: MockerFixture) -> None:
        mock = mocker.patch(SERVICE, return_value=VIDEOS_RESULT)
        response = client.get(MOVIE_URL)
        assert response.status_code == 200
        assert VideosResponse.model_validate(response.json()) == VIDEOS_RESULT
        assert response.json()["videos"][0]["type"] == "trailer"
        mock.assert_called_once_with(MediaType.MOVIE, MOVIE_ID, season=None)

    def test_passes_season_for_shows(self, client: TestClient, mocker: MockerFixture) -> None:
        mock = mocker.patch(SERVICE, return_value=VIDEOS_RESULT)
        assert client.get(SHOW_URL, params={"season": SEASON}).status_code == 200
        mock.assert_called_once_with(MediaType.SHOW, SERIES_ID, season=SEASON)

    def test_season_on_movie_is_422(self, client: TestClient, mocker: MockerFixture) -> None:
        mock = mocker.patch(SERVICE, return_value=VIDEOS_RESULT)
        response = client.get(MOVIE_URL, params={"season": SEASON})
        assert response.status_code == 422
        assert response.json()["code"] == "INVALID_INPUT"
        mock.assert_not_called()

    def test_tmdb_media_type_tv_is_rejected(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/search/tmdb/tv/{SERIES_ID}/videos")
        assert response.status_code == 422
        assert response.json()["code"] == "INVALID_INPUT"

    def test_non_integer_id_is_422(self, client: TestClient) -> None:
        assert client.get("/api/v1/search/tmdb/movie/not-an-id/videos").status_code == 422

    def test_tmdb_unavailable_is_503(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(SERVICE, side_effect=TmdbUnavailableError("down"))
        response = client.get(MOVIE_URL)
        assert response.status_code == 503
        assert response.json()["code"] == "TMDB_UNAVAILABLE"

    def test_requires_api_key(self) -> None:
        from torrent_downloader.main import app

        assert TestClient(app).get(MOVIE_URL).status_code == 403
