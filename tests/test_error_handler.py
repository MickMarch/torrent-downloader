"""Tests for global exception handler: response shape and HTTP status codes."""

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from torrent_downloader.core.errors import AppException, ErrorCode


class TestAppExceptionHandler:
    def test_returns_correct_status_code(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(
            "torrent_downloader.routers.system.get_torrent_client",
            side_effect=AppException(
                status_code=503, code=ErrorCode.QB_UNAVAILABLE, detail="Unavailable."
            ),
        )
        assert client.get("/api/v1/health").status_code == 503

    def test_response_has_status_field(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            side_effect=AppException(
                status_code=404, code=ErrorCode.PATH_NOT_FOUND, detail="Not found."
            ),
        )
        body = client.get("/api/v1/storage?path=/bad").json()
        assert body["status"] == "error"

    def test_response_has_code_field(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            side_effect=AppException(
                status_code=404, code=ErrorCode.PATH_NOT_FOUND, detail="Not found."
            ),
        )
        body = client.get("/api/v1/storage?path=/bad").json()
        assert body["code"] == ErrorCode.PATH_NOT_FOUND.value

    def test_response_has_detail_field(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            side_effect=AppException(
                status_code=404, code=ErrorCode.PATH_NOT_FOUND, detail="Not found."
            ),
        )
        body = client.get("/api/v1/storage?path=/bad").json()
        assert body["detail"] == "Not found."

    def test_response_has_no_extra_fields(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            side_effect=AppException(
                status_code=404, code=ErrorCode.PATH_NOT_FOUND, detail="Not found."
            ),
        )
        body = client.get("/api/v1/storage?path=/bad").json()
        assert set(body.keys()) == {"status", "code", "detail"}


class TestValidationErrorHandler:
    def test_missing_required_param_returns_422(self, client: TestClient) -> None:
        assert client.get("/api/v1/storage").status_code == 422

    def test_validation_error_has_status_field(self, client: TestClient) -> None:
        body = client.get("/api/v1/storage").json()
        assert body["status"] == "error"

    def test_validation_error_has_code_field(self, client: TestClient) -> None:
        body = client.get("/api/v1/storage").json()
        assert body["code"] == ErrorCode.INVALID_INPUT.value

    def test_validation_error_has_detail_field(self, client: TestClient) -> None:
        body = client.get("/api/v1/storage").json()
        assert "detail" in body


class TestRouterErrorCodes:
    def test_storage_file_not_found_returns_path_not_found_code(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            side_effect=FileNotFoundError("No such file or directory"),
        )
        body = client.get("/api/v1/storage?path=/bad").json()
        assert body["code"] == ErrorCode.PATH_NOT_FOUND.value

    def test_storage_permission_error_returns_permission_denied_code(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            side_effect=PermissionError("Permission denied"),
        )
        body = client.get("/api/v1/storage?path=/restricted").json()
        assert body["code"] == ErrorCode.PERMISSION_DENIED.value

    def test_download_no_client_returns_qb_unavailable_code(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch("torrent_downloader.routers.transfers.get_torrent_client", return_value=None)
        body = client.post(
            "/api/v1/download",
            json={"magnet_uri": "magnet:?xt=urn:btih:abc", "media_type": "movie"},
        ).json()
        assert body["code"] == ErrorCode.QB_UNAVAILABLE.value

    def test_download_vpn_not_bound_returns_vpn_not_bound_code(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.transfers.get_torrent_client",
            return_value=mocker.MagicMock(),
        )
        mocker.patch("torrent_downloader.routers.transfers.is_vpn_bound", return_value=False)
        body = client.post(
            "/api/v1/download",
            json={"magnet_uri": "magnet:?xt=urn:btih:abc", "media_type": "movie"},
        ).json()
        assert body["code"] == ErrorCode.VPN_NOT_BOUND.value

    def test_torrent_search_no_client_returns_qb_unavailable_code(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch("torrent_downloader.routers.search.get_torrent_client", return_value=None)
        body = client.get("/api/v1/search/torrents?query=test").json()
        assert body["code"] == ErrorCode.QB_UNAVAILABLE.value
