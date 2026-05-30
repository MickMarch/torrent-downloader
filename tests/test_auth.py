"""Tests for API key authentication middleware."""

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture


@pytest.fixture
def unauthed_client() -> TestClient:
    from torrent_downloader.main import app
    return TestClient(app, raise_server_exceptions=False)


class TestProtectedEndpoints:
    def test_missing_key_returns_403(self, unauthed_client: TestClient) -> None:
        assert unauthed_client.get("/api/v1/storage?path=/tmp").status_code == 403

    def test_wrong_key_returns_403(self, unauthed_client: TestClient) -> None:
        assert unauthed_client.get(
            "/api/v1/storage?path=/tmp", headers={"X-API-Key": "wrong-key"}
        ).status_code == 403

    def test_correct_key_passes(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            return_value={"total_gb": 100.0, "used_gb": 50.0, "free_gb": 50.0, "used_percent": 50.0},
        )
        assert client.get("/api/v1/storage?path=/tmp").status_code == 200

    def test_missing_key_error_code(self, unauthed_client: TestClient) -> None:
        body = unauthed_client.get("/api/v1/storage?path=/tmp").json()
        assert body["code"] == "UNAUTHORIZED"

    def test_wrong_key_error_code(self, unauthed_client: TestClient) -> None:
        body = unauthed_client.get(
            "/api/v1/storage?path=/tmp", headers={"X-API-Key": "wrong-key"}
        ).json()
        assert body["code"] == "UNAUTHORIZED"


class TestHealthEndpointExempt:
    def test_health_reachable_without_key(self, unauthed_client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.routers.system.get_torrent_client", return_value=None)
        assert unauthed_client.get("/api/v1/health").status_code == 200

    def test_health_reachable_with_wrong_key(self, unauthed_client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.routers.system.get_torrent_client", return_value=None)
        assert unauthed_client.get(
            "/api/v1/health", headers={"X-API-Key": "wrong-key"}
        ).status_code == 200
