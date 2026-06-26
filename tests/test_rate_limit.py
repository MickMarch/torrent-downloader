"""Tests for rate limiting behavior."""

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture


class TestRateLimitBreached:
    def test_breaching_limit_returns_429(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            return_value={
                "total_gb": 100.0,
                "used_gb": 50.0,
                "free_gb": 50.0,
                "used_percent": 50.0,
            },
        )
        for _ in range(61):
            response = client.get("/api/v1/storage?path=/tmp")
        assert response.status_code == 429

    def test_429_response_has_rate_limited_code(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            return_value={
                "total_gb": 100.0,
                "used_gb": 50.0,
                "free_gb": 50.0,
                "used_percent": 50.0,
            },
        )
        for _ in range(61):
            response = client.get("/api/v1/storage?path=/tmp")
        assert response.json()["code"] == "RATE_LIMITED"

    def test_429_response_has_retry_after_header(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.system.get_disk_usage",
            return_value={
                "total_gb": 100.0,
                "used_gb": 50.0,
                "free_gb": 50.0,
                "used_percent": 50.0,
            },
        )
        for _ in range(61):
            response = client.get("/api/v1/storage?path=/tmp")
        assert "retry-after" in response.headers


class TestRateLimitWithinBounds:
    def test_requests_within_limit_pass(self, client: TestClient, mocker: MockerFixture) -> None:
        mocker.patch("torrent_downloader.routers.system.get_torrent_client", return_value=None)
        for _ in range(5):
            response = client.get("/api/v1/health")
        assert response.status_code == 200


class TestSearchEndpointLimit:
    def test_breaching_search_limit_returns_429(
        self, client: TestClient, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "torrent_downloader.routers.search.search_tmdb_multi",
            return_value=[],
        )
        for _ in range(21):
            response = client.get("/api/v1/search/tmdb?query=test")
        assert response.status_code == 429
