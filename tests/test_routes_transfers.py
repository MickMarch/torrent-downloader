"""Tests for /download host-path resolution, hash caching, and /transfers/{hash}/info."""

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from torrent_downloader.core.errors import ErrorCode

MOVIE_MAGNET = "magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678&dn=Movie"
SHOW_MAGNET = "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12&dn=Show"
TMDB_ID = 27205


def _download_body(magnet: str, media_type: str, **extra: object) -> dict[str, object]:
    return {"magnet_uri": magnet, "media_type": media_type, "tmdb_id": TMDB_ID, **extra}


@pytest.fixture(autouse=True)
def patch_media_host_path(mocker: MockerFixture):
    mocker.patch("torrent_downloader.routers.transfers.config", media_host_path="F:\\Media")


@pytest.fixture(autouse=True)
def clear_cache():
    from torrent_downloader.core.cache import app_cache

    app_cache.clear()
    yield
    app_cache.clear()


class TestDownloadResolvesHostPath:
    def test_movie_media_type_appends_movies_subdir(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mock_client = mocker.MagicMock()
        mocker.patch(
            "torrent_downloader.routers.transfers.get_torrent_client", return_value=mock_client
        )
        mocker.patch("torrent_downloader.routers.transfers.is_vpn_bound", return_value=True)

        client.post("/api/v1/download", json=_download_body(MOVIE_MAGNET, "movie"))

        mock_client.torrents_add.assert_called_once_with(
            urls=MOVIE_MAGNET, save_path="F:\\Media\\Movies"
        )

    def test_show_media_type_appends_shows_subdir(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mock_client = mocker.MagicMock()
        mocker.patch(
            "torrent_downloader.routers.transfers.get_torrent_client", return_value=mock_client
        )
        mocker.patch("torrent_downloader.routers.transfers.is_vpn_bound", return_value=True)

        client.post("/api/v1/download", json=_download_body(SHOW_MAGNET, "show"))

        mock_client.torrents_add.assert_called_once_with(
            urls=SHOW_MAGNET, save_path="F:\\Media\\Shows"
        )

    def test_dry_run_does_not_call_torrents_add(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mock_client = mocker.MagicMock()
        mocker.patch(
            "torrent_downloader.routers.transfers.get_torrent_client", return_value=mock_client
        )
        mocker.patch("torrent_downloader.routers.transfers.is_vpn_bound", return_value=True)

        response = client.post(
            "/api/v1/download", json=_download_body(MOVIE_MAGNET, "movie", dry_run=True)
        )

        mock_client.torrents_add.assert_not_called()
        assert response.status_code == 202


class TestDownloadCachesHashMetadata:
    def test_successful_add_stores_media_type_host_path_and_tmdb_id(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mock_client = mocker.MagicMock()
        mocker.patch(
            "torrent_downloader.routers.transfers.get_torrent_client", return_value=mock_client
        )
        mocker.patch("torrent_downloader.routers.transfers.is_vpn_bound", return_value=True)

        client.post("/api/v1/download", json=_download_body(MOVIE_MAGNET, "movie"))

        from torrent_downloader.core.cache import app_cache

        cached = app_cache.get("media_type:1234567890abcdef1234567890abcdef12345678")
        assert cached == {
            "media_type": "movie",
            "host_path": "F:\\Media\\Movies",
            "tmdb_id": TMDB_ID,
        }

    def test_hash_extracted_and_normalised_to_lowercase(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mock_client = mocker.MagicMock()
        mocker.patch(
            "torrent_downloader.routers.transfers.get_torrent_client", return_value=mock_client
        )
        mocker.patch("torrent_downloader.routers.transfers.is_vpn_bound", return_value=True)

        client.post("/api/v1/download", json=_download_body(SHOW_MAGNET, "show"))

        from torrent_downloader.core.cache import app_cache

        cached = app_cache.get("media_type:abcdef1234567890abcdef1234567890abcdef12")
        assert cached == {
            "media_type": "show",
            "host_path": "F:\\Media\\Shows",
            "tmdb_id": TMDB_ID,
        }

    def test_unparseable_hash_logs_warning_and_skips_cache(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mock_client = mocker.MagicMock()
        mocker.patch(
            "torrent_downloader.routers.transfers.get_torrent_client", return_value=mock_client
        )
        mocker.patch("torrent_downloader.routers.transfers.is_vpn_bound", return_value=True)
        mock_logger = mocker.patch("torrent_downloader.routers.transfers.app_logger")

        client.post("/api/v1/download", json=_download_body("magnet:?dn=NoHash", "movie"))

        mock_logger.warning.assert_called_once()

    def test_dry_run_does_not_cache(self, client: TestClient, mocker: MockerFixture) -> None:
        mock_client = mocker.MagicMock()
        mocker.patch(
            "torrent_downloader.routers.transfers.get_torrent_client", return_value=mock_client
        )
        mocker.patch("torrent_downloader.routers.transfers.is_vpn_bound", return_value=True)

        client.post("/api/v1/download", json=_download_body(MOVIE_MAGNET, "movie", dry_run=True))

        from torrent_downloader.core.cache import app_cache

        assert app_cache.get("media_type:1234567890abcdef1234567890abcdef12345678") is None


class TestTransferInfoEndpoint:
    def test_returns_cached_metadata_for_known_hash(self, client: TestClient) -> None:
        from torrent_downloader.core.cache import app_cache

        app_cache.set(
            "media_type:abc123",
            {"media_type": "movie", "host_path": "F:\\Media\\Movies", "tmdb_id": TMDB_ID},
        )

        response = client.get("/api/v1/transfers/abc123/info")

        assert response.status_code == 200
        body = response.json()
        assert body["media_type"] == "movie"
        assert body["host_path"] == "F:\\Media\\Movies"
        assert body["tmdb_id"] == TMDB_ID
        assert set(body.keys()) == {"media_type", "host_path", "tmdb_id"}

    def test_returns_404_for_unknown_hash(self, client: TestClient) -> None:
        response = client.get("/api/v1/transfers/unknownhash/info")
        assert response.status_code == 404

    def test_404_body_has_transfer_not_found_code(self, client: TestClient) -> None:
        body = client.get("/api/v1/transfers/unknownhash/info").json()
        assert body["code"] == ErrorCode.TRANSFER_NOT_FOUND.value

    def test_hash_lookup_is_case_insensitive(self, client: TestClient) -> None:
        from torrent_downloader.core.cache import app_cache

        app_cache.set(
            "media_type:abc123",
            {"media_type": "show", "host_path": "F:\\Media\\Shows", "tmdb_id": TMDB_ID},
        )

        response = client.get("/api/v1/transfers/ABC123/info")

        assert response.status_code == 200
        assert response.json()["media_type"] == "show"
