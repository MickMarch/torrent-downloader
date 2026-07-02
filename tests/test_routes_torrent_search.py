"""HTTP layer tests for GET /api/v1/search/torrents."""

from typing import Any

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

SEARCH_URL = "/api/v1/search/torrents"


def _make_torrent(name: str, seeders: int, url: str) -> dict[str, Any]:
    return {
        "fileName": name,
        "fileUrl": url,
        "nbSeeders": seeders,
        "nbLeechers": 5,
        "siteUrl": "https://example.com",
        "descrLink": "https://example.com/desc",
        "fileSize": 10_000_000_000,
    }


MOCK_FILTERED_RESULTS: list[dict[str, Any]] = [
    _make_torrent("Inception.2010.2160p.BluRay.x265", 100, "magnet:?xt=urn:btih:aaa"),
    _make_torrent("Inception.2010.1080p.WEB-DL.x264", 80, "magnet:?xt=urn:btih:bbb"),
    _make_torrent("Inception.2010.720p.HDTV.x264", 30, "magnet:?xt=urn:btih:ccc"),
]


MOVIE_PARAMS = {"query": "inception", "media_type": "movie"}


def _patch_pipeline(mocker: MockerFixture, results: list[dict[str, Any]]) -> None:
    mocker.patch(
        "torrent_downloader.routers.search.get_torrent_client", return_value=mocker.MagicMock()
    )
    mocker.patch("torrent_downloader.routers.search.search_torrents", return_value=results)
    mocker.patch("torrent_downloader.routers.search.filter_and_sort_results", return_value=results)


class TestSearchTorrentsRoute:
    def test_returns_503_when_client_unavailable(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch("torrent_downloader.routers.search.get_torrent_client", return_value=None)
        response = client.get(SEARCH_URL, params=MOVIE_PARAMS)
        assert response.status_code == 503

    def test_returns_200_with_valid_client(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, MOCK_FILTERED_RESULTS)
        response = client.get(SEARCH_URL, params=MOVIE_PARAMS)
        assert response.status_code == 200

    def test_response_shape_has_status_message_data(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, MOCK_FILTERED_RESULTS)
        body = client.get(SEARCH_URL, params=MOVIE_PARAMS).json()
        assert "status" in body
        assert "message" in body
        assert "data" in body

    def test_results_grouped_by_resolution_keys(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, MOCK_FILTERED_RESULTS)
        data = client.get(SEARCH_URL, params=MOVIE_PARAMS).json()["data"]
        for key in data:
            assert key in ("4K", "1080p", "720p")

    def test_returns_empty_data_when_no_results(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, [])
        body = client.get(SEARCH_URL, params={"query": "xyzzy", "media_type": "movie"}).json()
        assert body["data"] == {}

    def test_requires_query_param(self, client: TestClient) -> None:
        response = client.get(SEARCH_URL, params={"media_type": "movie"})
        assert response.status_code == 422

    def test_requires_media_type_param(self, client: TestClient) -> None:
        response = client.get(SEARCH_URL, params={"query": "inception"})
        assert response.status_code == 422

    def test_movie_with_season_is_rejected(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, MOCK_FILTERED_RESULTS)
        response = client.get(
            SEARCH_URL, params={"query": "inception", "media_type": "movie", "season": 1}
        )
        assert response.status_code == 422

    def test_orphan_episode_is_rejected(self, client: TestClient, mocker: MockerFixture) -> None:
        _patch_pipeline(mocker, MOCK_FILTERED_RESULTS)
        response = client.get(
            SEARCH_URL, params={"query": "show", "media_type": "show", "episode": 3}
        )
        assert response.status_code == 422

    def test_show_season_search_threads_scope_into_filter(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        _patch_pipeline(mocker, MOCK_FILTERED_RESULTS)
        spy = mocker.patch(
            "torrent_downloader.routers.search.filter_by_scope",
            return_value=MOCK_FILTERED_RESULTS,
        )
        response = client.get(
            SEARCH_URL, params={"query": "the wire", "media_type": "show", "season": 2}
        )
        assert response.status_code == 200
        scope_arg = spy.call_args.args[1]
        assert scope_arg.season == 2
        assert scope_arg.episode is None
