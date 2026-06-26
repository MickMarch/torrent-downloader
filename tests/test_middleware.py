"""Tests for request logging middleware."""

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture


class TestRequestIdHeader:
    def test_response_includes_request_id(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.routers.system.get_torrent_client", return_value=None)
        response = client.get("/api/v1/health")
        assert "x-request-id" in response.headers

    def test_request_id_is_valid_uuid(self, client: TestClient, mocker: MockerFixture) -> None:
        import uuid

        mocker.patch("torrent_downloader.routers.system.get_torrent_client", return_value=None)
        response = client.get("/api/v1/health")
        request_id = response.headers["x-request-id"]
        uuid.UUID(request_id)  # raises ValueError if invalid

    def test_each_request_gets_unique_id(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.routers.system.get_torrent_client", return_value=None)
        r1 = client.get("/api/v1/health")
        r2 = client.get("/api/v1/health")
        assert r1.headers["x-request-id"] != r2.headers["x-request-id"]

    def test_error_response_includes_request_id(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            side_effect=FileNotFoundError,
        )
        response = client.get("/api/v1/storage?path=/nonexistent")
        assert "x-request-id" in response.headers


class TestRequestLogging:
    def test_logs_method_path_status_duration(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mock_log = mocker.patch("torrent_downloader.core.middleware.app_logger")
        mocker.patch("torrent_downloader.routers.system.get_torrent_client", return_value=None)
        client.get("/api/v1/health")
        mock_log.info.assert_called_once()
        args = mock_log.info.call_args[0]
        rendered = args[0] % args[1:]
        assert "GET" in rendered
        assert "/api/v1/health" in rendered
        assert "200" in rendered
        assert "ms" in rendered

    def test_logs_query_string(self, client: TestClient, mocker: MockerFixture) -> None:
        mock_log = mocker.patch("torrent_downloader.core.middleware.app_logger")
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            return_value={
                "total_gb": 100.0,
                "used_gb": 50.0,
                "free_gb": 50.0,
                "used_percent": 50.0,
            },
        )
        client.get("/api/v1/storage?path=/tmp")
        args = mock_log.info.call_args[0]
        rendered = args[0] % args[1:]
        assert "path=/tmp" in rendered

    def test_logs_on_protected_endpoint(self, client: TestClient, mocker: MockerFixture) -> None:
        mock_log = mocker.patch("torrent_downloader.core.middleware.app_logger")
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            return_value={
                "total_gb": 100.0,
                "used_gb": 50.0,
                "free_gb": 50.0,
                "used_percent": 50.0,
            },
        )
        client.get("/api/v1/storage?path=/tmp")
        mock_log.info.assert_called_once()

    def test_logs_failed_request(self, client: TestClient, mocker: MockerFixture) -> None:
        mock_log = mocker.patch("torrent_downloader.core.middleware.app_logger")
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            side_effect=FileNotFoundError,
        )
        client.get("/api/v1/storage?path=/nonexistent")
        mock_log.info.assert_called_once()
        args = mock_log.info.call_args[0]
        rendered = args[0] % args[1:]
        assert "404" in rendered
