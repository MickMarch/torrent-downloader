"""Tests for /download path resolution, hash caching, and /transfers/{hash}/info."""

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from torrent_downloader.core.errors import ErrorCode

MOVIE_MAGNET = "magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678&dn=Movie"
SHOW_MAGNET = "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12&dn=Show"


@pytest.fixture(autouse=True)
def patch_paths(mocker: MockerFixture):
    mocker.patch(
        "torrent_downloader.routers.transfers.config",
        movies_path="/media/movies",
        tv_path="/media/tv",
        movies_host_path="F:\\Media\\Movies",
        tv_host_path="F:\\Media\\TV",
    )


@pytest.fixture(autouse=True)
def clear_cache():
    from torrent_downloader.core.cache import app_cache

    app_cache.clear()
    yield
    app_cache.clear()


class TestDownloadResolvesSavePath:
    def test_movie_media_type_uses_movies_path(self, client: TestClient, mocker: MockerFixture) -> None:
        mock_client = mocker.MagicMock()
        mocker.patch("torrent_downloader.routers.transfers.get_torrent_client", return_value=mock_client)
        mocker.patch("torrent_downloader.routers.transfers.is_vpn_bound", return_value=True)

        client.post("/api/v1/download", json={"magnet_uri": MOVIE_MAGNET, "media_type": "movie"})

        mock_client.torrents_add.assert_called_once_with(urls=MOVIE_MAGNET, save_path="/media/movies")

    def test_show_media_type_uses_tv_path(self, client: TestClient, mocker: MockerFixture) -> None:
        mock_client = mocker.MagicMock()
        mocker.patch("torrent_downloader.routers.transfers.get_torrent_client", return_value=mock_client)
        mocker.patch("torrent_downloader.routers.transfers.is_vpn_bound", return_value=True)

        client.post("/api/v1/download", json={"magnet_uri": SHOW_MAGNET, "media_type": "show"})

        mock_client.torrents_add.assert_called_once_with(urls=SHOW_MAGNET, save_path="/media/tv")

    def test_dry_run_does_not_call_torrents_add(self, client: TestClient, mocker: MockerFixture) -> None:
        mock_client = mocker.MagicMock()
        mocker.patch("torrent_downloader.routers.transfers.get_torrent_client", return_value=mock_client)
        mocker.patch("torrent_downloader.routers.transfers.is_vpn_bound", return_value=True)

        response = client.post(
            "/api/v1/download", json={"magnet_uri": MOVIE_MAGNET, "media_type": "movie", "dry_run": True}
        )

        mock_client.torrents_add.assert_not_called()
        assert response.status_code == 202


class TestDownloadCachesHashMetadata:
    def test_successful_add_stores_media_type_and_host_path(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.transfers.config",
            movies_path="/media/movies",
            movies_host_path="F:\\Media\\Movies",
        )
        mock_client = mocker.MagicMock()
        mocker.patch("torrent_downloader.routers.transfers.get_torrent_client", return_value=mock_client)
        mocker.patch("torrent_downloader.routers.transfers.is_vpn_bound", return_value=True)

        client.post("/api/v1/download", json={"magnet_uri": MOVIE_MAGNET, "media_type": "movie"})

        from torrent_downloader.core.cache import app_cache

        cached = app_cache.get("media_type:1234567890abcdef1234567890abcdef12345678")
        assert cached == {"media_type": "movie", "host_path": "F:\\Media\\Movies"}

    def test_hash_extracted_and_normalised_to_lowercase(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(
            "torrent_downloader.routers.transfers.config",
            tv_path="/media/tv",
            tv_host_path="F:\\Media\\TV",
        )
        mock_client = mocker.MagicMock()
        mocker.patch("torrent_downloader.routers.transfers.get_torrent_client", return_value=mock_client)
        mocker.patch("torrent_downloader.routers.transfers.is_vpn_bound", return_value=True)

        client.post("/api/v1/download", json={"magnet_uri": SHOW_MAGNET, "media_type": "show"})

        from torrent_downloader.core.cache import app_cache

        cached = app_cache.get("media_type:abcdef1234567890abcdef1234567890abcdef12")
        assert cached == {"media_type": "show", "host_path": "F:\\Media\\TV"}

    def test_dry_run_does_not_cache(self, client: TestClient, mocker: MockerFixture) -> None:
        mock_client = mocker.MagicMock()
        mocker.patch("torrent_downloader.routers.transfers.get_torrent_client", return_value=mock_client)
        mocker.patch("torrent_downloader.routers.transfers.is_vpn_bound", return_value=True)

        client.post(
            "/api/v1/download", json={"magnet_uri": MOVIE_MAGNET, "media_type": "movie", "dry_run": True}
        )

        from torrent_downloader.core.cache import app_cache

        assert app_cache.get("media_type:1234567890abcdef1234567890abcdef12345678") is None


class TestTransferInfoEndpoint:
    def test_returns_cached_metadata_for_known_hash(self, client: TestClient) -> None:
        from torrent_downloader.core.cache import app_cache

        app_cache.set("media_type:abc123", {"media_type": "movie", "host_path": "F:\\Media\\Movies"})

        mocker_config = {"movies_path": "/media/movies"}
        response = client.get("/api/v1/transfers/abc123/info")

        assert response.status_code == 200
        body = response.json()
        assert body["media_type"] == "movie"
        assert body["host_path"] == "F:\\Media\\Movies"

    def test_returns_404_for_unknown_hash(self, client: TestClient) -> None:
        response = client.get("/api/v1/transfers/unknownhash/info")
        assert response.status_code == 404

    def test_404_body_has_transfer_not_found_code(self, client: TestClient) -> None:
        body = client.get("/api/v1/transfers/unknownhash/info").json()
        assert body["code"] == ErrorCode.TRANSFER_NOT_FOUND.value

    def test_response_includes_save_path_resolved_from_media_type(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.transfers.config",
            movies_path="/media/movies",
            tv_path="/media/tv",
        )
        from torrent_downloader.core.cache import app_cache

        app_cache.set("media_type:def456", {"media_type": "show", "host_path": "F:\\Media\\TV"})

        body = client.get("/api/v1/transfers/def456/info").json()
        assert body["save_path"] == "/media/tv"
